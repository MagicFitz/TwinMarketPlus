"""Safe read/write access to the two local model configuration files."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml

from backend.settings import Settings


ModelKind = Literal["language", "embedding"]

_FILES: dict[ModelKind, str] = {
    "language": "api.yaml",
    "embedding": "embedding.yaml",
}


class ModelSettingsService:
    """Expose a deliberately small, credential-safe model settings contract."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def get_all(self) -> dict[str, dict[str, Any]]:
        return {kind: self.get(kind) for kind in _FILES}

    def get(self, kind: ModelKind) -> dict[str, Any]:
        config = self._read(kind)
        api_key = config.get("api_key")
        if isinstance(api_key, list):
            api_key_configured = any(str(value).strip() for value in api_key)
        else:
            api_key_configured = bool(str(api_key or "").strip())

        shared = {
            "kind": kind,
            "configured": bool(config),
            "provider": self._text(config.get("provider")),
            "model_name": self._text(config.get("model_name")),
            "base_url": self._text(config.get("base_url")),
            "timeout": self._number(config.get("timeout")),
            "api_key_configured": api_key_configured,
        }
        if kind == "language":
            api_type = self._text(config.get("api_type")) or "openai"
            return {"api_type": api_type, **shared, "provider": shared["provider"] or api_type}
        return {
            **shared,
            "endpoint": self._text(config.get("endpoint")),
            "max_retries": self._number(config.get("max_retries")),
        }

    def update(self, kind: ModelKind, changes: dict[str, Any], *, api_key_provided: bool) -> dict[str, Any]:
        config = self._read(kind)
        allowed = {"provider", "model_name", "base_url", "timeout"}
        if kind == "language":
            allowed.add("api_type")
        else:
            allowed.update({"endpoint", "max_retries"})

        for key in allowed:
            if key in changes:
                value = changes[key]
                if value is None or value == "":
                    config.pop(key, None)
                else:
                    config[key] = value

        if api_key_provided:
            raw_key = str(changes.get("api_key") or "").strip()
            if raw_key:
                # Language-model callers support key rotation, hence the list.
                config["api_key"] = [raw_key] if kind == "language" else raw_key
            else:
                config.pop("api_key", None)

        self._validate(kind, config)
        self._write(kind, config)
        return self.get(kind)

    def _path(self, kind: ModelKind) -> Path:
        return self.settings.project_path(Path("config") / _FILES[kind])

    def _read(self, kind: ModelKind) -> dict[str, Any]:
        path = self._path(kind)
        if not path.is_file():
            return {}
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ValueError(f"{_FILES[kind]} 不是有效的 YAML 配置") from error
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{_FILES[kind]} 必须是键值配置")
        return value

    def _write(self, kind: ModelKind, config: dict[str, Any]) -> None:
        path = self._path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A same-directory replace avoids leaving a partly-written credential file.
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                yaml.safe_dump(config, output, allow_unicode=True, sort_keys=False)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _text(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _number(value: Any) -> int | None:
        return value if isinstance(value, int | float) and not isinstance(value, bool) else None

    @staticmethod
    def _validate(kind: ModelKind, config: dict[str, Any]) -> None:
        model_name = str(config.get("model_name") or "").strip()
        if not model_name:
            raise ValueError("模型名称不能为空")
        if len(model_name) > 200:
            raise ValueError("模型名称不能超过 200 个字符")
        for name in ("base_url", "endpoint"):
            value = config.get(name)
            if value in (None, ""):
                continue
            parsed = urlparse(str(value))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{name} 必须是完整的 http(s) 地址")
        for name in ("timeout", "max_retries"):
            if name not in config:
                continue
            if not isinstance(config[name], int | float) or isinstance(config[name], bool) or config[name] < 0:
                raise ValueError(f"{name} 必须是非负数字")
        if kind == "language" and str(config.get("api_type") or "openai") not in {
            "openai", "openrouter", "vllm", "ollama", "local",
        }:
            raise ValueError("不支持的语言模型 API 类型")
