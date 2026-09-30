import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rm_llm import service
from rm_llm import agent


class ResponseContract(unittest.IsolatedAsyncioTestCase):
    async def test_http_200_errors_keep_safe_detail_and_semantic_status(self):
        from aiohttp import web
        key = "synthetic-secret"
        async def fail(request):
            code = request.match_info["code"]
            return web.json_response({"error": {"code": code, "message": "Upstream failed " + key}}, headers={"Retry-After": "2"})
        app = web.Application()
        app.router.add_get("/{code}", fail)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            for code, expected in [("503", 503), ("402", 402), ("unknown", 0)]:
                with self.assertRaises(service.ProviderHTTPError) as caught:
                    await service.request_json(f"http://127.0.0.1:{port}/{code}", key)
                self.assertEqual(caught.exception.status, expected)
                self.assertIn("HTTP 200", str(caught.exception))
                self.assertIn("Upstream failed", str(caught.exception))
                self.assertNotIn(key, str(caught.exception))
                self.assertEqual(caught.exception.retry_after, 2)
        finally:
            await runner.cleanup()

    def test_incomplete_is_not_a_success(self):
        result = agent.normalize(dict(status="incomplete", output=[dict(type="message", content=[dict(type="output_text", text='{"half":')])]))
        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["calls"], [])

    def test_tool_roundtrip_items(self):
        result = agent.normalize(dict(status="completed", output=[dict(type="function_call", name="lookup_evidence", call_id="call1", arguments='{"ids":["P1"]}')]))
        self.assertEqual(result["calls"][0]["arguments"], {"ids": ["P1"]})
        self.assertEqual(result["status"], "tools")

    def test_partial_tool_arguments_are_rejected(self):
        result = agent.normalize(dict(status="completed", output=[dict(type="function_call", name="lookup_evidence", call_id="call1", arguments='{"ids":')]))
        self.assertEqual(result["status"], "failure")

    def test_refusal_not_retried(self):
        result = agent.normalize(dict(status="completed", output=[dict(type="message", content=[dict(type="refusal")])]))
        self.assertFalse(result["retryable"])

    async def test_no_paid_request_when_input_too_large(self):
        profile = agent.AgentProfile().configure("openai/gpt-6-astra", "SYNTHETIC_KEY", "Auto", "medium", 1000, 1000, 30)[0]
        caps = dict(parameters={"tools": {}}, endpoints=[dict(id="test", context_length=5000)])
        with patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(agent, "request_response_stream", new=AsyncMock()) as send:
            result = await agent.AgentRequest().request(profile, dict(instructions="x" * 9000, input=[], tools=[]))
        self.assertEqual(result[0]["code"], "input_budget")
        send.assert_not_called()

    async def test_transient_error_is_returned_not_hidden_retry(self):
        profile = agent.AgentProfile().configure("openai/gpt-6-astra", "SYNTHETIC_KEY", "Auto", "medium", 1000, 2000, 30)[0]
        caps = dict(parameters={"tools": {}}, endpoints=[dict(id="test", context_length=5000)])
        with patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(agent, "consume_key", return_value="synthetic-secret"), patch.object(agent, "request_response_stream", new=AsyncMock(side_effect=service.ProviderHTTPError(429, "Busy", 4))) as send:
            result = await agent.AgentRequest().request(profile, dict(instructions="test", input=[], tools=[]))
        self.assertTrue(result[0]["retryable"])
        self.assertEqual(result[0]["retry_after"], 4)
        self.assertEqual(send.await_count, 1)

    async def test_vision_is_external_and_does_not_count_base64_as_prompt_text(self):
        import torch
        profile = agent.AgentProfile().configure("test/vision", "SYNTHETIC_KEY", "Auto", "medium", 1000, 64000, 30)[0]
        caps = dict(parameters={}, endpoints=[dict(id="test", context_length=128000)], input_modalities=["text", "image"])
        image = torch.zeros((1, 32, 32, 3))
        response = dict(status="completed", output=[dict(type="message", content=[dict(type="output_text", text='{"accept":true}')])])
        parts = [dict(type="image_url", image_url=dict(url="data:image/png;base64," + "x"*500000))]
        with patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(agent, "consume_key", return_value="synthetic-secret"), patch.object(agent, "image_parts", return_value=parts), patch.object(agent, "request_response_stream", new=AsyncMock(return_value=response)) as send:
            result = await agent.AgentRequest().request(profile, dict(instructions="Inspect", input=[], tools=[]), image)
        self.assertEqual(result[0]["status"], "complete")
        self.assertEqual(send.await_count, 1)
        self.assertEqual(send.call_args.args[2]["input"][-1]["content"][1]["type"], "input_image")

    async def test_tool_parallel_parameter_only_when_advertised(self):
        profile = agent.AgentProfile().configure("test/tools", "SYNTHETIC_KEY", "Auto", "medium", 1000, 64000, 30)[0]
        caps = dict(parameters={"tools": {}}, endpoints=[dict(id="test", context_length=128000, parameters=["tools"])])
        request = dict(instructions="Use one tool.", input=[], tools=[dict(type="function", name="check", parameters={"type":"object"})])
        response = dict(status="completed", output=[dict(type="message", content=[dict(type="output_text", text="OK")])])
        for supported in (False, True):
            if supported:
                caps["endpoints"][0]["parameters"].append("parallel_tool_calls")
            with patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(agent, "consume_key", return_value="synthetic-secret"), patch.object(agent, "request_response_stream", new=AsyncMock(return_value=response)) as send:
                result = await agent.AgentRequest().request(profile, request)
            self.assertEqual(result[0]["status"], "complete")
            body = send.call_args.args[2]
            self.assertEqual("parallel_tool_calls" in body, supported)
            self.assertTrue(body["provider"]["require_parameters"])
            if supported:
                self.assertIs(body["parallel_tool_calls"], False)

    async def test_access_and_configuration_errors_cannot_trigger_provider_retry(self):
        profile = agent.AgentProfile().configure("test/tools", "SYNTHETIC_KEY", "Auto", "medium", 1000, 64000, 30)[0]
        caps = dict(parameters={}, endpoints=[dict(id="test", context_length=128000)])
        for status in (0, 401, 402, 403, 404):
            with self.subTest(status=status), patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(agent, "consume_key", return_value="synthetic-secret"), patch.object(agent, "request_response_stream", new=AsyncMock(side_effect=service.ProviderHTTPError(status, "Cannot use endpoint"))) as send:
                result = await agent.AgentRequest().request(profile, dict(instructions="Test", input=[], tools=[]))
            self.assertEqual(result[0]["code"], "provider_configuration")
            self.assertFalse(result[0]["retryable"])
            self.assertEqual(send.await_count, 1)

    async def test_nonvision_model_or_oversized_sheet_never_sends_request(self):
        import torch
        profile = agent.AgentProfile().configure("test/no-vision", "SYNTHETIC_KEY", "Auto", "medium", 1000, 64000, 30)[0]
        caps = dict(parameters={}, endpoints=[dict(id="test", context_length=128000)], input_modalities=["text"])
        with patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(agent, "request_response_stream", new=AsyncMock()) as send:
            result = await agent.AgentRequest().request(profile, dict(instructions="Inspect", input=[], tools=[]), torch.zeros((1,32,32,3)))
        self.assertEqual(result[0]["status"], "failure")
        send.assert_not_called()
        caps["input_modalities"].append("image")
        with patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(agent, "request_response_stream", new=AsyncMock()) as send:
            result = await agent.AgentRequest().request(profile, dict(instructions="Inspect", input=[], tools=[]), torch.empty((2,32,32,3)))
        self.assertEqual(result[0]["status"], "failure")
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
