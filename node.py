import asyncio
import base64
import io
import json
import logging
import math

import numpy as np
from PIL import Image
from comfy_execution.utils import get_executing_context
from server import PromptServer
import comfy.model_management
from comfy_api.latest import VideoContainer, VideoCodec

from .service import RMError, ProviderHTTPError, consume_key, model_capabilities, provider_info, request_json, read_records, DETAILS, LOCK
from .streaming import request_stream
from . import providers as adapters
from .provider_transport import complete as provider_complete
from .template_options import FIELDS as TEMPLATE_FIELDS, PREFIX as TEMPLATE_PREFIX
from .budgets import BUDGET_NAMES, apply_budgets, check_input, usage_report

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
        if "reasoning" not in caps["parameters"]:
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
    if type(value) in (int, float) and "maximum" in schema and value > schema["maximum"]:
        raise RMError(f"{name} must be at most {schema['maximum']}.")


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
    video_supported = video is not None and provider in {"OpenRouter", "Google Gemini"} and "video" in modalities
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


class ChatCompletionNode:
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
                "user_prompt": ("STRING", {"default": "Please respond to the following request.", "multiline": True}),
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

    async def generate(self, provider, model_name, endpoint, api_key_env, credential_source, system_prompt, user_prompt, parameters_json, timeout_seconds, image=None, video=None, key_ticket="", console_output=False, input_budget=0, thinking_budget=0, output_budget=0, **connected_parameters):
        if type(console_output) is not bool:
            raise RMError("console_output must be a boolean (On or Off).")
        started = asyncio.get_running_loop().time()
        base, _ = provider_info(provider)
        if credential_source not in {"Environment variable", "Masked session key"}:
            raise RMError("credential_source must be Environment variable or Masked session key.")
        if credential_source == "Masked session key" and not key_ticket:
            raise RMError("API Key Needed!")
        key = consume_key(provider, key_ticket if credential_source == "Masked session key" else "", api_key_env)
        try:
            parameters = json.loads(parameters_json)
        except json.JSONDecodeError:
            raise RMError("Model settings are not valid JSON.") from None
        if console_output:
            logging.info("[RM-LLM] Checking %s model capabilities.", provider)
        caps = await interruptible(model_capabilities(provider, model_name, key=key))
        parameters = merge_connected_parameters(parameters, connected_parameters, caps)
        parameters, budget_plan = apply_budgets(provider, model_name, caps, parameters, input_budget, thinking_budget, output_budget, endpoint=endpoint)
        body = build_body(provider, model_name, endpoint, caps, system_prompt, user_prompt, parameters, image, video)
        check_input(body, budget_plan)
        body["stream"] = console_output
        stream_fields = next((ep["parameters"] for ep in caps["endpoints"] if ep["id"] == endpoint), caps["parameters"])
        if console_output and "stream_options" in stream_fields:
            options = body.setdefault("stream_options", {})
            if isinstance(options, dict):
                options.setdefault("include_usage", True)
        if console_output:
            logging.info("[RM-LLM] Streaming from %s; waiting for the first generated text.", provider)
        result = await interruptible(provider_complete(provider, body, caps, key, timeout_seconds) if provider in adapters.PROVIDERS else request_completion(provider, base + "/chat/completions", key, body, timeout_seconds))
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
        usage = usage_report(provider, result, budget_plan, content, reasoning)
        return {"ui": {"text": [content], "rm_llm_usage": [usage]}, "result": (content, reasoning, response_json)}


def creativity_to_sampling(creativity):
    if type(creativity) not in (int, float) or not math.isfinite(creativity):
        raise RMError("Creativity must be a finite number from 0 to 100.")
    c = max(0.0, min(100.0, creativity)) / 100.0
    return {
        "temperature": math.floor(0.2 * 6.0 ** c * 100 + 0.5) / 100,
        "top_p": math.floor((1.0 - 0.1 * 10.0 ** (-c)) * 100 + 0.5) / 100,
    }


class ConversationNode(ChatCompletionNode):
    @classmethod
    def INPUT_TYPES(cls):
        inputs = super().INPUT_TYPES()
        inputs["optional"]["creativity"] = ("FLOAT", {
            "forceInput": True, "min": 0.0, "max": 100.0,
            "tooltip": "0–100: sets Temperature and top_p. Individually connected sampling inputs take precedence.",
        })
        inputs["optional"]["reasoning.enabled"] = ("BOOLEAN", {"forceInput": True, "tooltip": "Enable reasoning when supported by the selected model."})
        inputs["optional"]["agent_request"] = ("RM_LLM_AGENT_REQUEST", {"tooltip": "A connected tool conversation uses the Responses transport. System/user prompts and model settings remain on this RM-LLM node."})
        for name in BUDGET_NAMES:
            inputs["optional"][name] = ("INT", {"default": 0, "min": 0, "max": 2**31 - 1,
                "tooltip": "Tokens; 0 keeps existing/default behaviour. Positive budgets take precedence over corresponding token settings. Thinking and output may share one API limit."})
        inputs["hidden"] = {"dynprompt": "DYNPROMPT"}
        return inputs

    async def generate(self, parameters_json, creativity=None, agent_request=None, dynprompt=None, input_budget=0, thinking_budget=0, output_budget=0, **kwargs):
        model_info = {"provider": kwargs.get("provider"), "model": kwargs.get("model_name")}
        context = get_executing_context()
        if context is not None and dynprompt is not None:
            inputs = dynprompt.get_node(context.node_id)["inputs"]
            defaults = {provider_info(provider)[1] for provider in ("OpenRouter", "Featherless", "LithosAI", *adapters.PROVIDERS)}
            # A runtime provider connection owns its default key selection.
            # Explicitly connected/custom environment names keep their meaning.
            if isinstance(inputs.get("provider"), list) and not isinstance(inputs.get("api_key_env"), list) and kwargs.get("api_key_env") in defaults:
                kwargs["api_key_env"] = provider_info(kwargs["provider"])[1]
        if context is not None:
            display_id = dynprompt.get_display_node_id(context.node_id) if dynprompt is not None else context.node_id
            PromptServer.instance.send_sync("rm050-llm-model", {"node": display_id, "model_info": model_info}, PromptServer.instance.client_id)
        if creativity is not None:
            if kwargs.get("provider") == "Anthropic":
                raise RMError("Anthropic does not support paired Creativity sampling. Use temperature or top_p in Advanced.")
            try:
                parameters = json.loads(parameters_json)
            except json.JSONDecodeError:
                raise RMError("Model settings are not valid JSON.") from None
            if not isinstance(parameters, dict):
                raise RMError("Model settings must be a JSON object.")
            parameters.update(creativity_to_sampling(creativity))
            parameters_json = json.dumps(parameters)
        if agent_request is not None:
            # Import lazily: agent.py uses helpers from this module, so a
            # module-level import would prevent RM-LLM from loading at startup.
            from .agent import AgentRequest
            if kwargs["provider"] != "OpenRouter":
                raise RMError("The existing tool-conversation transport supports OpenRouter. Ordinary RM-LLM requests still support the other providers.")
            if kwargs["credential_source"] != "Environment variable":
                raise RMError("Tool conversations require a server-side environment variable credential.")
            try:
                parameters = json.loads(parameters_json)
                conversation = json.loads(kwargs["user_prompt"])
            except (TypeError, json.JSONDecodeError):
                raise RMError("Connected agent settings and conversation must be valid JSON.") from None
            if not isinstance(parameters, dict) or not isinstance(conversation, list):
                raise RMError("Agent settings must be an object and the conversation must be an array.")
            parameters.setdefault("reasoning", {"effort": parameters.get("reasoning_effort", "medium")})
            caps = await interruptible(model_capabilities(kwargs["provider"], kwargs["model_name"]))
            parameters, budget_plan = apply_budgets(kwargs["provider"], kwargs["model_name"], caps, parameters, input_budget, thinking_budget, output_budget, responses=True, endpoint=kwargs["endpoint"])
            if "max_tokens" in parameters and "max_output_tokens" in parameters:
                raise RMError("Set only one output token limit.")
            effort = parameters.pop("reasoning_effort", "medium")
            reasoning = parameters.pop("reasoning", {"effort": effort})
            maximum = parameters.pop("max_tokens", parameters.pop("max_output_tokens", 16384))
            if not isinstance(reasoning, dict):
                raise RMError("reasoning must be a JSON object.")
            if "effort" not in reasoning and effort != "medium":
                reasoning["effort"] = effort
            if type(maximum) is not int or maximum < 1:
                raise RMError("The output token limit must be a positive integer.")
            connected = {name: value for name, value in kwargs.items() if name not in {"provider", "model_name", "endpoint", "api_key_env", "credential_source", "system_prompt", "user_prompt", "timeout_seconds", "image", "video", "key_ticket", "console_output"}}
            if connected or kwargs.get("video") is not None:
                raise RMError("For tool conversations, put model settings in parameters_json; video input is not supported.")
            profile = dict(provider=kwargs["provider"], model=kwargs["model_name"], endpoint=kwargs["endpoint"], api_key_env=kwargs["api_key_env"], reasoning_effort=reasoning.get("effort", "medium"), max_output_tokens=maximum, input_ceiling=agent_request["input_ceiling"], timeout_seconds=kwargs["timeout_seconds"], extra_parameters=parameters, reasoning=reasoning)
            request = dict(instructions=kwargs["system_prompt"], input=conversation, tools=agent_request["tools"])
            check_input(request, budget_plan)
            if kwargs.get("image") is not None:
                budget_plan["input_has_media"] = True
            if input_budget:
                profile["input_ceiling"] = min(profile["input_ceiling"], input_budget)
            if not budget_plan["generation_limit"]:
                budget_plan["generation_limit"] = maximum
                budget_plan["output"] = max(0, maximum - budget_plan["thinking"])
            result, = await AgentRequest().request(profile, request, image=kwargs.get("image"))
            text = result.get("text", "")
            report = text or json.dumps(result.get("calls") or {"status": result["status"], "message": result.get("message", "")}, ensure_ascii=False)
            ui = {"text": [report], "rm_llm_model": [model_info]}
            if result.get("status") in {"complete", "tools"}:
                ui["rm_llm_usage"] = [usage_report(kwargs["provider"], result, budget_plan, text)]
            return {"ui": ui, "result": (text, "", json.dumps(result, ensure_ascii=False))}
        result = await super().generate(parameters_json=parameters_json, input_budget=input_budget, thinking_budget=thinking_budget, output_budget=output_budget, **kwargs)
        if model_info["provider"] and model_info["model"]:
            result["ui"]["rm_llm_model"] = [model_info]
        return result


class RMLLM050(ConversationNode):
    """RM-LLM 0.6.0; compatible IDs with provider request status."""

    DESCRIPTION = (
        "Twelve LLM API providers with model discovery, "
        "dynamic controls, optional media input, and server-side credentials."
    )
