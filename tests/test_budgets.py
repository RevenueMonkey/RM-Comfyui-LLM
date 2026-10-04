"""Offline budget contracts, using the existing host/network stubs."""
import unittest
from unittest.mock import AsyncMock, patch

from test_providers import caps, body, n, s, t
from rm_test import budgets as b


class BudgetContracts(unittest.TestCase):
    def test_automatic_display_scale_preserves_request(self):
        c = {"parameters": {}, "endpoints": [
            {"id": "a", "context_length": 100000, "max_tokens": 8000},
            {"id": "b", "context_length": 200000, "max_tokens": 16000},
        ]}
        parameters, plan = b.apply_budgets("OpenRouter", "test", c, {}, endpoint="a")
        self.assertEqual(parameters, {})
        self.assertEqual(plan["display_limits"], {"input": 100000, "thinking": 8000, "output": 8000})
        result = {"usage": {"prompt_tokens": 833, "completion_tokens": 784,
                            "completion_tokens_details": {"reasoning_tokens": 666}}}
        report = b.usage_report("OpenRouter", result, plan)
        for kind, used in (("input", 833), ("thinking", 666), ("output", 118)):
            self.assertEqual(report[kind]["used"], used)
            self.assertGreater(report[kind]["fraction"], 0)
            self.assertEqual(report[kind]["scale_source"], "model_limit")
        plan["input"] = 1000
        self.assertEqual(b.usage_report("OpenRouter", result, plan)["input"]["fraction"], .833)

    def test_automatic_estimated_scale_and_unknown_usage(self):
        plan = dict(input=0, thinking=0, output=0, thinking_mode="allowance", thinking_possible=True)
        report = b.usage_report("OpenRouter", {"usage": {"prompt_tokens": 833}}, plan, "answer")
        self.assertEqual(report["input"]["scale_source"], "estimated")
        self.assertGreater(report["input"]["fraction"], 0)
        self.assertGreater(report["output"]["fraction"], 0)
        self.assertIsNone(report["thinking"]["used"])
        self.assertEqual(report["thinking"]["fraction"], 0)

    def test_zero_preserves_settings(self):
        parameters = {"max_tokens": 9000, "reasoning": {"enabled": True, "max_tokens": 2048}}
        changed, plan = b.apply_budgets("Anthropic", "claude-sonnet-4-5", caps("Anthropic", "claude-sonnet-4-5"), parameters)
        self.assertEqual(changed, parameters)
        self.assertEqual(plan["thinking"], 2048)
        self.assertEqual(plan["output"], 6952)
        changed["reasoning"]["enabled"] = False
        self.assertTrue(parameters["reasoning"]["enabled"])

    def test_shared_limit_without_numeric_thinking(self):
        for provider, model, key in (("OpenAI", "o3", "max_completion_tokens"), ("DeepSeek", "deepseek-reasoner", "max_tokens")):
            parameters, plan = b.apply_budgets(provider, model, caps(provider, model), {}, 0, 2000, 1000)
            self.assertEqual(parameters, {key: 3000})
            self.assertEqual(plan["thinking_mode"], "allowance")
            t.translate(provider, body(model, **parameters), caps(provider, model))

    def test_claude_numeric_and_adaptive(self):
        for model, expected in (("claude-sonnet-4-5", "numeric"), ("claude-sonnet-4-6", "allowance")):
            c = caps("Anthropic", model)
            parameters, plan = b.apply_budgets("Anthropic", model, c, {"reasoning": {"enabled": True}}, 0, 2048, 1024)
            _, native = t.translate("Anthropic", body(model, **parameters), c)
            self.assertEqual(native["max_tokens"], 3072)
            self.assertEqual(plan["thinking_mode"], expected)
            self.assertEqual(native["thinking"], {"type": "enabled", "budget_tokens": 2048} if expected == "numeric" else {"type": "adaptive"})
        with self.assertRaises(s.RMError):
            b.apply_budgets("Anthropic", "claude-sonnet-4-5", caps("Anthropic", "claude-sonnet-4-5"), {"reasoning": {"enabled": True}}, 0, 100, 1000)

    def test_output_uses_existing_thinking_allowance(self):
        c = caps("Anthropic", "claude-sonnet-4-5")
        for reasoning, expected in (({"enabled": True}, 1024), ({"enabled": True, "max_tokens": 2048}, 2048)):
            parameters, plan = b.apply_budgets("Anthropic", "claude-sonnet-4-5", c, {"reasoning": reasoning}, 0, 0, 512)
            self.assertEqual(parameters["max_tokens"], expected + 512)
            self.assertEqual(parameters["reasoning"], reasoning)

    def test_gemini_and_fireworks_numeric_controls(self):
        for provider, model in (("Google Gemini", "gemini-2.5-flash"), ("Fireworks AI", "accounts/fireworks/models/qwen3-235b-a22b")):
            c = caps(provider, model)
            if provider == "Fireworks AI":
                c["reasoning_options"]["supports_budget"] = True
                c["parameters"]["reasoning"] = {"type": "object"}
            parameters, plan = b.apply_budgets(provider, model, c, {}, 0, 2048, 1000)
            _, native = t.translate(provider, body(model, **parameters), c)
            self.assertEqual(plan["thinking_mode"], "numeric")
            if provider == "Google Gemini":
                self.assertEqual(native["generationConfig"]["thinkingConfig"]["thinkingBudget"], 2048)
                self.assertEqual(native["generationConfig"]["maxOutputTokens"], 3048)
            else:
                self.assertEqual(native["reasoning_effort"], 2048)

    def test_disabled_and_nonreasoning(self):
        c = caps("Google Gemini", "gemini-2.5-flash")
        parameters, plan = b.apply_budgets("Google Gemini", "gemini-2.5-flash", c, {"reasoning": {"enabled": False}}, 0, 2000, 1000)
        self.assertEqual(parameters, {"max_tokens": 1000, "reasoning": {"enabled": False}})
        self.assertEqual(plan["thinking"], 0)
        parameters, plan = b.apply_budgets("Groq", "text-model", caps("Groq"), {}, 0, 2000, 1000)
        self.assertEqual(parameters, {"max_completion_tokens": 1000})

    def test_openrouter_metadata_and_responses(self):
        c = {"parameters": {"reasoning": {}, "max_tokens": {}}, "reasoning_options": {"supports_max_tokens": True}}
        parameters, plan = b.apply_budgets("OpenRouter", "test", c, {"reasoning": {"effort": "high"}}, 0, 2000, 1000, responses=True)
        self.assertEqual(parameters, {"max_output_tokens": 3000, "reasoning": {"enabled": True, "max_tokens": 2000}})
        c["reasoning_options"] = {}
        parameters, plan = b.apply_budgets("OpenRouter", "test", c, {}, 0, 2000, 1000)
        self.assertNotIn("reasoning", parameters)
        self.assertEqual(plan["thinking_mode"], "allowance")

    def test_invalid_budgets(self):
        for value in (-1, 0.5, True, float("nan"), "100", 2**31):
            with self.assertRaises(s.RMError):
                b.apply_budgets("Groq", "test", caps("Groq"), {}, value)
        with self.assertRaises(s.RMError):
            b.apply_budgets("Groq", "test", caps("Groq"), {"max_completion_tokens": "bad"})

    def test_budget_does_not_enable_known_default_off(self):
        c = caps("Anthropic", "claude-sonnet-4-5")
        parameters, plan = b.apply_budgets("Anthropic", "claude-sonnet-4-5", c, {}, 0, 2048, 1000)
        self.assertEqual(parameters, {"max_tokens": 1000})
        self.assertEqual(plan["thinking_mode"], "off")

    def test_input_estimate_excludes_base64(self):
        small = body()
        large = body()
        for document, length in ((small, 8), (large, 1000000)):
            document["messages"][1]["content"] = [{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * length}}]
        self.assertEqual(b.estimate_input(small), b.estimate_input(large))
        plan = {"input": 1}
        with self.assertRaisesRegex(s.RMError, "No generation sent"):
            b.check_input(large, plan)

    def test_usage_actual_and_hidden(self):
        plan = dict(input=1000, thinking=200, output=300, thinking_mode="allowance", thinking_possible=True, input_estimate=100)
        result = {"usage": {"prompt_tokens": 150, "completion_tokens": 250, "completion_tokens_details": {"reasoning_tokens": 100}}}
        report = b.usage_report("OpenRouter", result, plan)
        self.assertEqual([report[k]["used"] for k in ("input", "thinking", "output")], [150, 100, 150])
        self.assertEqual(report["thinking"]["fraction"], .5)
        report = b.usage_report("OpenAI", {"usage": {"completion_tokens": 250}}, plan, "answer")
        self.assertIsNone(report["thinking"]["used"])
        self.assertIn("not reported", report["thinking"]["tooltip"])
        self.assertIn("Estimated", report["output"]["tooltip"])

    def test_native_usage_and_overflow(self):
        plan = dict(input=100, thinking=100, output=100, thinking_mode="numeric", thinking_possible=True)
        report = b.usage_report("Anthropic", {"usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "cache_creation_input_tokens": 20, "output_tokens": 160, "output_tokens_details": {"thinking_tokens": 60}}}, plan)
        self.assertEqual(report["input"]["used"], 120)
        self.assertEqual(report["input"]["fraction"], 1)
        self.assertIn("exceeded", report["input"]["tooltip"])
        self.assertEqual(report["output"]["used"], 100)
        report = b.usage_report("Google Gemini", {"usage": {"promptTokenCount": 50, "candidatesTokenCount": 40, "thoughtsTokenCount": 30}}, plan)
        self.assertEqual([report[k]["used"] for k in ("input", "thinking", "output")], [50, 30, 40])


class BudgetExecution(unittest.IsolatedAsyncioTestCase):
    async def test_agent_budgets_and_report(self):
        from rm_test.agent import AgentRequest
        c = {"provider": "OpenRouter", "parameters": {"reasoning": {}, "max_tokens": {}}, "reasoning_options": {"default_enabled": False}, "endpoints": []}
        args = dict(provider="OpenRouter", model_name="test", endpoint="Auto", api_key_env="OPENROUTER_API_KEY", credential_source="Environment variable", system_prompt="system", user_prompt='[{"role":"user","content":"hello"}]', parameters_json="{}", timeout_seconds=30, agent_request={"input_ceiling": 8000, "tools": []})
        result = {"status": "complete", "text": "answer", "usage": {"input_tokens": 20, "output_tokens": 60, "output_tokens_details": {"reasoning_tokens": 40}}}
        with patch.object(n, "model_capabilities", AsyncMock(return_value=c)), patch.object(AgentRequest, "request", AsyncMock(return_value=(result,))) as request:
            finished = await n.RMLLM050().generate(**args, input_budget=1000, thinking_budget=200, output_budget=100)
            profile = request.call_args.args[0]
            self.assertEqual(profile["max_output_tokens"], 300)
            self.assertEqual(profile["input_ceiling"], 1000)
            self.assertEqual(finished["ui"]["rm_llm_usage"][0]["thinking"]["used"], 40)
            request.reset_mock()
            with self.assertRaises(s.RMError):
                await n.RMLLM050().generate(**args, input_budget=1)
            request.assert_not_awaited()

    async def test_input_stop_and_generation_contract(self):
        c = caps("OpenAI", "o3")
        response = {"choices": [{"message": {"content": "answer"}}], "usage": {"prompt_tokens": 20, "completion_tokens": 60, "completion_tokens_details": {"reasoning_tokens": 40}}}
        args = dict(provider="OpenAI", model_name="o3", endpoint="Auto", api_key_env="OPENAI_API_KEY", credential_source="Environment variable", system_prompt="system", user_prompt="hello", parameters_json="{}", timeout_seconds=30)
        with patch.object(n, "consume_key", return_value="mock-key"), patch.object(n, "model_capabilities", AsyncMock(return_value=c)), patch.object(n, "provider_complete", AsyncMock(return_value=response)) as complete:
            with self.assertRaisesRegex(s.RMError, "Input budget exceeded"):
                await n.RMLLM050().generate(**args, input_budget=1)
            complete.assert_not_awaited()
            result = await n.RMLLM050().generate(**args, thinking_budget=200, output_budget=100, console_output=True)
            sent = complete.call_args.args[1]
            self.assertEqual(sent["max_completion_tokens"], 300)
            self.assertEqual(sent["stream_options"], {"include_usage": True})
            self.assertEqual(result["ui"]["rm_llm_usage"][0]["output"]["used"], 20)


if __name__ == "__main__":
    unittest.main()
