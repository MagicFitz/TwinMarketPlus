"""Unit tests for the provider-aware LLM request boundary."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import requests

from Agent import BaseAgent


def make_agent(**attributes):
    agent = BaseAgent.__new__(BaseAgent)
    agent.provider = "openai"
    agent.api_type = "openai"
    agent.model_name = "test-model"
    agent.max_retries = 3
    agent.retry_delay = 0
    agent.model_capabilities = {
        "context_window": 100,
        "max_output_tokens": 40,
        "supports": {"temperature": False, "top_p": False,
                     "frequency_penalty": False, "presence_penalty": False,
                     "max_tokens": True, "max_completion_tokens": False},
    }
    agent._log_api_event = Mock()
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    for name, value in attributes.items():
        setattr(agent, name, value)
    return agent


class ProviderAwareRequestTests(unittest.TestCase):
    def test_max_tokens_is_limited_by_context_and_model_output(self):
        agent = make_agent()
        effective, input_tokens = agent._effective_max_tokens(
            [{"role": "user", "content": "x" * 100}], 999
        )
        self.assertGreater(input_tokens, 0)
        self.assertLessEqual(effective, 40)
        self.assertLessEqual(effective, 100 - input_tokens - 32)

    def test_unsupported_sampling_parameters_are_not_sent(self):
        agent = make_agent()
        response = SimpleNamespace(usage=None, _request_id="provider-request")
        create = Mock(return_value=response)
        agent.client.chat.completions.create = create

        result = agent._BaseAgent__call_api([{"role": "user", "content": "hi"}], max_tokens=9)

        self.assertIs(result, response)
        request = create.call_args.kwargs
        self.assertEqual(request["max_tokens"], 9)
        for parameter in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
            self.assertNotIn(parameter, request)

    def test_deterministic_400_is_not_retried(self):
        agent = make_agent()
        response = SimpleNamespace(status_code=400, headers={})
        failure = requests.HTTPError("invalid parameter", response=response)
        create = Mock(side_effect=failure)
        agent.client.chat.completions.create = create

        with self.assertRaises(requests.HTTPError):
            agent._BaseAgent__call_api([{"role": "user", "content": "hi"}])

        self.assertEqual(create.call_count, 1)
        self.assertFalse(agent._log_api_event.call_args.kwargs["retryable"])

    def test_rate_limit_is_retried(self):
        agent = make_agent(max_retries=2)
        response = SimpleNamespace(status_code=429, headers={})
        failure = requests.HTTPError("rate limited", response=response)
        success = SimpleNamespace(usage=None, _request_id="done")
        create = Mock(side_effect=[failure, success])
        agent.client.chat.completions.create = create

        self.assertIs(agent._BaseAgent__call_api([{"role": "user", "content": "hi"}]), success)
        self.assertEqual(create.call_count, 2)
