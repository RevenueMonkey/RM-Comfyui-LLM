import asyncio
import base64
import io
import json
import logging
import math

import numpy as np
from PIL import Image
import comfy.model_management
from comfy_api.latest import VideoContainer, VideoCodec

from .service import RMError, ProviderHTTPError, consume_key, model_capabilities, provider_info, request_json, read_records, DETAILS, LOCK
from .streaming import request_stream
from .template_options import FIELDS as TEMPLATE_FIELDS, PREFIX as TEMPLATE_PREFIX

MEDIA_LIMIT = 48 * 1024 * 1024
RESERVED_INPUTS = {"provider", "model", "models", "messages", "stream", "stream_options", "route", "model_name", "endpoint", "api_key_env", "credential_source", "system_prompt", "user_prompt", "parameters_json", "timeout_seconds", "image", "video", "key_ticket", "console_output"}


def parameter_sockets():
    definitions = {TEMPLATE_PREFIX + name: schema for name, schema in TEMPLATE_FIELDS.items()}
    for record in read_records().values():
        definitions.update(record["parameters"])
    with LOCK:
        for _, caps in DETAILS.values():
            definitions.update(caps["parameters"])
            definitions.update({TEMPLATE_PREFIX + name: schema for name, schema in caps.get("template_parameters", {}).items()})
    sockets = {}
    for name, schema in definitions.items():
        if name in RESERVED_INPUTS or name == "structured_outputs":
            continue
        kinds = schema.get("type", [])
        kinds = [kinds] if isinstance(kinds, str) else kinds
        kinds = set(kinds) - {"null"}
        socket = "INT" if kinds == {"integer"} else "FLOAT" if kinds == {"number"} else "BOOLEAN" if kinds == {"boolean"} else "STRING"
        sockets[name] = (socket, {"forceInput": True, "tooltip": schema.get("description", "Model setting. Structured values are supplied as JSON text.")})
    return sockets


def merge_connected_parameters(parameters, connected, caps):
    if not isinstance(parameters, dict):
        raise RMError("Model settings must be a JSON object.")
    parameters = dict(parameters)
    for name, value in connected.items():
        if name.startswith(TEMPLATE_PREFIX) or name == "reasoning.enabled":
            continue
        if name not in caps["parameters"]:
            raise RMError(f"Connected setting {name} is unsupported by the selected model. Disconnect it or select a compatible model.")
        schema = caps["parameters"][name]
        kinds = schema.get("type", [])
        kinds = [kinds] if isinstance(kinds, str) else kinds
        kinds = set(kinds) - {"null"}
        if isinstance(value, str) and kinds != {"string"} and not (schema.get("enum") and all(v is None or isinstance(v, str) for v in schema["enum"])):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise RMError(f"Connected setting {name} requires valid JSON text.") from None
        parameters[name] = value
    nested = {name[len(TEMPLATE_PREFIX):]: value for name, value in connected.items() if name.startswith(TEMPLATE_PREFIX)}
    if nested:
        options = parameters.get("chat_template_kwargs", {})
        if not isinstance(options, dict):
            raise RMError("chat_template_kwargs must be a JSON object.")
        options = dict(options)
        for name, value in nested.items():
            if name not in caps.get("template_parameters", {}):
                raise RMError(f"Connected chat-template option {name} is not known for the selected model. Refresh capabilities or disconnect it.")
            if name == "enable_thinking":
                options.pop("thinking", None)
                options.pop("do_reasoning", None)
            options[name] = value
        parameters["chat_template_kwargs"] = options
    if "reasoning.enabled" in connected:
        if caps.get("provider") != "OpenRouter" or "reasoning" not in caps["parameters"]:
            raise RMError("Thinking/Reasoning is unsupported by the selected model. Disconnect its input or select a compatible model.")
        options = parameters.get("reasoning", {})
        if not isinstance(options, dict):
            raise RMError("reasoning must be a JSON object.")
        enabled = connected["reasoning.enabled"]
        if type(enabled) is not bool:
            raise RMError("Thinking/Reasoning must be a boolean (On or Off).")
        options = dict(options, enabled=enabled)
        if not enabled:
            options.pop("effort", None)
            options.pop("max_tokens", None)
            parameters.pop("reasoning_effort", None)
        elif options.get("effort") == "none":
            options.pop("effort")
        if enabled and parameters.get("reasoning_effort") == "none":
            parameters.pop("reasoning_effort")
        parameters["reasoning"] = options
    return parameters


def validate_value(name, value, schema):
    kinds = schema.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    valid = {"null": value is None, "boolean": isinstance(value, bool), "integer": type(value) is int, "number": type(value) in (int, float), "string": isinstance(value, str), "array": isinstance(value, list), "object": isinstance(value, dict)}
    if kinds and not any(valid.get(k, True) for k in kinds):
        raise RMError(f"{name} has the wrong JSON type.")
    if type(value) in (int, float) and not math.isfinite(value):
        raise RMError(f"{name} must be finite.")
    if "enum" in schema and value not in schema["enum"]:
        raise RMError(f"{name} is not an advertised option.")
    if type(value) in (int, float) and "minimum" in schema and value < schema["minimum"]:
        raise RMError(f"{name} must be at least {schema['minimum']}.")


class LimitedBuffer(io.BytesIO):
    def write(self, value):
        if self.tell() + len(value) > MEDIA_LIMIT:
            raise RMError("Encoded media exceeds 48 MiB. Resize images or trim/compress the video.")
        return super().write(value)


def image_parts(images):
    if images.ndim != 4 or images.shape[-1] not in (1, 3, 4) or images.shape[0] < 1:
        raise RMError("image must be a nonempty ComfyUI IMAGE batch [batch, height, width, channels].")
    parts = []
    total = 0
    for frame in images:
        comfy.model_management.throw_exception_if_processing_interrupted()
        pixels = np.clip(frame.detach().cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
        if pixels.shape[-1] == 1:
            pixels = pixels[:, :, 0]
        buffer = LimitedBuffer()
        Image.fromarray(pixels).save(buffer, format="PNG")
        total += buffer.tell()
        if total > MEDIA_LIMIT:
            raise RMError("Image batch exceeds 48 MiB. Reduce the number or resolution of images.")
        parts.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")}})
    return parts


def video_part(video):
    buffer = LimitedBuffer()
    video.save_to(buffer, format=VideoContainer.MP4, codec=VideoCodec.H264)
    return {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")}}


def validate_parameters(parameters, caps, endpoint):
    if not isinstance(parameters, dict):
        raise RMError("Model settings must be a JSON object.")
    selected = next((ep for ep in caps["endpoints"] if ep["id"] == endpoint), None)
    if endpoint != "Auto" and selected is None:
        raise RMError("The selected hosting endpoint is no longer available. Refresh and select an endpoint.")
    allowed = set(selected["parameters"] if selected else caps["parameters"])
    if set(parameters) - allowed or "structured_outputs" in parameters:
        raise RMError("One or more enabled settings are unsupported by this model/endpoint. Refresh capabilities and review settings.")
    for name, value in parameters.items():
        schema = caps["parameters"].get(name, {})
        validate_value(name, value, schema)
    reasoning = parameters.get("reasoning") or {}
    if isinstance(reasoning, dict):
        if "enabled" in reasoning and type(reasoning["enabled"]) is not bool:
            raise RMError("reasoning.enabled must be a boolean (On or Off).")
        if caps.get("reasoning_options", {}).get("mandatory") and (reasoning.get("enabled") is False or reasoning.get("effort") == "none" or parameters.get("reasoning_effort") == "none"):
            raise RMError("This model requires reasoning and cannot turn Thinking/Reasoning off.")
    for name, schema in caps.get("template_parameters", {}).items():
        options = parameters.get("chat_template_kwargs") or {}
        if name in options:
            validate_value(TEMPLATE_PREFIX + name, options[name], schema)
    ranges = {"temperature": (0, 2), "top_p": (0, 1), "min_p": (0, 1), "top_a": (0, 1), "frequency_penalty": (-2, 2), "presence_penalty": (-2, 2), "repetition_penalty": (0, 2), "top_logprobs": (0, 20), "max_tokens": (1, 2**31-1), "max_completion_tokens": (1, 2**31-1)}
    for name, (minimum, maximum) in ranges.items():
        if name in parameters and parameters[name] is not None:
            value = parameters[name]
            if type(value) not in (int, float) or not minimum <= value <= maximum:
                raise RMError(f"{name} must be between {minimum} and {maximum}.")
    if "max_tokens" in parameters and "max_completion_tokens" in parameters:
        raise RMError("Enable only one token-limit parameter.")
    limit = selected.get("max_tokens") if selected else max((ep.get("max_tokens") or 0 for ep in caps["endpoints"]), default=0)
    if limit and max(parameters.get("max_tokens") or 0, parameters.get("max_completion_tokens") or 0) > limit:
        raise RMError(f"The advertised output limit is {limit} tokens.")
    return parameters


def build_body(provider, model, endpoint, caps, system_prompt, user_prompt, parameters, image=None, video=None):
    parameters = validate_parameters(parameters, caps, endpoint)
    modalities = caps["input_modalities"]
    image_supported = image is not None and "image" in modalities
    video_supported = video is not None and provider == "OpenRouter" and "video" in modalities
    # Keep a connected media socket stable when a model is changed.  The
    # frontend marks that socket N/A, and the request remains a valid text
    # request with the unsupported media omitted.
    if image is not None and not image_supported:
        logging.warning("[RM-LLM] Image input is connected but unsupported by %s/%s; omitting it.", provider, model)
    if video is not None and not video_supported:
        logging.warning("[RM-LLM] Video input is connected but unsupported by %s/%s; omitting it.", provider, model)
    merge_system = provider == "Featherless" and caps.get("system_role_rejected") is True
    user_content = system_prompt + "\n\n" + user_prompt if merge_system and system_prompt else user_prompt
    content = [{"type": "text", "text": user_content}]
    if image_supported:
        content.extend(image_parts(image))
    if video_supported:
        content.append(video_part(video))
    messages = []
    if system_prompt and not merge_system:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content if len(content) > 1 else user_content})
    body = {"model": model, "messages": messages, "stream": False, **parameters}
    if provider == "OpenRouter":
        body["provider"] = {"require_parameters": True}
        if endpoint != "Auto":
            body["provider"].update({"only": [endpoint], "allow_fallbacks": False})
    return body


async def interruptible(coroutine):
    task = asyncio.create_task(coroutine)
    try:
        while not task.done():
            comfy.model_management.throw_exception_if_processing_interrupted()
            await asyncio.wait({task}, timeout=0.25)
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def request_completion(provider, url, key, body, timeout):
    deadline = asyncio.get_running_loop().time() + timeout
    for attempt in range(4):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise RMError("The request timeout expired while waiting for Featherless model capacity.")
        try:
            request = request_stream if body.get("stream") else request_json
            return await request(url, key, body, remaining)
        except ProviderHTTPError as error:
            retryable = provider == "Featherless" and error.status == 503
            retryable = retryable or (provider == "LithosAI" and error.status in {429, 500, 502, 503, 504})
            if not retryable:
                raise
            if attempt == 3:
                label = "LithosAI retry budget" if provider == "LithosAI" else "Featherless capacity retries"
                raise RMError(f"{error} {label} exhausted after 4 attempts for {body['model']}. Try again later or select another model.") from None
            delay = error.retry_after if error.retry_after is not None else 5 * 2**attempt
            remaining = deadline - asyncio.get_running_loop().time()
            if delay >= remaining:
                raise RMError(f"{error} The request timeout leaves no time for another capacity retry.") from None
            logging.warning("[RM-LLM] %s HTTP %s: retry %s/3 in %.1f seconds.", provider, error.status, attempt + 1, delay)
            await asyncio.sleep(delay)


class RMLLM:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "provider": ("STRING", {"default": "OpenRouter"}),
                "model_name": ("STRING", {"default": "", "tooltip": "Click model_name in the RM-LLM panel to fetch and search the complete provider catalog."}),
                "endpoint": ("STRING", {"default": "Auto"}),
                "api_key_env": ("STRING", {"default": "OPENROUTER_API_KEY", "tooltip": "Environment variable NAME only. The server reads its value; it is never sent to the browser."}),
                "credential_source": ("STRING", {"default": "Environment variable"}),
                "system_prompt": ("STRING", {"default": "You are a helpful assistant.", "multiline": True}),
                "user_prompt": ("STRING", {"default": "", "multiline": True}),
                "parameters_json": ("STRING", {"default": "{}", "multiline": True}),
                "timeout_seconds": ("INT", {"default": 300, "min": 10, "max": 3600}),
            },
            "optional": {
                "image": ("IMAGE",),
                "video": ("VIDEO",),
                "key_ticket": ("STRING", {"default": ""}),
                "console_output": ("BOOLEAN", {"default": False, "label_on": "On", "label_off": "Off", "tooltip": "Stream generated text and returned reasoning live to the ComfyUI console."}),
                **parameter_sockets(),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("response", "reasoning", "response_json")
    FUNCTION = "generate"
    CATEGORY = "RM/API"
    OUTPUT_NODE = True
    DESCRIPTION = "Featherless and OpenRouter LLM calls with live models, endpoint capabilities, optional image/video input, and server-side credentials. Each queue action makes a new request."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    async def generate(self, provider, model_name, endpoint, api_key_env, credential_source, system_prompt, user_prompt, parameters_json, timeout_seconds, image=None, video=None, key_ticket="", console_output=False, **connected_parameters):
        if type(console_output) is not bool:
            raise RMError("console_output must be a boolean (On or Off).")
        started = asyncio.get_running_loop().time()
        base, _ = provider_info(provider)
        if credential_source not in {"Environment variable", "Masked session key"}:
            raise RMError("credential_source must be Environment variable or Masked session key.")
        if credential_source == "Masked session key" and not key_ticket:
            raise RMError("API Key Needed!")
        key = consume_key(provider, key_ticket, api_key_env)
        try:
            parameters = json.loads(parameters_json)
        except json.JSONDecodeError:
            raise RMError("Model settings are not valid JSON.") from None
        if console_output:
            logging.info("[RM-LLM] Checking %s model capabilities.", provider)
        caps = await interruptible(model_capabilities(provider, model_name, key=key))
        parameters = merge_connected_parameters(parameters, connected_parameters, caps)
        body = build_body(provider, model_name, endpoint, caps, system_prompt, user_prompt, parameters, image, video)
        body["stream"] = console_output
        if console_output:
            logging.info("[RM-LLM] Streaming from %s; waiting for the first generated text.", provider)
        result = await interruptible(request_completion(provider, base + "/chat/completions", key, body, timeout_seconds))
        if not isinstance(result.get("choices"), list) or not result["choices"]:
            raise RMError("Provider returned no completion choices.")
        message = result["choices"][0].get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        if not reasoning:
            reasoning = "\n".join(part.get("text", "") for part in message.get("reasoning_details", []) if isinstance(part, dict))
        # Redact even a provider accidentally echoing its Authorization value.
        content = str(content).replace(key, "[REDACTED]")
        reasoning = str(reasoning).replace(key, "[REDACTED]")
        response_json = json.dumps(result, ensure_ascii=False).replace(json.dumps(key, ensure_ascii=False)[1:-1], "[REDACTED]")
        if console_output:
            logging.info("[RM-LLM] Completed in %.2f seconds.", asyncio.get_running_loop().time() - started)
        return {"ui": {"text": [content]}, "result": (content, reasoning, response_json)}
