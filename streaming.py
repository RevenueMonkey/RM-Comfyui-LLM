"""Incremental Chat Completions / Responses SSE transport and console display."""
import asyncio
import json
import sys
import time

import aiohttp

from .service import MAX_RESPONSE_BYTES, RMError, ProviderHTTPError, provider_error


class ConsoleStream:
    def __init__(self, key):
        self.key = key
        self.pending = {}
        self.channel = None
        self.last_activity = time.monotonic()

    def write(self, channel, text):
        if not isinstance(text, str) or not text:
            return
        self.last_activity = time.monotonic()
        text = (self.pending.pop(channel, "") + text).replace(self.key, "[REDACTED]")
        # Hold only a possible credential prefix, including across token boundaries.
        keep = 0
        for length in range(min(len(text), len(self.key) - 1), 0, -1):
            if text.endswith(self.key[:length]):
                keep = length
                break
        if keep:
            self.pending[channel] = text[-keep:]
            text = text[:-keep]
        self.emit(channel, text)

    def emit(self, channel, text):
        channel = channel.replace(self.key, "[REDACTED]") if self.key else channel
        channel = "".join(char for char in channel if ord(char) >= 32 and not 127 <= ord(char) <= 159)
        text = "".join(char for char in text if char in "\n\t" or (ord(char) >= 32 and not 127 <= ord(char) <= 159))
        if not text:
            return
        if channel != self.channel:
            sys.stdout.write(f"\n[RM-LLM] {channel}:\n")
            self.channel = channel
        sys.stdout.write(text)
        sys.stdout.flush()

    def finish(self, complete):
        if complete:
            for channel, text in self.pending.items():
                self.emit(channel, text)
        self.pending.clear()
        if self.channel is not None:
            sys.stdout.write("\n")
            sys.stdout.flush()


async def sse_events(content):
    buffer = b""
    data = []
    total = 0
    async for chunk in content.iter_chunked(65536):
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise RMError("Provider response exceeds 64 MiB.")
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.rstrip(b"\r")
            if not line:
                if data:
                    yield b"\n".join(data).decode("utf-8")
                    data.clear()
            elif line.startswith(b"data:"):
                data.append(line[5:].removeprefix(b" "))
    # A final event need not end with a blank line.
    if buffer.startswith(b"data:"):
        data.append(buffer[5:].removeprefix(b" ").rstrip(b"\r"))
    if data:
        yield b"\n".join(data).decode("utf-8")


def merge_delta(target, delta):
    for name, value in delta.items():
        if value is None:
            continue
        if name in {"tool_calls", "reasoning_details"} and isinstance(value, list):
            items = target.setdefault(name, [])
            for position, part in enumerate(value):
                index = part.get("index", position)
                item = next((entry for entry in items if entry.get("index") == index), None)
                if item is None:
                    item = {"index": index}
                    items.append(item)
                merge_delta(item, part)
        elif isinstance(value, dict):
            merge_delta(target.setdefault(name, {}), value)
        elif isinstance(value, str) and name in {"content", "reasoning", "reasoning_content", "text", "arguments", "name", "refusal", "data", "signature"}:
            target[name] = target.get(name, "") + value
        elif isinstance(value, list):
            if name == "content" and isinstance(target.get(name), str):
                previous = target[name]
                target[name] = ([{"type": "text", "text": previous}] if previous else []) + value
            else:
                target.setdefault(name, []).extend(value)
        else:
            target[name] = value


async def read_completion_stream(content, key, console):
    result = {"object": "chat.completion", "choices": []}
    choices = {}
    async for event in sse_events(content):
        if event.strip() == "[DONE]":
            if not choices:
                raise RMError("Provider returned an empty completion stream.")
            result["choices"] = [choices[index] for index in sorted(choices)]
            return result
        chunk = json.loads(event)
        if not isinstance(chunk, dict):
            raise RMError("Provider returned an invalid streaming event.")
        if chunk.get("error"):
            detail = provider_error(200, event, key)
            error = chunk["error"]
            # A capacity rejection can arrive inside an HTTP 200 stream.
            # Reuse the request layer's bounded 503 retries only before any
            # completion choice has started; never repeat partial output.
            if not choices and isinstance(error, dict) and error.get("code") == "capacity_exhausted":
                raise ProviderHTTPError(503, f"Provider capacity unavailable. {str(detail).split('Provider detail: ', 1)[-1]}")
            raise RMError(f"Provider stream failed. {str(detail).split('Provider detail: ', 1)[-1]} No automatic retry was made.")
        for name, value in chunk.items():
            if name not in {"choices", "object"}:
                result[name] = value
        for part in chunk.get("choices", []):
            index = part.get("index", 0)
            choice = choices.setdefault(index, {"index": index, "message": {"role": "assistant", "content": ""}, "finish_reason": None})
            if part.get("finish_reason") == "error":
                raise RMError("Provider reported a failed stream. No automatic retry was made.")
            delta = part.get("delta") or {}
            merge_delta(choice["message"], delta)
            for name, value in part.items():
                if name not in {"delta", "index"} and value is not None:
                    if name == "logprobs" and isinstance(value, dict):
                        merge_delta(choice.setdefault(name, {}), value)
                    else:
                        choice[name] = value
            suffix = f" (choice {index})" if index else ""
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            if not reasoning and isinstance(delta.get("content"), list):
                reasoning = "".join(item.get("text", "") for part in delta["content"] if isinstance(part, dict) and part.get("type") == "thinking" for item in part.get("thinking", []) if isinstance(item, dict))
            if not reasoning:
                reasoning = "".join(item.get("text", "") for item in delta.get("reasoning_details", []) if isinstance(item, dict))
            console.write("Reasoning" + suffix, reasoning)
            text = delta.get("content")
            if isinstance(text, list):
                text = "".join(item.get("text", "") for item in text if isinstance(item, dict))
            console.write("Response" + suffix, text)
    raise RMError("Provider stream ended before [DONE]; the response is incomplete. No automatic retry was made.")


def response_error(document, key, retry_header=None):
    error = document.get("error") or document
    code = str(error.get("code", "")) if isinstance(error, dict) else ""
    status = int(code) if code.isdecimal() and 400 <= int(code) <= 599 else 0
    return provider_error(status, json.dumps({"error": error}), key, retry_header, http_status=200)


async def read_response_stream(content, key, console):
    """Display deltas, but return only the provider's authoritative terminal object."""
    printed = set()
    tool_names = {}

    def display_item(item, index):
        if not isinstance(item, dict):
            raise RMError("Provider returned an invalid Responses output item.")
        item_id = item.get("id", index)
        if item.get("type") == "function_call":
            part = (item_id, "arguments")
            if part not in printed:
                console.write("Tool " + item.get("name", "function"), item.get("arguments", ""))
                printed.add(part)
        elif item.get("type") in {"message", "reasoning"}:
            parts = item.get("content", []) if item["type"] == "message" else item.get("summary", [])
            if not isinstance(parts, list) or any(not isinstance(part, dict) for part in parts):
                raise RMError("Provider returned invalid Responses content parts.")
            for position, content_part in enumerate(parts):
                part_type = content_part.get("type")
                if part_type not in {"output_text", "refusal", "summary_text"}:
                    continue
                kind = "reasoning_summary_text" if part_type == "summary_text" else part_type
                part = (item_id, "response." + kind, position)
                if part not in printed:
                    channel = "Reasoning" if part_type == "summary_text" else "Refusal" if part_type == "refusal" else "Response"
                    console.write(channel, content_part.get("text", content_part.get("refusal", "")))
                    printed.add(part)

    async for event in sse_events(content):
        if event.strip() == "[DONE]":
            break
        chunk = json.loads(event)
        if not isinstance(chunk, dict):
            raise RMError("Provider returned an invalid Responses streaming event.")
        kind = chunk.get("type", "")
        if kind == "error" or chunk.get("error"):
            raise response_error(chunk, key)
        if kind in {"response.completed", "response.incomplete", "response.failed"}:
            result = chunk.get("response")
            if not isinstance(result, dict):
                raise RMError("Provider terminal event has no response object.")
            expected = kind.removeprefix("response.")
            if result.get("status") != expected:
                raise RMError("Provider terminal event has an inconsistent response status.")
            if result.get("error"):
                raise response_error(result, key)
            output = result.get("output", [])
            if not isinstance(output, list):
                raise RMError("Provider terminal response has no output-item list.")
            for index, item in enumerate(output):
                display_item(item, index)
            # Incomplete output is returned as incomplete, never upgraded to success.
            return result
        item_id = chunk.get("item_id", chunk.get("output_index", 0))
        if kind in {"response.output_item.added", "response.output_item.done"}:
            item = chunk.get("item") or {}
            item_id = item.get("id", chunk.get("output_index", 0))
            if item.get("type") == "function_call":
                name = item.get("name", "function")
                tool_names[item_id] = name
                channel = "Tool " + name
                if kind.endswith("added"):
                    console.write(channel, "Generating arguments…\n")
            if kind.endswith("done"):
                display_item(item, chunk.get("output_index", 0))
        elif kind == "response.function_call_arguments.delta":
            printed.add((item_id, "arguments"))
            console.write("Tool " + tool_names.get(item_id, "arguments"), chunk.get("delta"))
        elif kind in {"response.output_text.delta", "response.refusal.delta",
                      "response.reasoning_summary_text.delta", "response.reasoning_text.delta"}:
            channel = "Reasoning" if "reasoning" in kind else "Refusal" if "refusal" in kind else "Response"
            part = (item_id, kind.removesuffix(".delta"), chunk.get("content_index", chunk.get("summary_index", 0)))
            printed.add(part)
            console.write(channel, chunk.get("delta"))
        elif kind in {"response.output_text.done", "response.refusal.done",
                      "response.reasoning_summary_text.done", "response.reasoning_text.done"}:
            part = (item_id, kind.removesuffix(".done"), chunk.get("content_index", chunk.get("summary_index", 0)))
            if part not in printed:
                channel = "Reasoning" if "reasoning" in kind else "Refusal" if "refusal" in kind else "Response"
                console.write(channel, chunk.get("text", chunk.get("refusal", "")))
                printed.add(part)
    raise RMError("Provider stream ended without a terminal Responses event; no answer or tool call was committed. No automatic retry was made.")


async def stream_heartbeat(console, interval=15):
    started = time.monotonic()
    while True:
        await asyncio.sleep(interval)
        if time.monotonic() - console.last_activity >= interval:
            console.write("Status", f"Request still awaiting provider output ({time.monotonic() - started:.0f}s elapsed).\n")


async def _request_stream(url, key, body, timeout, reader, *, extra_headers=None):
    headers = {"User-Agent": "RM-LLM/1.0", "Accept": "text/event-stream"}
    headers.update(extra_headers if extra_headers is not None else {"Authorization": "Bearer " + key})
    console = ConsoleStream(key)
    complete = False
    heartbeat = asyncio.create_task(stream_heartbeat(console))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout, connect=20)) as client:
            async with client.post(url, headers=headers, json=body, allow_redirects=False) as response:
                if response.status != 200:
                    raw = await response.content.read(16384)
                    raise provider_error(response.status, raw, key, response.headers.get("Retry-After"))
                if response.content_type != "text/event-stream":
                    raw = await response.content.read(16384)
                    try:
                        document = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        document = None
                    if isinstance(document, dict) and document.get("error"):
                        raise response_error(document, key, response.headers.get("Retry-After"))
                    raise RMError("Provider did not return the requested live SSE stream. No non-streaming fallback or automatic retry was made.")
                result = await reader(response.content, key, console)
                complete = True
                return result
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise RMError("Provider stream disconnected or timed out. No automatic retry was made.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RMError("Provider returned an invalid streaming event. No automatic retry was made.") from None
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        console.finish(complete)


async def request_stream(url, key, body, timeout):
    return await _request_stream(url, key, body, timeout, read_completion_stream)


async def request_response_stream(url, key, body, timeout):
    return await _request_stream(url, key, body, timeout, read_response_stream)
