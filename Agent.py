"""
AI代理基础类模块

该模块定义了一个通用的AI代理基础类，用于与OpenAI或本地大模型API进行交互。
支持多种AI模型、能力感知的参数适配、重试机制、并发API调用等功能。
"""

# 标准库导入
import os
import random
import time
import json
import logging
import uuid

# 第三方库导入
import requests
import yaml
from openai import OpenAI  # OpenAI官方客户端库


logger = logging.getLogger(__name__)

# Values here are deliberately conservative defaults.  Deployments can override a
# model (or add an internal model) with ``model_capabilities`` in their API YAML.
# ``supports`` controls which optional request fields are sent to a provider.
DEFAULT_MODEL_CAPABILITIES = {
    "openai": {
        "default": {
            "context_window": 128000,
            "max_output_tokens": 16384,
            "supports": {"temperature": True, "top_p": True,
                         "frequency_penalty": True, "presence_penalty": True,
                         "max_tokens": True},
        },
        "gpt-4o": {"context_window": 128000, "max_output_tokens": 16384},
        "gpt-4o-mini": {"context_window": 128000, "max_output_tokens": 16384},
        # Newer reasoning models use max_completion_tokens rather than max_tokens.
        "o1": {"context_window": 200000, "max_output_tokens": 100000,
               "supports": {"temperature": False, "top_p": False,
                            "frequency_penalty": False, "presence_penalty": False,
                            "max_tokens": False, "max_completion_tokens": True}},
    },
    "openrouter": {"default": {"context_window": 128000, "max_output_tokens": 16384}},
    "vllm": {"default": {"context_window": 32768, "max_output_tokens": 8192}},
    "local": {"default": {"context_window": 32768, "max_output_tokens": 8192,
                            "supports": {"temperature": True, "top_p": True,
                                         "frequency_penalty": False, "presence_penalty": False,
                                         "max_tokens": True}}},
    "ollama": {"default": {"context_window": 32768, "max_output_tokens": 8192}},
}

DEFAULT_SUPPORTS = {
    "temperature": True,
    "top_p": True,
    "frequency_penalty": True,
    "presence_penalty": True,
    "max_tokens": True,
    "max_completion_tokens": False,
}

# ============================ 全局配置 ============================
# 默认系统提示词
sys_default_prompt = "You are a helpful assistant."


class BaseAgent:
    """
    AI代理基础类

    该类封装了与OpenAI API的交互逻辑，提供了统一的接口来调用各种语言模型。
    支持多个API密钥的随机选择、重试机制、参数可配置等特性。

    Attributes:
        config: 从配置文件加载的配置信息
        api_type: API类型，可选 openai、openrouter、vllm、local 或 ollama
        api_keys: API密钥列表（本地模型可不配置）
        model_name: 使用的模型名称
        base_url: API基础URL
        default_system_prompt: 默认系统提示词
        client: OpenAI客户端实例（本地模型时为 None）
    """

    def __init__(
        self, system_prompt=sys_default_prompt, config_path="./config_random/zyf.yaml"
    ):
        """
        初始化AI代理

        Args:
            system_prompt (str): 系统提示词，定义AI的角色和行为模式
            config_path (str): 配置文件路径，包含API密钥、模型名称等信息
        """
        # 获取配置文件的绝对路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, config_path)

        # 加载配置文件
        with open(config_path, "r") as config_file:
            self.config = yaml.load(config_file, Loader=yaml.FullLoader)

        # 提取配置信息
        self.api_type = str(
            self.config.get("api_type", self.config.get("provider", "openai"))
        ).strip().lower()
        self.provider = str(self.config.get("provider", self.api_type)).strip().lower()
        self.api_keys = self.config.get("api_key", [])  # 本地模型不需要API密钥
        if isinstance(self.api_keys, str):
            self.api_keys = [self.api_keys]
        self.model_name = self.config["model_name"]  # 模型名称
        self.base_url = self.config["base_url"]  # API基础URL
        self.request_timeout = self.config.get("timeout", 120)
        self.local_think = self.config.get("think", False)
        self.local_max_tokens = self.config.get("max_tokens")
        self.default_system_prompt = system_prompt  # 默认系统提示词
        self.max_retries = int(self.config.get("max_retries", 3))
        self.retry_delay = float(self.config.get("retry_delay", 1))
        self.model_capabilities = self._resolve_model_capabilities()

        if self.api_type in {"local", "ollama"}:
            # 同时支持 http://host:port 和完整的 /api/chat 地址。
            self.local_chat_url = self.base_url.rstrip("/")
            if not self.local_chat_url.endswith("/api/chat"):
                self.local_chat_url += "/api/chat"
            self.client = None
        elif self.api_type in {"openai", "openrouter", "vllm"}:
            if not self.api_keys:
                raise ValueError("OpenAI API 配置缺少 api_key")
            # 初始化OpenAI客户端，随机选择一个API密钥
            self.client = OpenAI(
                api_key=random.choice(self.api_keys),  # 从多个密钥中随机选择
                base_url=self.base_url,  # 设置API基础URL
                timeout=self.request_timeout,
            )
        else:
            raise ValueError(
                f"不支持的 api_type: {self.api_type}，请使用 openai、local 或 ollama"
            )

    def _resolve_model_capabilities(self):
        """Return provider/model defaults merged with optional YAML overrides."""
        provider_defaults = DEFAULT_MODEL_CAPABILITIES.get(
            self.provider, DEFAULT_MODEL_CAPABILITIES["openai"]
        )
        resolved = dict(provider_defaults.get("default", {}))
        resolved["supports"] = dict(DEFAULT_SUPPORTS)
        resolved["supports"].update(provider_defaults.get("default", {}).get("supports", {}))
        model_defaults = provider_defaults.get(self.model_name, {})
        if not model_defaults:
            # Capability tables can use a stable model-family prefix (for example
            # ``o1`` also covers ``o1-mini``) without listing every revision.
            model_defaults = next(
                (value for key, value in provider_defaults.items()
                 if key != "default" and self.model_name.startswith(key)),
                {},
            )
        resolved.update({key: value for key, value in model_defaults.items() if key != "supports"})
        resolved["supports"].update(model_defaults.get("supports", {}))

        overrides = self.config.get("model_capabilities", {})
        # Support both {model: {...}} and {provider: {model: {...}}} forms.
        provider_overrides = overrides.get(self.provider, {}) if isinstance(overrides, dict) else {}
        override = {}
        if isinstance(overrides, dict):
            override.update(overrides.get("default", {}))
            override.update(overrides.get(self.model_name, {}))
        if isinstance(provider_overrides, dict):
            override.update(provider_overrides.get("default", {}))
            override.update(provider_overrides.get(self.model_name, {}))
        resolved.update({key: value for key, value in override.items() if key != "supports"})
        resolved["supports"].update(override.get("supports", {}))
        return resolved

    @staticmethod
    def _estimate_input_tokens(messages):
        """Cheap, provider-independent estimate used only to protect context limits."""
        serialized = json.dumps(messages, ensure_ascii=False, default=str)
        # ASCII prose averages roughly four chars/token; non-ASCII text is
        # estimated more conservatively because CJK and structured payloads can
        # tokenize much more densely.  The fixed part covers chat framing.
        ascii_chars = sum(char.isascii() for char in serialized)
        non_ascii_chars = len(serialized) - ascii_chars
        return max(1, (ascii_chars + 3) // 4 + non_ascii_chars * 2 + 8 * len(messages))

    def _effective_max_tokens(self, messages, requested_max_tokens):
        input_tokens = self._estimate_input_tokens(messages)
        context_window = int(self.model_capabilities["context_window"])
        model_max_output = int(self.model_capabilities["max_output_tokens"])
        # Reserve a small framing margin so token-estimation error does not turn
        # a near-limit request into a deterministic provider-side 400.
        available = context_window - input_tokens - max(32, context_window // 1000)
        effective = min(int(requested_max_tokens), model_max_output, available)
        if effective < 1:
            raise ValueError(
                "输入估算为 %s tokens，已超过 %s 的上下文窗口 %s" %
                (input_tokens, self.model_name, context_window)
            )
        return effective, input_tokens

    @staticmethod
    def _request_id(response_or_error):
        request_id = getattr(response_or_error, "_request_id", None)
        if request_id:
            return request_id
        response = getattr(response_or_error, "response", None)
        headers = getattr(response, "headers", {}) if response is not None else {}
        return headers.get("x-request-id") or headers.get("request-id")

    @staticmethod
    def _error_code(error):
        return (getattr(error, "code", None) or getattr(error, "status_code", None)
                or getattr(getattr(error, "response", None), "status_code", None)
                or error.__class__.__name__)

    @staticmethod
    def _is_retryable(error):
        """Only retry transient transport, rate-limit, and server failures."""
        if isinstance(error, (requests.Timeout, requests.ConnectionError)):
            return True
        response = getattr(error, "response", None)
        status = getattr(error, "status_code", None) or getattr(response, "status_code", None)
        if status is not None:
            return status == 408 or status == 409 or status == 429 or status >= 500
        # The OpenAI SDK exposes these names across supported 1.x releases.
        return error.__class__.__name__ in {"APITimeoutError", "APIConnectionError"}

    def _log_api_event(self, **event):
        logger.info("llm_request %s", json.dumps(event, ensure_ascii=False, default=str))

    def __post_process(self, response):
        """
        处理OpenAI API的响应数据

        从原始API响应中提取有用信息，包括生成的文本内容和使用的token数量。

        Args:
            response: OpenAI API返回的原始响应对象

        Returns:
            dict: 包含响应内容和token使用情况的字典
        """
        if self.api_type in {"local", "ollama"}:
            message = response.get("message") or {}
            content = message.get("content")
            if content is None:
                raise ValueError("本地模型响应中缺少 message.content")
            return {
                "response": content,
                "total_tokens": response.get("total_tokens")
                or response.get("prompt_eval_count", 0)
                + response.get("eval_count", 0),
            }

        usage = getattr(response, "usage", None)
        return {
            "response": response.choices[0].message.content,  # 提取AI生成的文本内容
            "total_tokens": getattr(usage, "total_tokens", 0),
        }

    def __call_api(
        self,
        messages,
        temperature=0.9,
        max_tokens=8192,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        **kwargs,
    ):
        """
        调用OpenAI API并获取响应

        仅在超时、连接错误、限流及服务端错误时重试；参数等确定性 4xx
        会立即失败。请求参数会按 provider/model capability 过滤，并根据
        估算输入 token 与上下文窗口收缩输出上限。

        Args:
            messages (list): 对话消息列表
            temperature (float): 温度参数，控制输出的随机性
            max_tokens (int): 最大生成token数量
            top_p (float): 核采样参数
            frequency_penalty (float): 频率惩罚参数
            presence_penalty (float): 存在惩罚参数
            **kwargs: 其他可选参数

        Returns:
            response: OpenAI API的原始响应对象

        Raises:
            Exception: 当API调用失败时抛出异常
        """
        effective_max_tokens, input_tokens = self._effective_max_tokens(messages, max_tokens)
        request_id = str(uuid.uuid4())
        for attempt in range(1, self.max_retries + 1):
            started_at = time.perf_counter()
            try:
                if self.api_type in {"local", "ollama"}:
                    local_kwargs = dict(kwargs)
                    think = local_kwargs.pop("think", self.local_think)
                    timeout = local_kwargs.pop("timeout", self.request_timeout)
                    num_predict = effective_max_tokens
                    if self.local_max_tokens is not None:
                        num_predict = min(num_predict, int(self.local_max_tokens))
                    local_kwargs.pop("stream", None)
                    supplied_options = local_kwargs.pop("options", {})
                    supports = self.model_capabilities["supports"]
                    options = {"num_predict": num_predict, **supplied_options}
                    if supports.get("temperature", False):
                        options["temperature"] = temperature
                    if supports.get("top_p", False):
                        options["top_p"] = top_p
                    payload = {"model": self.model_name, "messages": messages,
                               "stream": False, "think": think, "options": options,
                               **local_kwargs}
                    response = requests.post(self.local_chat_url, json=payload, timeout=timeout)
                    response.raise_for_status()
                    body = response.json()
                    self._log_api_event(
                        event="success", provider=self.provider, model=self.model_name,
                        request_id=response.headers.get("x-request-id", request_id),
                        latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
                        input_tokens=input_tokens, output_tokens=body.get("eval_count"),
                        total_tokens=body.get("total_tokens"), attempt=attempt, error_code=None,
                        requested_max_tokens=max_tokens, effective_max_tokens=num_predict)
                    return body

                request = {"model": self.model_name, "messages": messages, **kwargs}
                supports = self.model_capabilities["supports"]
                for name, value in (("temperature", temperature), ("top_p", top_p),
                                    ("frequency_penalty", frequency_penalty),
                                    ("presence_penalty", presence_penalty)):
                    if supports.get(name, False):
                        request[name] = value
                if supports.get("max_completion_tokens", False):
                    request["max_completion_tokens"] = effective_max_tokens
                elif supports.get("max_tokens", True):
                    request["max_tokens"] = effective_max_tokens
                response = self.client.chat.completions.create(**request)
                usage = getattr(response, "usage", None)
                self._log_api_event(
                    event="success", provider=self.provider, model=self.model_name,
                    request_id=self._request_id(response) or request_id,
                    latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
                    input_tokens=getattr(usage, "prompt_tokens", input_tokens),
                    output_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None), attempt=attempt,
                    error_code=None, requested_max_tokens=max_tokens,
                    effective_max_tokens=effective_max_tokens)
                return response
            except Exception as e:
                retryable = self._is_retryable(e)
                self._log_api_event(
                    event="error", provider=self.provider, model=self.model_name,
                    request_id=self._request_id(e) or request_id,
                    latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
                    input_tokens=input_tokens, output_tokens=None, total_tokens=None,
                    attempt=attempt, error_code=self._error_code(e), retryable=retryable,
                    requested_max_tokens=max_tokens, effective_max_tokens=effective_max_tokens,
                )
                print(f"[API错误] {str(e)}")
                if not retryable or attempt == self.max_retries:
                    raise
                time.sleep(self.retry_delay * attempt)

    def get_response(
        self,
        user_input=None,
        system_prompt=None,
        temperature=0.9,
        max_tokens=4096,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        debug=False,
        messages=None,  # 新增 messages 参数
        **kwargs,
    ):
        """
        获取AI的响应，支持多种输入模式

        该方法是主要的对外接口，支持传入单个用户输入或完整的对话消息列表。
        具有灵活的参数配置和错误处理机制。

        Args:
            user_input (str, optional): 用户输入的文本内容
            system_prompt (str, optional): 系统提示词，默认使用初始化时的提示词
            temperature (float): 温度参数，控制输出的随机性 (0-1)
            max_tokens (int): 最大生成token数量
            top_p (float): 核采样参数 (0-1)
            frequency_penalty (float): 频率惩罚参数 (-2.0-2.0)
            presence_penalty (float): 存在惩罚参数 (-2.0-2.0)
            debug (bool): 是否开启调试模式，会打印响应内容
            messages (list, optional): 完整的对话消息列表
            **kwargs: 其他传递给API的参数

        Returns:
            dict: 包含响应内容和token使用情况的字典，
                  或在出错时返回包含error字段的字典
        """
        try:
            # 使用默认系统提示词（如果未提供）
            if system_prompt is None:
                system_prompt = self.default_system_prompt

            # 初始化消息列表（如果未提供）
            if messages is None:
                messages = []
            else:
                # 不修改调用方传入的历史消息列表。
                messages = [dict(message) for message in messages]

            # 检查并添加系统提示词（如果不存在）
            if not any(msg["role"] == "system" for msg in messages):
                messages.insert(0, {"role": "system", "content": system_prompt})

            # 添加用户输入到消息列表（如果提供了user_input）
            if user_input is not None:
                messages.append({"role": "user", "content": user_input})

            # 清理kwargs中的messages参数，避免参数冲突
            if "messages" in kwargs:
                kwargs.pop("messages")

            # 调用底层API接口
            response = self.__call_api(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                **kwargs,
            )

            # 处理API响应，提取有用信息
            result = self.__post_process(response)

            # 调试模式：以绿色文字打印响应内容
            if debug:
                print("\033[92m" + f"[响应] {result['response']}" + "\033[0m")

            # 返回处理后的结果
            return result

        except Exception as e:
            # 错误处理：以红色文字打印错误信息
            print("\033[91m" + f"[错误] {str(e)}" + "\033[0m")
            return {"error": f"Error: {str(e)}"}


# ============================ 模块初始化和测试 ============================
# 记录模块加载的开始时间
start_time = time.time()
start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
print("模块加载开始时间:", start_date)
