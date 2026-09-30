import json
import math
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rm_llm import node, service
from rm_llm.node_v2 import RMLLMV2, creativity_to_sampling
from rm_llm.node_v3 import RMLLMV3
from rm_llm import node_v2
from comfy_execution.utils import CurrentNodeContext


class Sampling(unittest.IsolatedAsyncioTestCase):
    def test_v3_registration_contract(self):
        self.assertEqual(RMLLMV3.INPUT_TYPES()["required"]["provider"][1]["default"], "OpenRouter")
        self.assertEqual(service.PROVIDERS["LithosAI"], ("https://api.lithosai.cloud/v1", "LITHOSAI_API_KEY"))

    async def test_lithosai_catalog_and_capabilities(self):
        async def response(url, key="", body=None, timeout=45):
            if url.endswith("/models"):
                return {"object": "list", "data": [{"id": "moonshotai/Kimi-K3", "object": "model", "created": 1, "owned_by": "Moonshot AI"}]}
            self.assertEqual(url, "https://api.lithosai.cloud/v1/models/moonshotai/Kimi-K3")
            return {"id": "moonshotai/Kimi-K3", "object": "model", "created": 1, "owned_by": "Moonshot AI"}
        with patch.object(service, "request_json", new=AsyncMock(side_effect=response)):
            catalog = await service.fetch_catalog("LithosAI", "synthetic-key")
            caps = await service.model_capabilities("LithosAI", "moonshotai/Kimi-K3", refresh=True)
        self.assertEqual(catalog[0]["id"], "moonshotai/Kimi-K3")
        self.assertEqual(caps["input_modalities"], ["text"])
        self.assertEqual(caps["endpoints"][0]["id"], "LithosAI")
        self.assertIn("reasoning_effort", caps["parameters"])
    async def test_runtime_model_ui_event_and_cached_metadata(self):
        server = types.SimpleNamespace(client_id="browser", send_sync=Mock())
        dynprompt = types.SimpleNamespace(get_display_node_id=Mock(return_value="271:445"))
        async def generate(**kwargs):
            self.assertNotIn("dynprompt", kwargs)
            server.send_sync.assert_called_once()
            return {"ui": {"text": ["story"]}, "result": ("story", "", "{}")}
        with patch.object(node_v2.PromptServer, "instance", server), patch.object(node.RMLLM, "generate", new=AsyncMock(side_effect=generate)):
            with CurrentNodeContext("job", "loop.445"):
                result = await RMLLMV2().generate(parameters_json="{}", provider="OpenRouter",
                    model_name="synthetic/connected", dynprompt=dynprompt)
        info = {"provider": "OpenRouter", "model": "synthetic/connected"}
        server.send_sync.assert_called_once_with("rm-llm-model", {"node": "271:445", "model_info": info}, "browser")
        dynprompt.get_display_node_id.assert_called_once_with("loop.445")
        self.assertEqual(result["ui"]["rm_llm_model"], [info])
        self.assertEqual(result["result"], ("story", "", "{}"))

    async def test_openrouter_reasoning_metadata(self):
        options = {"mandatory": False, "default_enabled": True, "supported_efforts": ["max", "high", "low"], "default_effort": "max"}
        endpoint = {"data": {"architecture": {"input_modalities": ["text"]}, "endpoints": [{"tag": "test", "supported_parameters": ["reasoning", "reasoning_effort"]}]}}
        with patch.object(service, "request_json", new=AsyncMock(side_effect=[endpoint, {"data": [{"id": "synthetic/reasoning", "reasoning": options}]}])):
            caps = await service.model_capabilities("OpenRouter", "synthetic/reasoning", refresh=True)
        self.assertEqual(caps["reasoning_options"], options)

    def test_reasoning_toggle_merge_and_mandatory_guard(self):
        caps = {"provider": "OpenRouter", "parameters": {"reasoning": {"type": "object"}, "reasoning_effort": {"type": "string"}}, "endpoints": [], "reasoning_options": {"mandatory": False}}
        saved = {"reasoning": {"effort": "high", "exclude": True, "max_tokens": 1000}, "reasoning_effort": "high"}
        result = node.merge_connected_parameters(saved, {"reasoning.enabled": False}, caps)
        self.assertEqual(result, {"reasoning": {"enabled": False, "exclude": True}})
        self.assertEqual(saved["reasoning"]["effort"], "high")
        result = node.merge_connected_parameters({}, {"reasoning": '{"exclude":true,"effort":"none"}', "reasoning.enabled": True}, caps)
        self.assertEqual(result, {"reasoning": {"enabled": True, "exclude": True}})
        caps["reasoning_options"]["mandatory"] = True
        for settings in [{"reasoning": {"enabled": False}}, {"reasoning": {"effort": "none"}}, {"reasoning_effort": "none"}]:
            with self.assertRaises(service.RMError):
                node.validate_parameters(settings, caps, "Auto")
        with self.assertRaises(service.RMError):
            node.merge_connected_parameters({}, {"reasoning.enabled": "false"}, caps)
        caps["provider"] = "Featherless"
        with self.assertRaises(service.RMError):
            node.merge_connected_parameters({}, {"reasoning.enabled": True}, caps)

    def test_curve_and_clamping(self):
        for c, temperature, top_p in [(0, .2, .9), (50, .49, .97), (100, 1.2, .99)]:
            pair = creativity_to_sampling(c)
            self.assertAlmostEqual(pair["temperature"], temperature)
            self.assertAlmostEqual(pair["top_p"], top_p)
        self.assertEqual(creativity_to_sampling(-20), creativity_to_sampling(0))
        self.assertEqual(creativity_to_sampling(120), creativity_to_sampling(100))
        for invalid in [True, "50", float("nan"), float("inf")]:
            with self.assertRaises(service.RMError):
                creativity_to_sampling(invalid)

    async def test_omission_and_explicit_creativity(self):
        with patch.object(node.RMLLM, "generate", new_callable=AsyncMock) as base:
            await RMLLMV2().generate(parameters_json='{"top_p":0.8}')
            self.assertEqual(base.call_args.kwargs["parameters_json"], '{"top_p":0.8}')
            await RMLLMV2().generate(parameters_json='{"seed":1}', creativity=100, temperature=.7)
            params = json.loads(base.call_args.kwargs["parameters_json"])
            self.assertAlmostEqual(params["temperature"], 1.2)
            self.assertEqual(params["seed"], 1)
            self.assertEqual(base.call_args.kwargs["temperature"], .7)
            caps = {"parameters": {"temperature": {"type": "number"}, "top_p": {"type": "number"}}}
            merged = node.merge_connected_parameters(params, {"temperature": .7}, caps)
            self.assertEqual(merged["temperature"], .7)
            self.assertAlmostEqual(merged["top_p"], .99)
            with self.assertRaises(service.RMError):
                await RMLLMV2().generate(parameters_json='[]', creativity=50)

    def test_schema_preserves_original_node(self):
        self.assertNotIn("creativity", node.RMLLM.INPUT_TYPES()["optional"])
        self.assertEqual(RMLLMV2.INPUT_TYPES()["optional"]["creativity"][0], "FLOAT")

    async def test_generation_payload_and_unsupported_sampling(self):
        caps = {"input_modalities": ["text"], "parameters": {"temperature": {"type": "number"}, "top_p": {"type": "number"}}, "endpoints": []}
        arguments = dict(provider="Featherless", model_name="synthetic/test", endpoint="Auto", api_key_env="", credential_source="Environment variable", system_prompt="sys", user_prompt="user", parameters_json="{}", timeout_seconds=30, creativity=50, temperature=.8)
        response = {"choices": [{"message": {"content": "Synthetic response"}}]}
        with patch.object(node, "consume_key", return_value="synthetic-secret"), patch.object(node, "model_capabilities", new=AsyncMock(return_value=caps)), patch.object(node, "request_completion", new=AsyncMock(return_value=response)) as request:
            result = await RMLLMV2().generate(**arguments)
            body = request.call_args.args[3]
            self.assertNotIn("creativity", body)
            self.assertEqual(body["temperature"], .8)
            self.assertEqual(body["top_p"], .97)
            self.assertEqual(result["result"][0], "Synthetic response")
            del caps["parameters"]["top_p"]
            with self.assertRaises(service.RMError):
                await RMLLMV2().generate(**arguments)
            self.assertEqual(request.await_count, 1)


if __name__ == "__main__":
    unittest.main()
