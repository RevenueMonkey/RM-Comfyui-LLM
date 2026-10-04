"""Provider adapters. No SDKs, credentials or network activity at import time."""
import copy
import re
from urllib.parse import quote, urlencode

# Fixed destinations: a model name or catalogue response never chooses a host.
PROVIDERS = {
    "OpenAI": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "Google Gemini": ("https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY"),
    "Anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "DeepSeek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "Groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "Mistral AI": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "xAI": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "Together AI": ("https://api.together.ai/v1", "TOGETHER_API_KEY"),
    "Fireworks AI": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
}
SOURCES = {
    "OpenAI": "https://developers.openai.com/api/reference/resources/chat",
    "Google Gemini": "https://ai.google.dev/api/generate-content",
    "Anthropic": "https://platform.claude.com/docs/en/api/messages/create",
    "DeepSeek": "https://api-docs.deepseek.com/api/create-chat-completion",
    "Groq": "https://console.groq.com/docs/api-reference",
    "Mistral AI": "https://docs.mistral.ai/api/endpoint/chat",
    "xAI": "https://docs.x.ai/developers/rest-api-reference/inference/chat",
    "Together AI": "https://docs.together.ai/reference/chat-completions-1",
    "Fireworks AI": "https://docs.fireworks.ai/api-reference/post-chatcompletions",
}
SCHEMAS = {
    "temperature": {"type": "number", "minimum": 0, "maximum": 2},
    "top_p": {"type": "number", "minimum": 0, "maximum": 1},
    "top_k": {"type": "integer", "minimum": 1},
    "max_tokens": {"type": "integer", "minimum": 1},
    "max_completion_tokens": {"type": "integer", "minimum": 1},
    "seed": {"type": "integer"},
    "stop": {"type": ["string", "array"]},
    "frequency_penalty": {"type": "number", "minimum": -2, "maximum": 2},
    "presence_penalty": {"type": "number", "minimum": -2, "maximum": 2},
    "response_format": {"type": "object"},
    "tools": {"type": "array"},
    "tool_choice": {"type": ["string", "object"]},
    "reasoning_effort": {"type": "string"},
    "reasoning": {"type": "object", "description": "RM-LLM reasoning settings: enabled, effort or max_tokens, when supported."},
    "thinking": {"type": "object", "description": "Provider-native thinking settings. Do not combine with the Thinking/Reasoning toggle."},
    "thinking_config": {"type": "object", "description": "Gemini thinkingConfig, using its native field names."},
    "output_config": {"type": "object", "description": "Anthropic output_config, including effort where supported."},
    "safety_settings": {"type": "array", "description": "Gemini safetySettings, using its native field names."},
    "stream_options": {"type": "object"},
}
COMMON = "temperature top_p max_tokens stop"
FIELDS = {
    "OpenAI": "temperature top_p max_completion_tokens stop seed frequency_penalty presence_penalty response_format tools tool_choice stream_options",
    "Google Gemini": "temperature top_p top_k max_tokens stop seed response_format tools tool_choice safety_settings",
    "Anthropic": COMMON + " top_k tools tool_choice",
    "DeepSeek": COMMON + " frequency_penalty presence_penalty response_format tools tool_choice stream_options",
    "Groq": "temperature top_p max_completion_tokens stop seed frequency_penalty presence_penalty response_format tools tool_choice stream_options",
    "Mistral AI": COMMON + " seed frequency_penalty presence_penalty response_format tools tool_choice",
    "xAI": COMMON + " seed frequency_penalty presence_penalty response_format tools tool_choice stream_options",
    "Together AI": COMMON + " top_k seed frequency_penalty presence_penalty response_format tools tool_choice stream_options",
    "Fireworks AI": COMMON + " top_k frequency_penalty presence_penalty response_format tools tool_choice stream_options",
}


def records():
    # Reviewed provider contract, not a claim that every model supports every field.
    return {p: {"source": SOURCES[p], "refreshed_at": "2026-10-04T00:00:00Z",
                "parameters": {n: copy.deepcopy(SCHEMAS[n]) for n in sorted(set(FIELDS[p].split()) |
                               {"reasoning", "reasoning_effort", "thinking", "thinking_config", "output_config"})}}
            for p in PROVIDERS}


def headers(provider, key):
    if provider == "Anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    if provider == "Google Gemini":
        return {"x-goog-api-key": key}
    return {"Authorization": "Bearer " + key}


def model_id(provider, model):
    return model.removeprefix("models/") if provider == "Google Gemini" else model


def chat_model(provider, item):
    ident = item.get("id", "").lower()
    if provider == "Google Gemini":
        return "generateContent" in item.get("supportedGenerationMethods", []) and not any(x in ident for x in ("image", "tts", "robotics"))
    if provider == "Together AI":
        return item.get("type") in (None, "chat")
    if provider == "Mistral AI":
        return item.get("capabilities", {}).get("completion_chat", True)
    if provider == "Fireworks AI":
        return bool(item.get("supportsServerless")) and item.get("kind") not in ("EMBEDDING", "IMAGE_GENERATION", "AUDIO")
    if provider == "OpenAI":
        return ident.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4", "ft:gpt-")) and not any(x in ident for x in ("realtime", "audio", "transcribe", "tts", "image", "search", "deep-research", "codex", "-pro"))
    if provider == "Groq":
        return item.get("active", True) and not any(x in ident for x in ("whisper", "tts", "guard", "orpheus"))
    return True


async def catalog(provider, key, request, progress):
    from .service import RMError
    if not key:
        raise RMError("API Key Needed!")
    base = PROVIDERS[provider][0]
    root = base + "/models"
    params = {}
    if provider == "Anthropic": params = {"limit": 1000}
    if provider == "Google Gemini": params = {"pageSize": 1000}
    if provider == "xAI": root = base + "/language-models"
    if provider == "Fireworks AI":
        root = "https://api.fireworks.ai/v1/accounts/fireworks/models"
        params = {"pageSize": 200}
    found, seen = {}, set()
    for page in range(1000):
        url = root + ("?" + urlencode(params) if params else "")
        if url in seen: raise RMError("Provider repeated a model catalogue page.")
        seen.add(url)
        data = await request(url, key, extra_headers=headers(provider, key), allow_list=provider == "Together AI")
        items = data if isinstance(data, list) else data.get("models" if provider in {"Google Gemini", "xAI", "Fireworks AI"} else "data")
        if not isinstance(items, list): raise RMError("Provider returned an invalid model catalogue.")
        for raw in items:
            if not isinstance(raw, dict): continue
            ident = raw.get("id") or raw.get("name")
            if not isinstance(ident, str): continue
            item = dict(raw, id=model_id(provider, ident))
            if not chat_model(provider, item): continue
            item["name"] = raw.get("display_name") or raw.get("displayName") or item["id"]
            found[item["id"]] = item
        progress(provider, state="loading", count=len(found), page=page + 1)
        token = None
        if isinstance(data, dict):
            if provider == "Anthropic" and data.get("has_more"):
                token = data.get("last_id")
                if not token: raise RMError("Provider omitted the next model page cursor.")
                params["after_id"] = token
            elif provider in {"Google Gemini", "Fireworks AI"}:
                token = data.get("nextPageToken")
                params["pageToken"] = token
            elif data.get("has_more"):
                raise RMError("Provider returned undocumented model pagination.")
        if not token: break
    else: raise RMError("Provider model pagination did not finish.")
    if not found: raise RMError("No supported chat models were returned by this provider.")
    return sorted(found.values(), key=lambda item: item["id"].casefold())


async def metadata(provider, model, key, request, cached_catalog):
    from .service import RMError
    model = model_id(provider, model)
    if provider == "Together AI":
        # This provider documents a list, not a GET /models/{id} endpoint.
        try:
            items = await cached_catalog(provider, key)
        except RMError:
            return {"id": model}
        item = next((m for m in items if m["id"] == model), None)
        if item is None:
            # Manual names remain usable during catalogue outages; do not infer media.
            return {"id": model}
        return item
    base = PROVIDERS[provider][0]
    path = "/language-models/" if provider == "xAI" else "/models/"
    url = base + path + quote(model, safe="")
    if provider == "Fireworks AI":
        if not re.fullmatch(r"accounts/[A-Za-z0-9_.-]+/models/[A-Za-z0-9_.-]+", model):
            raise RMError("Use the Fireworks model ID accounts/ACCOUNT/models/MODEL.")
        url = "https://api.fireworks.ai/v1/" + model
    if provider == "DeepSeek":
        # DeepSeek also documents only model listing. Generation accepts manual IDs.
        return {"id": model}
    raw = await request(url, key, extra_headers=headers(provider, key))
    raw = raw.get("data", raw)
    if not isinstance(raw, dict): raise RMError("Provider returned invalid model metadata.")
    if provider != "Fireworks AI" and not chat_model(provider, dict(raw, id=model)):
        raise RMError("This model does not support the node's chat/text transport.")
    return raw


def capabilities(provider, model, raw):
    from .service import RMError
    fields = set(FIELDS[provider].split())
    modalities = ["text"]
    m = model_id(provider, model).lower()
    feature = raw.get("capabilities") or {}
    thinking = feature.get("thinking") or {}
    reasoning_options = {}
    # Never infer vision merely from a VL/vision substring in an arbitrary ID.
    known = {
        "OpenAI": m.startswith(("gpt-4o", "gpt-4.1", "gpt-5", "o3", "o4")) and not m.startswith("o3-mini"),
        "Google Gemini": m.startswith(("gemini-1.5-", "gemini-2.0-", "gemini-2.5-", "gemini-3")),
        "Anthropic": m.startswith(("claude-3", "claude-sonnet-4", "claude-opus-4", "claude-haiku-4")),
        "Groq": m in {"meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"},
        "Together AI": m in {"meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct-fp8", "meta-llama/llama-3.2-11b-vision-instruct-turbo", "meta-llama/llama-3.2-90b-vision-instruct-turbo"},
        "DeepSeek": m in {"deepseek-flash", "deepseek-v4-pro"},
    }
    inputs = raw.get("input_modalities") or (raw.get("architecture") or {}).get("input_modalities")
    vision = feature.get("vision") is True or (feature.get("image_input") or {}).get("supported") is True or raw.get("supportsImageInput") is True
    if isinstance(inputs, list):
        vision = "image" in inputs
    elif "vision" in feature: vision = feature["vision"] is True
    elif "image_input" in feature: vision = feature["image_input"].get("supported") is True
    elif "supportsImageInput" not in raw: vision = vision or known.get(provider, False)
    if vision: modalities.append("image")
    if provider == "Google Gemini" and ("video" in inputs if isinstance(inputs, list) else known[provider]): modalities.append("video")
    context = raw.get("context_length") or raw.get("max_model_len") or raw.get("contextLength") or raw.get("inputTokenLimit") or raw.get("max_input_tokens")
    maximum = raw.get("max_completion_tokens") or raw.get("outputTokenLimit") or (raw.get("max_tokens") if provider == "Anthropic" else None)
    if provider == "OpenAI" and m.startswith(("o1", "o3", "o4", "gpt-5")):
        fields -= {"temperature", "top_p", "stop", "frequency_penalty", "presence_penalty", "seed"}
        fields |= {"reasoning", "reasoning_effort"}
        reasoning_options = {"mandatory": not m.startswith(("gpt-5.1", "gpt-5.2", "gpt-5.4"))}
    if provider == "Anthropic":
        if thinking.get("supported") or m.startswith(("claude-3-7-", "claude-sonnet-4", "claude-opus-4", "claude-haiku-4")):
            fields |= {"reasoning", "thinking"}
        if (feature.get("effort") or {}).get("supported"): fields.add("output_config")
        if m.startswith(("claude-opus-4-6", "claude-sonnet-4-6", "claude-opus-5")):
            fields -= {"temperature", "top_p", "top_k"}
    if provider == "Google Gemini":
        if not raw.get("topK"): fields.discard("top_k")
        if raw.get("thinking") or m.startswith(("gemini-2.5-", "gemini-3")):
            fields |= {"reasoning", "thinking_config"}
            reasoning_options = {"mandatory": m.startswith(("gemini-2.5-pro", "gemini-3"))}
    if provider == "DeepSeek" and m == "deepseek-reasoner":
        fields -= {"temperature", "top_p", "frequency_penalty", "presence_penalty"}
        fields.add("reasoning")
        reasoning_options = {"mandatory": True}
    elif provider == "DeepSeek" and m.startswith(("deepseek-v4", "deepseek-flash")):
        fields -= {"frequency_penalty", "presence_penalty"}
        fields |= {"reasoning", "thinking", "reasoning_effort"}
        reasoning_options = {"default_enabled": True, "supported_efforts": ["none", "low", "high", "max"]}
    if provider == "xAI" and (m.startswith("grok-4") or m.startswith("grok-3-mini")) and "non-reasoning" not in m:
        fields -= {"frequency_penalty", "presence_penalty", "stop"}
        fields.add("reasoning")
        reasoning_options = {"mandatory": True}
        if m.startswith("grok-3-mini"):
            fields.add("reasoning_effort")
            reasoning_options["supported_efforts"] = ["low", "high"]
    if provider == "Groq" and m.startswith("openai/gpt-oss-"):
        fields |= {"reasoning", "reasoning_effort"}
        reasoning_options = {"mandatory": True}
        reasoning_options["supported_efforts"] = ["low", "medium", "high"]
    if provider == "Together AI":
        if m.startswith(("qwen/qwen3", "deepseek-ai/deepseek-v3.1", "deepseek-ai/deepseek-v4", "zai-org/glm-5")):
            fields.add("reasoning")
        elif m.startswith(("openai/gpt-oss-", "deepseek-ai/deepseek-r1")):
            fields.add("reasoning")
            reasoning_options = {"mandatory": True}
            if m.startswith("openai/gpt-oss-"):
                fields.add("reasoning_effort")
                reasoning_options["supported_efforts"] = ["low", "medium", "high"]
    if provider == "Mistral AI" and m.startswith("magistral-"):
        fields.add("reasoning")
        reasoning_options = {"mandatory": True}
    elif provider == "Mistral AI" and m in {"mistral-small-latest", "mistral-small-2603", "mistral-medium-3-5", "zai-glm-5-3"}:
        fields |= {"reasoning", "reasoning_effort"}
        reasoning_options = {"mandatory": m == "zai-glm-5-3", "supported_efforts": ["low", "high", "max"] if m == "zai-glm-5-3" else ["none", "high"]}
    if provider == "Mistral AI" and feature.get("function_calling") is False: fields -= {"tools", "tool_choice"}
    if provider == "Fireworks AI" and raw.get("supportsTools") is False: fields -= {"tools", "tool_choice"}
    if provider == "Fireworks AI":
        style = (raw.get("conversationConfig") or {}).get("style", "").lower()
        leaf = m.rsplit("/", 1)[-1]
        hybrid = style.startswith(("qwen3", "deepseek-v3", "deepseek-v4", "glm", "kimi-k3")) or leaf.startswith(("qwen3", "deepseek-v3p", "deepseek-v4", "glm-4p", "glm-5", "kimi-k3"))
        mandatory = leaf.startswith(("gpt-oss-", "minimax-m2")) or style == "harmony"
        if (hybrid or mandatory) and style != "qwen3-no-thinking":
            fields |= {"reasoning", "reasoning_effort", "thinking"}
            efforts = ["low", "medium", "high"] if mandatory else ["none", "low", "medium", "high", "xhigh", "max"]
            reasoning_options = {"mandatory": mandatory, "supported_efforts": efforts, "supports_budget": hybrid and ("qwen3" in style or leaf.startswith("qwen3"))}
    params = {name: copy.deepcopy(SCHEMAS[name]) for name in sorted(fields)}
    if provider == "Fireworks AI": params["top_k"]["minimum"] = -1
    if provider == "Anthropic" and "temperature" in params: params["temperature"]["maximum"] = 1
    if provider == "Google Gemini" and "maxTemperature" in raw: params["temperature"]["maximum"] = raw["maxTemperature"]
    if "reasoning_effort" in params and reasoning_options.get("supported_efforts"):
        params["reasoning_effort"]["enum"] = reasoning_options["supported_efforts"]
    endpoint = {"id": provider, "name": provider, "parameters": list(params), "context_length": context, "max_tokens": maximum}
    return {"provider": provider, "model": model, "input_modalities": modalities, "endpoints": [endpoint], "parameters": params,
            "source": "Provider model metadata and reviewed API documentation; undocumented capabilities are not assumed.",
            "documentation": SOURCES[provider], "record_updated": "2026-10-04T00:00:00Z", "reasoning_options": reasoning_options,
            "native_thinking": thinking, "creativity_supported": provider != "Anthropic"}
