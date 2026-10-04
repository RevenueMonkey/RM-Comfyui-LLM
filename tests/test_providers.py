"""Offline contract tests. No server, real credentials or provider calls."""
import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


def stub(name, **values):
    module = types.ModuleType(name)
    module.__dict__.update(values)
    sys.modules[name] = module
    return module


# Standalone subprocess only. Real numerical/image libraries are kept intact.
stub("server", PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(
    routes=types.SimpleNamespace(post=lambda path: lambda handler: handler))))
stub("folder_paths")
management = stub("comfy.model_management", throw_exception_if_processing_interrupted=lambda: None)
stub("comfy", model_management=management)
stub("comfy_execution")
stub("comfy_execution.utils", get_executing_context=lambda: None)
stub("comfy_api")
stub("comfy_api.latest", VideoContainer=types.SimpleNamespace(MP4="mp4"), VideoCodec=types.SimpleNamespace(H264="h264"))
spec = importlib.util.spec_from_file_location("rm_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from rm_test import providers as p, provider_transport as t, service as s, node as n, streaming


def caps(provider, model="test", raw=None):
    return p.capabilities(provider, model, raw or {})


def body(model="test", **settings):
    return dict(model=model, messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "hello"}], stream=False, **settings)


class Content:
    def __init__(self, events):
        self.data = "".join("data: " + (e if isinstance(e, str) else json.dumps(e)) + "\n\n" for e in events).encode()

    async def iter_chunked(self, size):
        for start in range(0, len(self.data), 7):
            yield self.data[start:start + 7]


class Console:
    def __init__(self): self.items = []
    def write(self, channel, text):
        if text: self.items.append((channel, text))


class Contracts(unittest.TestCase):
    def test_import_registration(self):
        self.assertEqual(set(package.NODE_CLASS_MAPPINGS), {"RM_LLM_050", "RMLLMAgentProfile050", "RMLLMAgentRequest050"})
        self.assertEqual(len(s.PROVIDERS), 12)
        schema = n.RMLLM050.INPUT_TYPES()
        self.assertIn("thinking_config", schema["optional"])
        self.assertIn("reasoning.enabled", schema["optional"])

    def test_provider_credentials_and_ui_agree(self):
        js = (ROOT / "web/rm_llm.js").read_text(encoding="utf-8")
        for provider, (_, variable) in s.PROVIDERS.items():
            self.assertIn(provider, js)
            self.assertIn(variable, js)
            with patch.dict(s.os.environ, {variable: "dummy-test-secret"}):
                self.assertEqual(s.environment_key(provider), "dummy-test-secret")
        self.assertNotIn("Authorization", p.headers("Anthropic", "test"))
        self.assertNotIn("Authorization", p.headers("Google Gemini", "test"))
        self.assertEqual(p.headers("Anthropic", "test")["anthropic-version"], "2023-06-01")

    def test_session_key_is_provider_bound(self):
        token = s.store_session("OpenAI", "dummy-test-key")
        self.assertEqual(s.session_key("OpenAI", token), "dummy-test-key")
        with self.assertRaises(s.RMError): s.session_key("Groq", token)
        s.SESSIONS.clear()

    def test_each_new_provider_has_valid_basic_request(self):
        for provider in p.PROVIDERS:
            with self.subTest(provider=provider):
                c = caps(provider)
                b = n.build_body(provider, "test", "Auto", c, "system", "hello", {})
                url, result = t.translate(provider, b, c)
                self.assertTrue(url.startswith(p.PROVIDERS[provider][0]))
                self.assertNotIn("reasoning.enabled", result)

    def test_native_system_and_media(self):
        b = body()
        b["messages"][1]["content"] = [{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
        _, anthropic = t.translate("Anthropic", b, caps("Anthropic"))
        self.assertEqual(anthropic["system"], "system")
        self.assertEqual(anthropic["messages"][0]["content"][1]["source"]["data"], "AAAA")
        self.assertEqual(anthropic["max_tokens"], 4096)
        _, gemini = t.translate("Google Gemini", b, caps("Google Gemini"))
        self.assertEqual(gemini["systemInstruction"]["parts"][0]["text"], "system")
        self.assertEqual(gemini["contents"][0]["parts"][1]["inlineData"]["mimeType"], "image/png")

    def test_metadata_overrides_documented_vision(self):
        self.assertNotIn("image", caps("Anthropic", "claude-sonnet-4-5", {"capabilities": {"image_input": {"supported": False}}})["input_modalities"])
        self.assertNotIn("image", caps("Together AI", "unknown-VL-vision")["input_modalities"])
        self.assertIn("image", caps("Mistral AI", raw={"capabilities": {"vision": True}})["input_modalities"])
        self.assertIn("image", caps("Fireworks AI", raw={"supportsImageInput": True})["input_modalities"])
        self.assertIn("video", caps("Google Gemini", "gemini-2.5-flash")["input_modalities"])

    def test_incompatible_sampling_and_mandatory_thinking(self):
        c = caps("OpenAI", "o3")
        self.assertNotIn("temperature", c["parameters"])
        with self.assertRaises(s.RMError): n.validate_parameters({"reasoning": {"enabled": False}}, c, "Auto")
        with self.assertRaises(s.RMError): t.translate("Anthropic", body(temperature=.5, top_p=.9), caps("Anthropic"))
        with self.assertRaises(s.RMError): n.validate_parameters({"temperature": 1.5}, caps("Anthropic"), "Auto")

    def test_thinking_translation(self):
        c = caps("Anthropic", "claude-sonnet-4-5")
        _, out = t.translate("Anthropic", body(reasoning={"enabled": True}), c)
        self.assertEqual(out["thinking"], {"type": "enabled", "budget_tokens": 1024})
        with self.assertRaises(s.RMError): t.translate("Anthropic", body(max_tokens=1000, reasoning={"enabled": True}), c)
        c = caps("Anthropic", "new-model", {"capabilities": {"thinking": {"supported": True, "types": {"adaptive": {"supported": True}}}}})
        _, out = t.translate("Anthropic", body(reasoning={"enabled": True}), c)
        self.assertEqual(out["thinking"]["type"], "adaptive")
        c = caps("Google Gemini", "gemini-2.5-flash")
        _, out = t.translate("Google Gemini", body("gemini-2.5-flash", reasoning={"enabled": False}), c)
        self.assertEqual(out["generationConfig"]["thinkingConfig"]["thinkingBudget"], 0)
        _, out = t.translate("DeepSeek", body("deepseek-flash", reasoning={"enabled": False}), caps("DeepSeek", "deepseek-flash"))
        self.assertEqual(out["thinking"], {"type": "disabled"})
        _, out = t.translate("Together AI", body(reasoning={"enabled": True}), caps("Together AI", "Qwen/Qwen3.5-9B"))
        self.assertEqual(out["reasoning"], {"enabled": True})
        _, out = t.translate("Mistral AI", body(reasoning={"enabled": True}), caps("Mistral AI", "mistral-small-latest"))
        self.assertEqual(out["reasoning_effort"], "high")

    def test_normalized_tool_results_preserve_native(self):
        raw = {"content": [{"type": "thinking", "thinking": "think"}, {"type": "text", "text": "answer"}, {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": 1}}], "usage": {"output_tokens": 5}, "stop_reason": "tool_use"}
        result = t.normalize("Anthropic", raw)
        self.assertIs(result["provider_response"], raw)
        self.assertEqual(result["choices"][0]["message"]["reasoning"], "think")
        self.assertEqual(json.loads(result["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]), {"q": 1})

    def test_tool_translation(self):
        b = body(tools=[{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}], tool_choice="required")
        _, out = t.translate("Anthropic", b, caps("Anthropic"))
        self.assertEqual(out["tool_choice"], {"type": "any"})
        self.assertIn("input_schema", out["tools"][0])
        _, out = t.translate("Google Gemini", b, caps("Google Gemini"))
        self.assertEqual(out["toolConfig"]["functionCallingConfig"]["mode"], "ANY")

    def test_empty_settings_remain_omitted(self):
        for provider in p.PROVIDERS:
            _, out = t.translate(provider, body(), caps(provider))
            self.assertNotIn("temperature", out)
            self.assertNotIn("top_p", out)
            self.assertNotIn("reasoning", out)

    def test_fireworks_thinking_and_budget(self):
        c = caps("Fireworks AI", "accounts/fireworks/models/qwen3-235b", {"conversationConfig": {"style": "qwen3"}})
        _, out = t.translate("Fireworks AI", body(reasoning={"enabled": False}), c)
        self.assertEqual(out["reasoning_effort"], "none")
        _, out = t.translate("Fireworks AI", body(reasoning={"max_tokens": 2000}), c)
        self.assertEqual(out["reasoning_effort"], 2000)
        c = caps("Fireworks AI", "accounts/fireworks/models/gpt-oss-120b")
        with self.assertRaises(s.RMError): t.translate("Fireworks AI", body(reasoning={"enabled": False}), c)
        with self.assertRaises(s.RMError): t.translate("Fireworks AI", body(reasoning={"max_tokens": 2000}), c)

    def test_connected_reasoning_and_creativity_precedence(self):
        c = caps("DeepSeek", "deepseek-flash")
        result = n.merge_connected_parameters({"reasoning": {"effort": "high"}}, {"reasoning.enabled": False}, c)
        self.assertEqual(result["reasoning"], {"enabled": False})
        c = caps("Together AI")
        result = n.merge_connected_parameters(n.creativity_to_sampling(50), {"temperature": .8}, c)
        self.assertEqual(result["temperature"], .8)
        self.assertEqual(result["top_p"], .97)
        self.assertNotIn("image", caps("OpenAI", "o3-mini")["input_modalities"])


class AsyncContracts(unittest.IsolatedAsyncioTestCase):
    async def test_real_node_execution_all_providers_with_mock_http(self):
        options = {name: schema[1]["default"] for name, schema in n.RMLLM050.INPUT_TYPES()["required"].items()}
        options.update(model_name="test", user_prompt="hello")
        for provider in s.PROVIDERS:
            with self.subTest(provider=provider):
                c = caps(provider) if provider in p.PROVIDERS else {"provider": provider, "parameters": {}, "input_modalities": ["text"], "endpoints": []}
                native = {"content": [{"type": "text", "text": "answer"}], "stop_reason": "end_turn"} if provider == "Anthropic" else {"candidates": [{"content": {"parts": [{"text": "answer"}]}, "finishReason": "STOP"}]}
                compatible = {"choices": [{"message": {"content": "answer"}}]}
                with patch.object(n, "consume_key", return_value="dummy-secret"), patch.object(n, "model_capabilities", AsyncMock(return_value=c)), patch.object(t, "request_json", AsyncMock(return_value=native)), patch.object(n, "request_completion", AsyncMock(return_value=compatible)):
                    result = await n.RMLLM050().generate(**dict(options, provider=provider))
                self.assertEqual(result["result"][0], "answer")

    async def test_json_transport_headers_and_together_array(self):
        calls = []
        class Response:
            status = 200
            headers = {}
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            @property
            def content(self): return self
            async def iter_chunked(self, size): yield b'[{"id":"example"}]'
        class Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            def request(self, *a, **kw): calls.append((a, kw)); return Response()
        with patch.object(s.aiohttp, "ClientSession", Client):
            result = await s.request_json("https://api.together.ai/v1/models", "dummy", allow_list=True)
            self.assertEqual(result[0]["id"], "example")
            with self.assertRaises(s.RMError): await s.request_json("https://api.anthropic.com/v1/models", "dummy", extra_headers=p.headers("Anthropic", "dummy"))
        self.assertFalse(calls[0][1]["allow_redirects"])
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer dummy")
        self.assertNotIn("Authorization", calls[1][1]["headers"])
        self.assertEqual(calls[1][1]["headers"]["x-api-key"], "dummy")

    async def test_native_http_error_and_cancellation_propagate(self):
        with patch.object(t, "request_json", AsyncMock(side_effect=s.RMError("API Key Needed!"))):
            with self.assertRaisesRegex(s.RMError, "API Key Needed"):
                await t.complete("Anthropic", body(), caps("Anthropic"), "dummy", 30)
        with patch.object(t, "request_json", AsyncMock(side_effect=asyncio.CancelledError())):
            with self.assertRaises(asyncio.CancelledError):
                await t.complete("Google Gemini", body(), caps("Google Gemini"), "dummy", 30)

    async def test_fireworks_and_gemini_page_tokens(self):
        for provider, item in [("Fireworks AI", {"name": "accounts/fireworks/models/example", "supportsServerless": True}), ("Google Gemini", {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]})]:
            request = AsyncMock(side_effect=[{"models": [item], "nextPageToken": "next&evil=1"}, {"models": []}])
            result = await p.catalog(provider, "dummy", request, lambda *a, **kw: None)
            self.assertEqual(len(result), 1)
            self.assertIn("pageToken=next%26evil%3D1", request.call_args.args[0])

    async def test_gemini_video_and_json_mode(self):
        b = body("gemini-2.5-flash", response_format={"type": "json_schema", "json_schema": {"schema": {"type": "object"}}}, max_tokens=100)
        b["messages"][1]["content"] = [{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AAAA"}}]
        _, out = t.translate("Google Gemini", b, caps("Google Gemini", "gemini-2.5-flash"))
        self.assertEqual(out["contents"][0]["parts"][0]["inlineData"]["mimeType"], "video/mp4")
        self.assertEqual(out["generationConfig"]["maxOutputTokens"], 100)
        self.assertEqual(out["generationConfig"]["responseJsonSchema"], {"type": "object"})

    async def test_all_catalog_shapes(self):
        for provider in p.PROVIDERS:
            raw = {"id": "example", "type": "chat"}
            data = {"data": [raw]}
            if provider == "Together AI": data = [raw]
            if provider == "Google Gemini": data = {"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]}]}
            if provider == "xAI": data = {"models": [raw]}
            if provider == "Fireworks AI": data = {"models": [{"name": "accounts/fireworks/models/example", "supportsServerless": True}]}
            if provider == "OpenAI": data = {"data": [{"id": "gpt-4.1"}, {"id": "text-embedding-3-small"}]}
            request = AsyncMock(return_value=data)
            result = await p.catalog(provider, "test-key", request, lambda *a, **kw: None)
            self.assertEqual(len(result), 1, provider)
            self.assertNotIn("test-key", request.call_args.args[0])

    async def test_pagination_is_local_and_bounded(self):
        request = AsyncMock(side_effect=[{"data": [{"id": "a"}], "has_more": True, "last_id": "https://evil.invalid/key"}, {"data": [{"id": "b"}], "has_more": False}])
        result = await p.catalog("Anthropic", "test-key", request, lambda *a, **kw: None)
        self.assertEqual(len(result), 2)
        self.assertTrue(request.call_args.args[0].startswith("https://api.anthropic.com/v1/models?"))
        request = AsyncMock(return_value={"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]}], "nextPageToken": "same"})
        with self.assertRaises(s.RMError): await p.catalog("Google Gemini", "test-key", request, lambda *a, **kw: None)
        self.assertEqual(request.await_count, 2)

    async def test_manual_model_does_not_require_full_catalog(self):
        request = AsyncMock(return_value={"id": "manual-model"})
        catalog = AsyncMock(side_effect=s.RMError("unavailable"))
        result = await p.metadata("OpenAI", "gpt-4.1", "key", request, catalog)
        self.assertEqual(result["id"], "manual-model")
        catalog.assert_not_awaited()
        result = await p.metadata("Together AI", "manual-model", "key", request, catalog)
        self.assertEqual(result["id"], "manual-model")

    async def test_claude_stream(self):
        events = [{"type": "message_start", "message": {"id": "msg", "usage": {"input_tokens": 10}}}, {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}, {"type": "content_block_delta", "index": 0, "delta": {"thinking": "thought"}}, {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}, {"type": "content_block_delta", "index": 1, "delta": {"text": "answer"}}, {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 4}}, {"type": "message_stop"}]
        console = Console()
        raw = await t.read_native_stream("Anthropic", Content(events), "key", console)
        self.assertEqual(console.items, [("Reasoning", "thought"), ("Response", "answer")])
        self.assertEqual(raw["usage"], {"input_tokens": 10, "output_tokens": 4})
        with self.assertRaises(s.RMError): await t.read_native_stream("Anthropic", Content(events[:-1]), "key", Console())

    async def test_gemini_stream(self):
        events = [{"candidates": [{"index": 0, "content": {"parts": [{"text": "thought", "thought": True}]}}]}, {"candidates": [{"index": 0, "content": {"parts": [{"text": "answer"}]}, "finishReason": "STOP"}]}, {"usageMetadata": {"totalTokenCount": 12}}]
        console = Console()
        raw = await t.read_native_stream("Google Gemini", Content(events), "key", console)
        result = t.normalize("Google Gemini", raw)
        self.assertEqual(result["choices"][0]["message"]["content"], "answer")
        self.assertEqual(result["choices"][0]["message"]["reasoning"], "thought")
        self.assertEqual(result["usage"]["totalTokenCount"], 12)
        with self.assertRaises(s.RMError): await t.read_native_stream("Google Gemini", Content(events[:1]), "key", Console())

    async def test_mistral_stream_preserves_thinking(self):
        content = [{"type": "thinking", "thinking": [{"type": "text", "text": "thought"}]}, {"type": "text", "text": "answer"}]
        console = Console()
        result = await streaming.read_completion_stream(Content([{"choices": [{"index": 0, "delta": {"content": content}}]}, "[DONE]"]), "key", console)
        result = t.normalize("Mistral AI", result)
        self.assertEqual(result["choices"][0]["message"]["reasoning"], "thought")
        self.assertIn(("Reasoning", "thought"), console.items)

    async def test_missing_key_never_requests_catalog(self):
        request = AsyncMock()
        with self.assertRaisesRegex(s.RMError, "API Key Needed"):
            await p.catalog("OpenAI", "", request, lambda *a, **kw: None)
        request.assert_not_awaited()

    async def test_native_nonstream_http_headers(self):
        raw = {"content": [{"type": "text", "text": "answer"}], "stop_reason": "end_turn"}
        with patch.object(t, "request_json", AsyncMock(return_value=raw)) as request:
            result = await t.complete("Anthropic", body(), caps("Anthropic"), "dummy-key", 30)
            self.assertEqual(request.call_args.kwargs["extra_headers"]["x-api-key"], "dummy-key")
            self.assertEqual(result["choices"][0]["message"]["content"], "answer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
