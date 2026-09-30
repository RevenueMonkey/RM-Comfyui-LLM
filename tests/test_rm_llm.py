"""Run with the portable Python. Uses synthetic credentials and no paid API calls."""
import asyncio
import base64
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
server = types.ModuleType("server")
server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=types.SimpleNamespace(post=lambda path: lambda f: f)))
sys.modules["server"] = server
spec = importlib.util.spec_from_file_location("rm_llm", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules["rm_llm"] = package
spec.loader.exec_module(package)
from rm_llm import service, node, streaming, template_options
import torch
import av
from PIL import Image
from comfy_api.latest import InputImpl, VideoComponents


def capabilities():
    return {"input_modalities": ["text", "image", "video"], "parameters": {"temperature": {"type": "number"}, "max_tokens": {"type": "integer"}, "reasoning": {"type": "object"}}, "endpoints": [{"id": "host/a", "parameters": ["temperature", "max_tokens"], "max_tokens": 100}, {"id": "host/b", "parameters": ["reasoning"], "max_tokens": 200}]}


class Credentials(unittest.TestCase):
    def setUp(self):
        service.SESSIONS.clear()
        service.TICKETS.clear()

    def test_single_use_ticket_bound_to_provider(self):
        session = service.store_session("OpenRouter", "synthetic-secret")
        with self.assertRaises(service.RMError):
            service.issue_ticket("Featherless", session)
        ticket = service.issue_ticket("OpenRouter", session)
        self.assertEqual(service.consume_key("OpenRouter", ticket, ""), "synthetic-secret")
        with self.assertRaises(service.RMError):
            service.consume_key("OpenRouter", ticket, "")

    def test_expired_sessions(self):
        session = service.store_session("OpenRouter", "synthetic-secret")
        with patch.object(service.time, "monotonic", return_value=service.time.monotonic() + service.SESSION_TTL + 1):
            with self.assertRaises(service.RMError):
                service.issue_ticket("OpenRouter", session)

    def test_environment_lookup_and_missing_name(self):
        with patch.dict(os.environ, {"RM_TEST_API_KEY": "synthetic-secret"}):
            self.assertEqual(service.environment_key("OpenRouter", "RM_TEST_API_KEY"), "synthetic-secret")
        with self.assertRaises(service.RMError):
            service.environment_key("OpenRouter", "not-an-env-name")


class Payloads(unittest.TestCase):
    def test_rejected_system_role_preserves_both_prompts_and_media(self):
        caps = capabilities()
        caps["system_role_rejected"] = True
        body = node.build_body("Featherless", "test", "Auto", caps, "System instructions", "User request", {})
        self.assertEqual(body["messages"], [{"role": "user", "content": "System instructions\n\nUser request"}])
        body = node.build_body("Featherless", "test", "Auto", caps, "System instructions", "User request", {}, image=torch.zeros((1, 4, 4, 3)))
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["content"][0]["text"], "System instructions\n\nUser request")
        self.assertEqual(body["messages"][0]["content"][1]["type"], "image_url")
        for provider, rejected in [("Featherless", False), ("OpenRouter", True)]:
            caps["system_role_rejected"] = rejected
            body = node.build_body(provider, "test", "Auto", caps, "System instructions", "User request", {})
            self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        caps["system_role_rejected"] = True
        body = node.build_body("Featherless", "test", "Auto", caps, "", "User request", {})
        self.assertEqual(body["messages"], [{"role": "user", "content": "User request"}])

    def test_model_settings_have_typed_comfyui_sockets(self):
        inputs = node.RMLLM.INPUT_TYPES()
        for name, kind in {"temperature": "FLOAT", "top_k": "INT", "seed": "INT", "include_reasoning": "BOOLEAN", "reasoning": "STRING", "tools": "STRING"}.items():
            self.assertEqual(inputs["optional"][name][0], kind)
            self.assertTrue(inputs["optional"][name][1]["forceInput"])
        self.assertEqual(inputs["required"]["provider"][0], "STRING")

    def test_connected_parameters_take_precedence_and_parse_json(self):
        caps = capabilities()
        merged = node.merge_connected_parameters({"temperature": 0.2}, {"temperature": 0.9, "reasoning": '{"effort":"high"}'}, caps)
        self.assertEqual(merged, {"temperature": 0.9, "reasoning": {"effort": "high"}})
        with self.assertRaisesRegex(service.RMError, "unsupported"):
            node.merge_connected_parameters({}, {"invented": 1}, caps)
        with self.assertRaisesRegex(service.RMError, "valid JSON"):
            node.merge_connected_parameters({}, {"reasoning": "bad JSON"}, caps)

    def test_system_user_and_exact_provider_routing(self):
        body = node.build_body("OpenRouter", "model/a", "host/a", capabilities(), "system", "user", {"temperature": 0})
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        self.assertEqual(body["provider"], {"only": ["host/a"], "allow_fallbacks": False, "require_parameters": True})
        self.assertEqual(body["temperature"], 0)

    def test_endpoint_specific_parameters_and_token_limits(self):
        for params in [{"reasoning": {}}, {"max_tokens": 101}, {"temperature": True}, {"model": "other"}, {"temperature": float("nan")}]:
            with self.subTest(params=params), self.assertRaises(service.RMError):
                node.validate_parameters(params, capabilities(), "host/a")

    def test_image_batch_is_preserved(self):
        images = torch.zeros((2, 4, 4, 3))
        images[1] = 1
        body = node.build_body("OpenRouter", "model/a", "Auto", capabilities(), "", "describe", {}, image=images)
        content = body["messages"][0]["content"]
        self.assertEqual(len(content), 3)
        pixels = []
        for part in content[1:]:
            encoded = part["image_url"]["url"].split(",", 1)[1]
            pixels.append(Image.open(io.BytesIO(base64.b64decode(encoded))).getpixel((0, 0)))
        self.assertEqual(pixels, [(0, 0, 0), (255, 255, 255)])

    def test_native_video_encoding(self):
        video = InputImpl.VideoFromComponents(VideoComponents(images=torch.zeros((3, 16, 16, 3)), frame_rate=Fraction(3, 1)))
        part = node.video_part(video)
        data = base64.b64decode(part["video_url"]["url"].split(",", 1)[1])
        with av.open(io.BytesIO(data)) as container:
            self.assertEqual(len(list(container.decode(video=0))), 3)

    def test_unsupported_media_is_rejected_before_encoding(self):
        caps = capabilities()
        caps["input_modalities"] = ["text"]
        with self.assertRaises(service.RMError):
            node.build_body("OpenRouter", "model/a", "Auto", caps, "", "", {}, image=object())
        with self.assertRaises(service.RMError):
            node.build_body("Featherless", "model/a", "Auto", capabilities(), "", "", {}, video=object())

    def test_media_size_boundary(self):
        with patch.object(node, "MEDIA_LIMIT", 5), self.assertRaises(service.RMError):
            node.LimitedBuffer().write(b"123456")


class ProviderErrors(unittest.TestCase):
    def test_error_detail_redacts_key_and_control_characters(self):
        key = 'synthetic-"secret'
        raw = json.dumps({"error": {"message": f"No valid executor. {key}\n", "code": "no_executor"}}).encode()
        error = service.provider_error(503, raw, key, "12")
        self.assertIn("No valid executor", str(error))
        self.assertIn("no_executor", str(error))
        self.assertNotIn(key, str(error))
        self.assertNotIn("\n", str(error))
        self.assertEqual(error.status, 503)
        self.assertEqual(error.retry_after, 12)

    def test_html_errors_are_not_dumped(self):
        error = service.provider_error(503, b"<html>internal-header-secret</html>")
        self.assertNotIn("internal-header-secret", str(error))
        self.assertIn("capacity", str(error))


class Discovery(unittest.IsolatedAsyncioTestCase):
    async def test_console_switch_selects_streaming_transport(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch.object(node, "consume_key", return_value="synthetic-secret"), patch.object(node, "model_capabilities", new=AsyncMock(return_value=capabilities())), patch.object(node, "request_json", new=AsyncMock(return_value=response)) as regular, patch.object(node, "request_stream", new=AsyncMock(return_value=response)) as live, patch.object(node.logging, "info") as log:
                result = await node.RMLLM().generate("OpenRouter", "model/a", "Auto", "", "Environment variable", "sys", "user", "{}", 30, console_output=enabled)
                request, unused = (live, regular) if enabled else (regular, live)
                self.assertEqual(request.await_count, 1)
                unused.assert_not_awaited()
                self.assertEqual(request.await_args.args[2]["stream"], enabled)
                self.assertNotIn("console_output", request.await_args.args[2])
                self.assertEqual(result["result"][0], "ok")
                if not enabled:
                    log.assert_not_called()

    async def test_connected_inputs_reach_api_payload(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.object(node, "consume_key", return_value="synthetic-secret"), patch.object(node, "model_capabilities", new=AsyncMock(return_value=capabilities())), patch.object(node, "request_json", new=AsyncMock(return_value=response)) as request:
            await node.RMLLM().generate("OpenRouter", "model/a", "Auto", "", "Environment variable", "connected system", "connected user", '{"temperature":0.2}', 30, temperature=0.9, reasoning='{"effort":"high"}')
        body = request.await_args.args[2]
        self.assertEqual(body["temperature"], 0.9)
        self.assertEqual(body["reasoning"], {"effort": "high"})
        self.assertEqual(body["messages"], [{"role": "system", "content": "connected system"}, {"role": "user", "content": "connected user"}])

    async def test_capacity_retry_then_success(self):
        error = service.ProviderHTTPError(503, "No valid executor", retry_after=7)
        result = {"choices": []}
        with patch.object(node, "request_json", new=AsyncMock(side_effect=[error, result])) as request, patch.object(node.asyncio, "sleep", new=AsyncMock()) as sleep:
            actual = await node.request_completion("Featherless", "url", "synthetic", {"model": "test"}, 300)
        self.assertEqual(actual, result)
        self.assertEqual(request.await_count, 2)
        sleep.assert_awaited_once_with(7)

    async def test_capacity_retries_are_bounded(self):
        error = service.ProviderHTTPError(503, "No valid executor")
        with patch.object(node, "request_json", new=AsyncMock(side_effect=error)) as request, patch.object(node.asyncio, "sleep", new=AsyncMock()) as sleep:
            with self.assertRaisesRegex(service.RMError, "after 4 attempts"):
                await node.request_completion("Featherless", "url", "synthetic", {"model": "test"}, 300)
        self.assertEqual(request.await_count, 4)
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [5, 10, 20])

    async def test_authentication_errors_are_not_retried(self):
        error = service.ProviderHTTPError(401, "Invalid key")
        with patch.object(node, "request_json", new=AsyncMock(side_effect=error)) as request:
            with self.assertRaises(service.ProviderHTTPError):
                await node.request_completion("Featherless", "url", "synthetic", {"model": "test"}, 300)
        self.assertEqual(request.await_count, 1)

    async def test_retry_after_cannot_exceed_request_deadline(self):
        error = service.ProviderHTTPError(503, "Busy", retry_after=600)
        with patch.object(node, "request_json", new=AsyncMock(side_effect=error)) as request, patch.object(node.asyncio, "sleep", new=AsyncMock()) as sleep:
            with self.assertRaisesRegex(service.RMError, "no time"):
                await node.request_completion("Featherless", "url", "synthetic", {"model": "test"}, 300)
        self.assertEqual(request.await_count, 1)
        sleep.assert_not_awaited()

    async def test_featherless_short_pages_do_not_truncate_catalog(self):
        async def response(url, key=""):
            page = int(url.split("page=")[1].split("&")[0])
            return {"data": [{"id": f"model/{page}"}], "pagination": {"current_page": page, "total_pages": 3, "per_page": 1000}}
        with patch.object(service, "request_json", side_effect=response):
            models = await service.fetch_catalog("Featherless")
        self.assertEqual([m["id"] for m in models], ["model/1", "model/2", "model/3"])

    async def test_openrouter_pagination_cannot_redirect_keys(self):
        response = {"data": [{"id": "model/a"}], "links": {"next": "https://example.invalid/steal"}}
        with patch.object(service, "request_json", return_value=response), self.assertRaises(service.RMError):
            await service.fetch_catalog("OpenRouter", "synthetic-secret")

    async def test_featherless_vision_flag_overrides_incomplete_modalities(self):
        raw = {"id": "model/a", "input_modalities": ["text"], "features": {"image_input": True}}
        with patch.object(service, "request_json", return_value=raw), patch.object(service, "discover_template_options", new=AsyncMock(return_value=({}, "test", False))):
            caps = await service.model_capabilities("Featherless", "model/a", refresh=True)
        self.assertIn("image", caps["input_modalities"])
        self.assertNotIn("video", caps["input_modalities"])

    async def test_generate_redacts_secrets_and_preserves_tool_calls(self):
        response = {"choices": [{"message": {"content": "synthetic-secret", "reasoning_content": "synthetic-secret", "tool_calls": [{"id": "call1"}]}}]}
        with patch.object(node, "consume_key", return_value="synthetic-secret"), patch.object(node, "model_capabilities", new=AsyncMock(return_value=capabilities())), patch.object(node, "request_json", new=AsyncMock(return_value=response)):
            result = await node.RMLLM().generate("OpenRouter", "model/a", "Auto", "", "Environment variable", "sys", "user", "{}", 30)
        self.assertNotIn("synthetic-secret", json.dumps(result))
        self.assertIn("tool_calls", result["result"][2])

    async def test_cancellation_closes_pending_request(self):
        closed = asyncio.Event()
        async def pending():
            try:
                await asyncio.sleep(10)
            finally:
                closed.set()
        task = asyncio.create_task(node.interruptible(pending()))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(closed.is_set())


class TemplateOptions(unittest.IsolatedAsyncioTestCase):
    def test_system_rejection_requires_direct_template_guard(self):
        guard = "{% if messages[0]['role'] == 'system' %}{{ raise_exception('System role not supported') }}{% endif %}"
        self.assertTrue(template_options.rejects_system_role(guard))
        for template in ["System role not supported", "{{ raise_exception('unrelated') }}", guard.replace("'system'", "'assistant'"), "{% if messages[0]['role'] == 'system' %}{{ messages[0]['content'] }}{% endif %}"]:
            self.assertFalse(template_options.rejects_system_role(template))

    async def test_discovery_carries_system_role_restriction(self):
        with patch.object(template_options, "fetch_template", new=AsyncMock(return_value=({}, "https://huggingface.co/test", True))):
            fields, note, rejected = await template_options.discover_template_options("Featherless", "owner/model", {}, {})
        self.assertTrue(rejected)
        self.assertIn("prepended", note)
        self.assertFalse(fields)

    def test_template_inspection_is_typed_and_does_not_render(self):
        fields = template_options.inspect_template('{{ raise_exception("never execute") }}{% if enable_thinking %}yes{% endif %}{{ thinking_budget }}{{ date_string }}{{ custom_count | default(3) }}{{ custom_flag | default(false) }}{{ messages }}{{ bos_token }}')
        self.assertEqual(fields["enable_thinking"]["type"], "boolean")
        self.assertEqual(fields["thinking_budget"]["type"], "integer")
        self.assertEqual(fields["custom_count"]["type"], "integer")
        self.assertEqual(fields["custom_flag"]["type"], "boolean")
        self.assertNotIn("messages", fields)
        self.assertNotIn("bos_token", fields)

    async def test_model_family_fallback_does_not_invent_budget_or_unknown_options(self):
        record = service.read_records()["Featherless"]
        with patch.object(template_options, "fetch_template", new=AsyncMock(return_value=(None, "", False))):
            gemma, _, _ = await template_options.discover_template_options("Featherless", "owner/gemma-4-31B", {}, record)
            qwen, _, _ = await template_options.discover_template_options("Featherless", "owner/qwen3.5-27B", {}, record)
            unknown, _, _ = await template_options.discover_template_options("Featherless", "owner/unknown", {}, record)
            fixed, _, _ = await template_options.discover_template_options("Featherless", "owner/Qwen3-4B-Thinking-2507", {}, record)
        self.assertEqual(set(gemma), {"enable_thinking"})
        self.assertIn("preserve_thinking", qwen)
        self.assertNotIn("thinking_budget", qwen)
        self.assertFalse(unknown)
        self.assertNotIn("enable_thinking", fixed)

    async def test_model_template_adds_specific_controls_and_openrouter_is_not_assumed(self):
        with patch.object(template_options, "fetch_template", new=AsyncMock(return_value=({"thinking_budget": template_options.FIELDS["thinking_budget"]}, "https://huggingface.co/test", False))) as fetch:
            fields, _, _ = await template_options.discover_template_options("Featherless", "owner/unknown", {}, {})
            self.assertEqual(fields["thinking_budget"]["type"], "integer")
            self.assertIn("public chat template", fields["thinking_budget"]["evidence"])
            before = fetch.await_count
            fields, _, _ = await template_options.discover_template_options("OpenRouter", "owner/unknown", {}, {})
            self.assertFalse(fields)
            self.assertEqual(before, fetch.await_count)

    def test_nested_inputs_merge_after_json_without_leaking_to_top_level(self):
        caps = capabilities()
        caps["parameters"]["chat_template_kwargs"] = {"type": "object"}
        caps["template_parameters"] = dict(template_options.FIELDS)
        params = node.merge_connected_parameters({"chat_template_kwargs": {"custom": "kept"}}, {"chat_template_kwargs": '{"custom":"connected","thinking":false}', "chat_template_kwargs.enable_thinking": True, "chat_template_kwargs.thinking_budget": 100}, caps)
        self.assertEqual(params, {"chat_template_kwargs": {"custom": "connected", "enable_thinking": True, "thinking_budget": 100}})
        body = node.build_body("Featherless", "test", "Auto", caps, "system", "user", params)
        self.assertEqual(body["chat_template_kwargs"]["enable_thinking"], True)
        self.assertNotIn("chat_template_kwargs.enable_thinking", body)
        for kwargs in ({"enable_thinking": "false"}, {"thinking_budget": -1}):
            with self.assertRaises(service.RMError):
                node.validate_parameters({"chat_template_kwargs": kwargs}, caps, "Auto")
        with self.assertRaisesRegex(service.RMError, "not known"):
            node.merge_connected_parameters({}, {"chat_template_kwargs.not_supported": True}, caps)
        self.assertEqual(node.RMLLM.INPUT_TYPES()["optional"]["chat_template_kwargs.enable_thinking"][0], "BOOLEAN")


class LiveStreaming(unittest.IsolatedAsyncioTestCase):
    async def test_live_http_stream_prints_before_completion_and_assembles_metadata(self):
        first_sent, finish = asyncio.Event(), asyncio.Event()
        captured = {}

        async def handler(request):
            captured.update(await request.json())
            response = service.web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            async def event(delta, **extra):
                payload = {"id": "stream-test", "choices": [{"index": 0, "delta": delta, **extra}]}
                await response.write(("data: " + json.dumps(payload) + "\r\n\r\n").encode())
            await response.write(b": keepalive\r\n\r\n")
            await event({"reasoning_content": "Thinking now. "})
            await event({"content": "Hello "})
            first_sent.set()
            await finish.wait()
            await event({"content": "synthetic-"})
            await event({"content": "secret world."})
            await event({"tool_calls": [{"index": 0, "id": "call1", "type": "function", "function": {"name": "lookup", "arguments": '{"x":'}}]})
            await event({"tool_calls": [{"index": 0, "function": {"arguments": '1}'}}]}, finish_reason="tool_calls")
            await response.write(b'data: {"choices":[],"usage":{"total_tokens":12}}\n\ndata: [DONE]\n\n')
            return response

        app = service.web.Application()
        app.router.add_post("/chat/completions", handler)
        runner = service.web.AppRunner(app)
        await runner.setup()
        site = service.web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        output = io.StringIO()
        task = None
        try:
            with patch.object(streaming.sys, "stdout", output):
                task = asyncio.create_task(streaming.request_stream(f"http://127.0.0.1:{port}/chat/completions", "synthetic-secret", {"stream": True}, 5))
                await asyncio.wait_for(first_sent.wait(), 2)
                for _ in range(100):
                    if "Hello " in output.getvalue():
                        break
                    await asyncio.sleep(.01)
                self.assertIn("Hello ", output.getvalue())
                self.assertIn("Thinking now.", output.getvalue())
                self.assertFalse(task.done(), "Console must print while provider is still generating")
                finish.set()
                result = await task
            self.assertTrue(captured["stream"])
            self.assertNotIn("synthetic-secret", output.getvalue())
            self.assertIn("Hello [REDACTED] world.", output.getvalue())
            self.assertEqual(result["usage"]["total_tokens"], 12)
            message = result["choices"][0]["message"]
            self.assertEqual(message["content"], "Hello synthetic-secret world.")
            self.assertEqual(message["tool_calls"][0]["function"], {"name": "lookup", "arguments": '{"x":1}'})
        finally:
            finish.set()
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await runner.cleanup()

    async def test_sse_fragmented_utf8_multiline_data_and_reasoning_details(self):
        class Content:
            async def iter_chunked(self, size):
                payload = 'data: {"choices":[{"index":0,"delta":{"content":"café",\n' + 'data: "reasoning_details":[{"index":0,"type":"reasoning.text","text":"why"}]}}]}\n\ndata: [DONE]'
                for byte in payload.encode():
                    yield bytes([byte])
        output = io.StringIO()
        with patch.object(streaming.sys, "stdout", output):
            console = streaming.ConsoleStream("synthetic-secret")
            result = await streaming.read_completion_stream(Content(), "synthetic-secret", console)
            console.finish(True)
        self.assertIn("café", output.getvalue())
        self.assertEqual(result["choices"][0]["message"]["reasoning_details"][0]["text"], "why")

    async def test_midstream_error_and_truncation_do_not_retry(self):
        class Content:
            def __init__(self, tail):
                self.tail = tail
            async def iter_chunked(self, size):
                yield b'data: {"choices":[{"index":0,"delta":{"content":"partial"}}]}\n\n'
                yield self.tail
        for tail in (b'data: {"error":{"code":503,"message":"lost synthetic-secret"}}\n\n', b""):
            async def request(*args):
                return await streaming.read_completion_stream(Content(tail), "synthetic-secret", streaming.ConsoleStream("synthetic-secret"))
            with patch.object(node, "request_stream", new=AsyncMock(side_effect=request)) as live, patch.object(streaming.sys, "stdout", io.StringIO()):
                with self.assertRaises(service.RMError) as error:
                    await node.request_completion("Featherless", "url", "synthetic-secret", {"stream": True}, 5)
                self.assertEqual(live.await_count, 1)
                self.assertNotIn("synthetic-secret", str(error.exception))

    async def test_streaming_http_503_retries_before_output(self):
        failure = service.ProviderHTTPError(503, "capacity", 0)
        with patch.object(node, "request_stream", new=AsyncMock(side_effect=[failure, {"choices": []}])) as live:
            await node.request_completion("Featherless", "url", "synthetic", {"stream": True, "model": "test"}, 5)
        self.assertEqual(live.await_count, 2)

    async def test_cancelling_live_request_closes_http_connection(self):
        ready, closed = asyncio.Event(), asyncio.Event()
        async def handler(request):
            response = service.web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            ready.set()
            try:
                while True:
                    await response.write(b": keepalive\n\n")
                    await asyncio.sleep(.01)
            except ConnectionResetError:
                pass
            finally:
                closed.set()
            return response
        app = service.web.Application()
        app.router.add_post("/chat", handler)
        runner = service.web.AppRunner(app)
        await runner.setup()
        site = service.web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        task = asyncio.create_task(node.interruptible(streaming.request_stream(f"http://127.0.0.1:{port}/chat", "synthetic-secret", {"stream": True}, 2)))
        try:
            await asyncio.wait_for(ready.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(closed.wait(), 1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await runner.cleanup()


if __name__ == "__main__":
    unittest.main()
