"""Translate RM-LLM requests at the provider boundary; keep native responses."""
import copy
import json
from urllib.parse import quote

from .providers import PROVIDERS, headers, model_id
from .service import RMError, request_json, provider_error
from .streaming import _request_stream, sse_events


def media_data(url):
    if not isinstance(url, str) or not url.startswith("data:") or ";base64," not in url:
        raise RMError("This provider requires inline base64 media.")
    mime, data = url[5:].split(";base64,", 1)
    return mime, data


def translate(provider, body, caps):
    body = copy.deepcopy(body)
    model = model_id(provider, body.pop("model"))
    stream = body.pop("stream", False)
    messages = body.pop("messages")
    reasoning = body.pop("reasoning", None)
    if reasoning is not None:
        if not isinstance(reasoning, dict) or set(reasoning) - {"enabled", "effort", "max_tokens"}:
            raise RMError("Reasoning accepts enabled, effort and max_tokens for this provider.")
        enabled = reasoning.get("enabled", True)
        if type(enabled) is not bool: raise RMError("Thinking/Reasoning must be On or Off.")
        if not enabled and caps.get("reasoning_options", {}).get("mandatory"):
            raise RMError("This model requires reasoning; leave Thinking/Reasoning on or at its default.")
        if provider == "Anthropic":
            if "thinking" in body: raise RMError("Set Thinking/Reasoning or thinking JSON, not both.")
            native = caps.get("native_thinking") or {}
            adaptive = (native.get("types", {}).get("adaptive") or {}).get("supported")
            adaptive = adaptive or model.startswith(("claude-opus-4-6", "claude-sonnet-4-6"))
            if not enabled: body["thinking"] = {"type": "disabled"}
            elif adaptive:
                if "max_tokens" in reasoning: raise RMError("Adaptive thinking uses effort, not a thinking-token budget.")
                body["thinking"] = {"type": "adaptive"}
            else:
                body["thinking"] = {"type": "enabled", "budget_tokens": reasoning.get("max_tokens", 1024)}
            if "effort" in reasoning:
                if "output_config" not in caps["parameters"]: raise RMError("This model does not advertise an effort control.")
                body.setdefault("output_config", {})["effort"] = reasoning["effort"]
        elif provider == "Google Gemini":
            if "thinking_config" in body: raise RMError("Set Thinking/Reasoning or thinking_config JSON, not both.")
            config = {"includeThoughts": True}
            if model.startswith("gemini-3"):
                if "max_tokens" in reasoning: raise RMError("This Gemini family uses thinking levels, not a token budget.")
                if "effort" in reasoning: config["thinkingLevel"] = reasoning["effort"]
            else:
                if "effort" in reasoning: raise RMError("This Gemini family uses a thinking-token budget, not effort.")
                config["thinkingBudget"] = reasoning.get("max_tokens", -1) if enabled else 0
            body["thinking_config"] = config
        elif provider in {"OpenAI", "Groq", "xAI"}:
            if "max_tokens" in reasoning: raise RMError("This provider uses reasoning effort, not a thinking-token budget.")
            if "reasoning_effort" in body and "effort" in reasoning: raise RMError("Set only one reasoning effort.")
            if not enabled: body["reasoning_effort"] = "none"
            elif "effort" in reasoning:
                if "reasoning_effort" not in caps["parameters"]: raise RMError("This model does not expose reasoning effort.")
                body["reasoning_effort"] = reasoning["effort"]
        elif provider == "DeepSeek":
            if model == "deepseek-reasoner":
                if set(reasoning) - {"enabled"}: raise RMError("The selected DeepSeek model does not expose a separate reasoning budget or effort.")
            else:
                if "max_tokens" in reasoning: raise RMError("DeepSeek uses reasoning effort, not a thinking-token budget.")
                if "thinking" in body: raise RMError("Set Thinking/Reasoning or thinking JSON, not both.")
                body["thinking"] = {"type": "enabled" if enabled else "disabled"}
                if not enabled: body.pop("reasoning_effort", None)
                elif "effort" in reasoning: body["reasoning_effort"] = reasoning["effort"]
        elif provider == "Together AI":
            if "max_tokens" in reasoning: raise RMError("Together does not use a separate reasoning-token budget here.")
            if not caps.get("reasoning_options", {}).get("mandatory"):
                body["reasoning"] = {"enabled": enabled}
            if "effort" in reasoning:
                if "reasoning_effort" not in caps["parameters"]: raise RMError("This model does not advertise reasoning effort.")
                body["reasoning_effort"] = reasoning["effort"]
        elif provider == "Mistral AI":
            if "reasoning_effort" in caps["parameters"]:
                if "max_tokens" in reasoning: raise RMError("Mistral uses reasoning effort, not a separate token budget.")
                body["reasoning_effort"] = reasoning.get("effort", body.get("reasoning_effort", "high")) if enabled else "none"
            elif set(reasoning) - {"enabled"}: raise RMError("This native reasoning model does not expose a separate budget or effort.")
        elif provider == "Fireworks AI":
            if "thinking" in body: raise RMError("Set Thinking/Reasoning or thinking JSON, not both.")
            if "max_tokens" in reasoning:
                if not caps.get("reasoning_options", {}).get("supports_budget"):
                    raise RMError("This Fireworks model does not advertise a reasoning-token budget.")
                budget = reasoning["max_tokens"]
                if type(budget) is not int or budget < 1: raise RMError("Reasoning budget must be a positive integer.")
                if "effort" in reasoning: raise RMError("Set a reasoning budget or effort, not both.")
                body["reasoning_effort"] = budget if enabled else "none"
            else:
                body["reasoning_effort"] = reasoning.get("effort", body.get("reasoning_effort", "medium")) if enabled else "none"
    base = PROVIDERS[provider][0]
    if provider == "Anthropic":
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        native_messages = []
        for message in messages:
            if message["role"] == "system": continue
            parts = message["content"]
            if isinstance(parts, list):
                native = []
                for part in parts:
                    if part["type"] == "text": native.append(part)
                    elif part["type"] == "image_url":
                        mime, data = media_data(part["image_url"]["url"])
                        native.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
                    else: raise RMError("Unsupported Anthropic content part.")
                parts = native
            native_messages.append({"role": message["role"], "content": parts})
        body.setdefault("max_tokens", min(4096, caps["endpoints"][0].get("max_tokens") or 4096))
        thinking = body.get("thinking", {})
        if thinking.get("type") == "enabled":
            budget = thinking.get("budget_tokens")
            if type(budget) is not int or not 1024 <= budget < body["max_tokens"]:
                raise RMError("Anthropic thinking budget must be at least 1024 and below max_tokens.")
            if "temperature" in body and body["temperature"] != 1:
                raise RMError("Anthropic extended thinking requires temperature 1 or omission.")
        if "temperature" in body and "top_p" in body:
            raise RMError("Anthropic: set temperature or top_p individually, not both.")
        if "stop" in body:
            stop = body.pop("stop"); body["stop_sequences"] = [stop] if isinstance(stop, str) else stop
        if "tools" in body:
            body["tools"] = [dict(name=t["function"]["name"], description=t["function"].get("description", ""), input_schema=t["function"].get("parameters", {"type": "object", "properties": {}})) if t.get("type") == "function" else t for t in body["tools"]]
        if "tool_choice" in body:
            choice = body["tool_choice"]
            if isinstance(choice, str): body["tool_choice"] = {"type": "any" if choice == "required" else choice}
            elif choice.get("type") == "function": body["tool_choice"] = {"type": "tool", "name": choice["function"]["name"]}
        return base + "/messages", dict(body, model=model, messages=native_messages, stream=stream, **({"system": system} if system else {}))
    if provider == "Google Gemini":
        native = {"contents": []}
        for message in messages:
            if message["role"] == "system":
                native["systemInstruction"] = {"parts": [{"text": message["content"]}]}; continue
            parts = message["content"]
            if isinstance(parts, str): parts = [{"type": "text", "text": parts}]
            translated = []
            for part in parts:
                if part["type"] == "text": translated.append({"text": part["text"]})
                elif part["type"] in {"image_url", "video_url"}:
                    mime, data = media_data(part[part["type"]]["url"])
                    translated.append({"inlineData": {"mimeType": mime, "data": data}})
                else: raise RMError("Unsupported Gemini content part.")
            native["contents"].append({"role": "user" if message["role"] == "user" else "model", "parts": translated})
        config = {}
        for name, native_name in {"temperature": "temperature", "top_p": "topP", "top_k": "topK", "max_tokens": "maxOutputTokens", "seed": "seed", "stop": "stopSequences", "thinking_config": "thinkingConfig"}.items():
            if name in body:
                value = body.pop(name)
                config[native_name] = [value] if name == "stop" and isinstance(value, str) else value
        if "response_format" in body:
            form = body.pop("response_format")
            if form.get("type") in {"json_object", "json_schema"}:
                config["responseMimeType"] = "application/json"
                if form.get("type") == "json_schema": config["responseJsonSchema"] = form["json_schema"]["schema"]
            elif form.get("type") != "text": raise RMError("Unsupported Gemini response format.")
        if "safety_settings" in body: native["safetySettings"] = body.pop("safety_settings")
        if "tools" in body:
            tools = body.pop("tools")
            if any(t.get("type") != "function" for t in tools): raise RMError("Gemini tools must use function declarations in OpenAI format.")
            native["tools"] = [{"functionDeclarations": [{k: v for k, v in t["function"].items() if k in {"name", "description", "parameters"}} for t in tools]}]
        if "tool_choice" in body:
            choice = body.pop("tool_choice")
            if isinstance(choice, str): option = {"mode": {"auto": "AUTO", "none": "NONE", "required": "ANY"}[choice]}
            else: option = {"mode": "ANY", "allowedFunctionNames": [choice["function"]["name"]]}
            native["toolConfig"] = {"functionCallingConfig": option}
        if body: raise RMError("Unsupported Gemini fields: " + ", ".join(body))
        if config: native["generationConfig"] = config
        operation = ":streamGenerateContent?alt=sse" if stream else ":generateContent"
        return base + "/models/" + quote(model, safe="") + operation, native
    if provider == "Mistral AI" and "seed" in body: body["random_seed"] = body.pop("seed")
    if not stream and "stream_options" in body:
        raise RMError("stream_options requires Live console output to be enabled.")
    return base + "/chat/completions", dict(body, model=model, messages=messages, stream=stream)


def normalize(provider, raw):
    if provider == "Mistral AI":
        result = copy.deepcopy(raw)
        for choice in result.get("choices", []):
            message = choice.get("message", {})
            if isinstance(message.get("content"), list):
                parts = message["content"]
                message["content"] = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
                message["reasoning"] = "".join(t.get("text", "") for p in parts if p.get("type") == "thinking" for t in p.get("thinking", []))
        result["provider_response"] = raw
        return result
    if provider not in {"Anthropic", "Google Gemini"}: return raw
    message = {"role": "assistant", "content": "", "reasoning": ""}
    calls = []
    if provider == "Anthropic":
        parts = raw.get("content", [])
        finish = raw.get("stop_reason")
        for part in parts:
            if part.get("type") == "text": message["content"] += part.get("text", "")
            elif part.get("type") == "thinking": message["reasoning"] += part.get("thinking", "")
            elif part.get("type") == "tool_use": calls.append({"id": part["id"], "type": "function", "function": {"name": part["name"], "arguments": json.dumps(part["input"])}})
        usage = raw.get("usage", {})
    else:
        candidates = raw.get("candidates") or []
        if not candidates:
            reason = (raw.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise RMError("Gemini returned no response: " + str(reason))
        finish = candidates[0].get("finishReason")
        for part in candidates[0].get("content", {}).get("parts", []):
            if "text" in part: message["reasoning" if part.get("thought") else "content"] += part["text"]
            elif "functionCall" in part:
                call = part["functionCall"]
                calls.append({"type": "function", "function": {"name": call["name"], "arguments": json.dumps(call.get("args", {}))}})
        usage = raw.get("usageMetadata", {})
    if calls: message["tool_calls"] = calls
    return {"choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage, "provider_response": raw}


async def read_native_stream(provider, content, key, console):
    raw, blocks, arguments = {}, {}, {}
    terminal = False
    async for event in sse_events(content):
        chunk = json.loads(event)
        if chunk.get("error") or chunk.get("type") == "error": raise provider_error(200, event, key)
        if provider == "Anthropic":
            kind = chunk.get("type")
            if kind == "message_start": raw = chunk["message"]
            elif kind == "content_block_start":
                blocks[chunk["index"]] = chunk["content_block"]
            elif kind == "content_block_delta":
                index, delta = chunk["index"], chunk["delta"]
                part = blocks[index]
                for name in ("text", "thinking", "signature"):
                    if name in delta:
                        part[name] = part.get(name, "") + delta[name]
                        if name != "signature": console.write("Reasoning" if name == "thinking" else "Response", delta[name])
                if "partial_json" in delta: arguments[index] = arguments.get(index, "") + delta["partial_json"]
            elif kind == "message_delta":
                raw.update(chunk.get("delta", {})); raw.setdefault("usage", {}).update(chunk.get("usage", {}))
            elif kind == "message_stop":
                terminal = True; break
        else:
            if chunk.get("promptFeedback", {}).get("blockReason"):
                raise RMError("Gemini blocked the prompt: " + str(chunk["promptFeedback"]["blockReason"]))
            for candidate in chunk.get("candidates", []):
                index = candidate.get("index", 0)
                target = blocks.setdefault(index, {"index": index, "content": {"role": "model", "parts": []}})
                parts = candidate.get("content", {}).get("parts", [])
                target["content"]["parts"].extend(parts)
                target.update({k: v for k, v in candidate.items() if k != "content"})
                for part in parts: console.write("Reasoning" if part.get("thought") else "Response", part.get("text"))
                if "finishReason" in candidate:
                    target["finishReason"] = candidate["finishReason"]; terminal = True
            raw.update({k: v for k, v in chunk.items() if k != "candidates"})
    if not terminal: raise RMError("Provider stream ended before completion. No automatic retry was made.")
    if provider == "Anthropic":
        for index, value in arguments.items(): blocks[index]["input"] = json.loads(value)
        raw["content"] = [blocks[i] for i in sorted(blocks)]
    else: raw["candidates"] = [blocks[i] for i in sorted(blocks)]
    return raw


async def complete(provider, body, caps, key, timeout):
    try:
        url, native = translate(provider, body, caps)
    except RMError:
        raise
    except (KeyError, TypeError, ValueError):
        raise RMError("Check provider-specific tools, response_format and thinking settings: an object has an invalid structure.") from None
    if provider in {"Anthropic", "Google Gemini"}:
        limit = 20_000_000 if provider == "Google Gemini" else 32_000_000
        if len(json.dumps(native).encode("utf-8")) > limit:
            raise RMError(f"{provider} inline request is too large. Resize images or shorten the video.")
    if provider not in {"Anthropic", "Google Gemini"}:
        from .node import request_completion
        return normalize(provider, await request_completion(provider, url, key, native, timeout))
    if body.get("stream"):
        async def reader(content, credential, console):
            return await read_native_stream(provider, content, credential, console)
        raw = await _request_stream(url, key, native, timeout, reader, extra_headers=headers(provider, key))
    else:
        raw = await request_json(url, key, native, timeout, extra_headers=headers(provider, key))
    return normalize(provider, raw)
