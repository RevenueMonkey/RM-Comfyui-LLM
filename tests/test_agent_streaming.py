"""Responses SSE regression tests. Local synthetic providers only; no paid calls."""
import asyncio
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rm_llm import service, streaming
from rm_llm import agent


KEY = "synthetic-secret"


def event(kind, **fields):
    return ("data: " + json.dumps(dict(type=kind, **fields), ensure_ascii=False) + "\n\n").encode()


class Content:
    def __init__(self, data):
        self.data = data

    async def iter_chunked(self, size):
        for byte in self.data:
            yield bytes([byte])


class AgentStreaming(unittest.IsolatedAsyncioTestCase):
    async def test_agent_streams_before_complete_and_preserves_tool_items_and_usage(self):
        ready, finish = asyncio.Event(), asyncio.Event()
        captured = {}
        terminal = dict(status="completed", output=[
            dict(type="reasoning", id="r1", encrypted_content="opaque-do-not-log"),
            dict(type="function_call", id="fc1", call_id="call1", name="lookup", arguments='{"query":"caf\u00e9 synthetic-secret"}')],
            usage=dict(input_tokens=12, output_tokens=8))

        async def handler(request):
            captured.update(await request.json())
            response = service.web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            await response.write(event("response.created", response=dict(status="in_progress")))
            await response.write(event("response.reasoning_summary_text.delta", item_id="r1", delta="Checking evidence. "))
            await response.write(event("response.output_item.added", item=dict(type="function_call", id="fc1", name="lookup")))
            await response.write(event("response.function_call_arguments.delta", item_id="fc1", delta='{"query":"café synthetic-'))
            ready.set()
            await finish.wait()
            await response.write(event("response.function_call_arguments.delta", item_id="fc1", delta='secret"}'))
            await response.write(event("response.output_item.done", item=terminal["output"][1]))
            await response.write(event("response.completed", response=terminal))
            return response

        app = service.web.Application()
        app.router.add_post("/responses", handler)
        runner = service.web.AppRunner(app)
        await runner.setup()
        site = service.web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        profile = agent.AgentProfile().configure("test/model", "TEST_KEY", "Auto", "medium", 1000, 64000, 10)[0]
        caps = dict(parameters={"tools": {}}, endpoints=[dict(id="test", context_length=128000)])
        output = io.StringIO()
        task = None
        try:
            with patch.object(streaming.sys, "stdout", output), patch.object(agent, "consume_key", return_value=KEY), \
                 patch.object(agent, "provider_info", return_value=(f"http://127.0.0.1:{port}", "")), \
                 patch.object(agent, "model_capabilities", new=AsyncMock(return_value=caps)):
                task = asyncio.create_task(agent.AgentRequest().request(profile, dict(instructions="Test", input=[], tools=[])))
                await asyncio.wait_for(ready.wait(), 2)
                for _ in range(100):
                    if "café " in output.getvalue():
                        break
                    await asyncio.sleep(.01)
                self.assertIn("Checking evidence.", output.getvalue())
                self.assertIn("Tool lookup", output.getvalue())
                self.assertIn("café ", output.getvalue())
                self.assertFalse(task.done())
                finish.set()
                result = (await task)[0]
            self.assertTrue(captured["stream"])
            self.assertNotIn(KEY, output.getvalue())
            self.assertNotIn("opaque-do-not-log", output.getvalue())
            self.assertEqual(output.getvalue().count("café "), 1)
            self.assertIn("[REDACTED]", output.getvalue())
            self.assertEqual(result["status"], "tools")
            self.assertEqual(result["calls"][0]["arguments"], {"query": "café [REDACTED]"})
            self.assertEqual(result["usage"], terminal["usage"])
            self.assertEqual(result["output"][0], terminal["output"][0])
        finally:
            finish.set()
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await runner.cleanup()

    async def read(self, data):
        output = io.StringIO()
        with patch.object(streaming.sys, "stdout", output):
            console = streaming.ConsoleStream(KEY)
            result = await streaming.read_response_stream(Content(data), KEY, console)
            console.finish(True)
        return result, output.getvalue()

    async def test_complete_text_and_done_only_reasoning_not_repeated(self):
        terminal = dict(status="completed", output=[dict(type="message", id="m1", content=[dict(type="output_text", text="Exact result")])])
        data = event("response.output_text.delta", item_id="m1", delta="Exact result")
        data += event("response.output_text.done", item_id="m1", text="Exact result")
        data += event("response.reasoning_summary_text.done", item_id="r1", text="Provider summary")
        data += event("response.completed", response=terminal)
        result, text = await self.read(data)
        self.assertEqual(text.count("Exact result"), 1)
        self.assertIn("Provider summary", text)
        self.assertEqual(result, terminal)

    async def test_provider_buffered_output_is_displayed_when_terminal_arrives(self):
        terminal = dict(status="completed", output=[dict(type="message", id="m1", content=[dict(type="output_text", text="Buffered result")])])
        result, text = await self.read(event("response.completed", response=terminal))
        self.assertEqual(text.count("Buffered result"), 1)
        self.assertEqual(result, terminal)

    async def test_truncated_stream_never_commits_partial_tool_call(self):
        data = event("response.function_call_arguments.delta", item_id="fc1", delta='{"query":')
        for tail in (b"", b"data: [DONE]\n\n"):
            with patch.object(streaming.sys, "stdout", io.StringIO()), self.assertRaisesRegex(service.RMError, "no answer or tool call"):
                await self.read(data + tail)

    async def test_incomplete_and_refusal_remain_failures(self):
        cases = [dict(status="incomplete", incomplete_details=dict(reason="max_output_tokens"), output=[]),
                 dict(status="completed", output=[dict(type="message", content=[dict(type="refusal", refusal="Cannot")])])]
        for terminal in cases:
            result, _ = await self.read(event("response." + terminal["status"], response=terminal))
            normal = agent.normalize(result)
            self.assertEqual(normal["status"], "failure")
            self.assertEqual(normal["calls"], [])
            self.assertFalse(normal["retryable"])

    async def test_provider_error_keeps_semantic_status_without_secret(self):
        error = dict(code="503", message="Lost " + KEY)
        for data in (event("error", **error), event("response.failed", response=dict(status="failed", error=error))):
            with self.assertRaises(service.ProviderHTTPError) as found:
                await self.read(data)
            self.assertEqual(found.exception.status, 503)
            self.assertNotIn(KEY, str(found.exception))

    async def test_wrong_or_missing_terminal_object_rejected(self):
        for data in (event("response.completed"), event("response.completed", response=dict(status="incomplete", output=[])),
                     event("response.completed", response=dict(status="completed", output={})),
                     event("response.completed", response=dict(status="completed", output=["invalid"])),
                     b"data: []\n\n"):
            with self.assertRaises(service.RMError):
                await self.read(data)

    async def test_heartbeat_visible_while_silent_and_cancellable(self):
        output = io.StringIO()
        with patch.object(streaming.sys, "stdout", output):
            console = streaming.ConsoleStream(KEY)
            heartbeat = asyncio.create_task(streaming.stream_heartbeat(console, interval=.01))
            try:
                await asyncio.sleep(.04)
                self.assertIn("awaiting provider output", output.getvalue())
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
        self.assertTrue(heartbeat.cancelled())

    async def test_json_error_instead_of_sse_not_misreported_as_config_failure(self):
        async def handler(request):
            return service.web.json_response(dict(error=dict(code=429, message="Busy " + KEY)), headers={"Retry-After": "3"})
        app = service.web.Application()
        app.router.add_post("/responses", handler)
        runner = service.web.AppRunner(app)
        await runner.setup()
        site = service.web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with self.assertRaises(service.ProviderHTTPError) as found:
                await streaming.request_response_stream(f"http://127.0.0.1:{port}/responses", KEY, dict(stream=True), 5)
            self.assertEqual(found.exception.status, 429)
            self.assertEqual(found.exception.retry_after, 3)
            self.assertNotIn(KEY, str(found.exception))
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    unittest.main()
