"""Routing compatibility, endpoint limits and mocked discovery (no inference)."""
import copy
import unittest
from unittest.mock import AsyncMock, patch
from test_providers import n, s
from rm_test.routing import resolve_route, endpoint_capabilities


def capabilities():
    return {"provider": "OpenRouter", "input_modalities": ["text"],
            "parameters": {"temperature": {"type": "number"}, "top_p": {"type": "number"}},
            "endpoints": [
                {"id": "azure", "parameters": ["temperature"], "context_length": 10000, "max_tokens": 1000},
                {"id": "azure/region", "parameters": ["temperature", "top_p"], "context_length": 8000, "max_tokens": 900},
                {"id": "openai", "parameters": ["top_p"], "context_length": 20000, "max_tokens": 2000}]}


class Routing(unittest.TestCase):
    def test_legacy_and_direct(self):
        self.assertEqual(resolve_route("", "OpenRouter", endpoint="azure"), ("OpenRouter", "azure"))
        self.assertEqual(resolve_route("", "Featherless"), ("Featherless", "Auto"))
        self.assertEqual(resolve_route("Direct", "OpenAI", "azure"), ("OpenAI", "Auto"))
        self.assertEqual(resolve_route("OpenRouter", "OpenAI", "azure"), ("OpenRouter", "azure"))
        for router, provider in [("Direct", "OpenRouter"), ("bad", "OpenAI")]:
            with self.assertRaises(s.RMError): resolve_route(router, provider)

    def test_selected_host_limits_and_controls(self):
        caps = capabilities(); original = copy.deepcopy(caps)
        selected = endpoint_capabilities(caps, "azure")
        self.assertEqual(set(selected["parameters"]), {"temperature"})
        self.assertEqual(selected["endpoints"][0]["max_tokens"], 900)
        self.assertEqual(selected["endpoints"][0]["context_length"], 8000)
        self.assertEqual(caps, original)
        self.assertIs(endpoint_capabilities(caps, "Auto"), caps)
        with self.assertRaises(s.RMError): endpoint_capabilities(caps, "absent")

    def test_provider_is_enforced_in_payload(self):
        caps = endpoint_capabilities(capabilities(), "azure")
        body = n.build_body("OpenRouter", "test/model", "azure", caps, "system", "user", {"temperature": .5})
        self.assertEqual(body["provider"], {"require_parameters": True, "only": ["azure"], "allow_fallbacks": False})
        with self.assertRaises(s.RMError):
            n.build_body("OpenRouter", "test/model", "azure", caps, "system", "user", {"top_p": .9})

    def test_inputs_append_without_reordering_existing_widgets(self):
        schema = n.RMLLM050.INPUT_TYPES()
        self.assertEqual(list(schema["optional"])[-2:], ["router", "hosting_provider"])
        self.assertEqual(schema["optional"]["router"][1]["default"], "")


class Discovery(unittest.IsolatedAsyncioTestCase):
    async def test_provider_first_filter_and_cache(self):
        s.ROUTING_CACHE.clear()
        with patch.object(s, "request_json", AsyncMock(side_effect=[
            {"data": [{"slug": "google-vertex", "name": "Google Vertex"}]},
            {"data": [{"id": "test/model", "name": "Test", "architecture": {"output_modalities": ["text"]}}]},
        ])) as request:
            providers = await s.routing_catalog()
            self.assertEqual(providers["providers"][0]["id"], "google-vertex")
            models = await s.routing_catalog("google-vertex")
            self.assertEqual(models["models"][0]["id"], "test/model")
            self.assertIn("providers=Google%20Vertex", request.call_args.args[0])
            self.assertEqual(await s.routing_catalog("google-vertex"), models)
            self.assertEqual(request.await_count, 2)
        s.ROUTING_CACHE.clear()

    async def test_node_routes_before_credentials(self):
        args = dict(provider="OpenAI", model_name="test/model", endpoint="Auto", api_key_env="OPENAI_API_KEY",
                    credential_source="Environment variable", system_prompt="s", user_prompt="u", parameters_json="{}", timeout_seconds=30)
        response = {"choices": [{"message": {"content": "answer"}}]}
        with patch.object(n, "consume_key", return_value="dummy") as key, \
             patch.object(n, "model_capabilities", AsyncMock(return_value=capabilities())), \
             patch.object(n, "request_completion", AsyncMock(return_value=response)) as complete:
            result = await n.RMLLM050().generate(**args, router="OpenRouter", hosting_provider="azure")
            self.assertEqual(key.call_args.args, ("OpenRouter", "", "OPENROUTER_API_KEY"))
            self.assertEqual(complete.call_args.args[3]["provider"]["only"], ["azure"])
            self.assertEqual(result["ui"]["rm_llm_model"][0]["hosting_provider"], "azure")
