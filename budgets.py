"""Token allowances and usage reporting; no tokenizer downloads or extra API calls."""
import copy
import json
import math

from .service import RMError

BUDGET_NAMES = ("input_budget", "thinking_budget", "output_budget")


def validate_budgets(values):
    for name, value in zip(BUDGET_NAMES, values):
        if type(value) is not int or not 0 <= value <= 2**31 - 1:
            raise RMError(f"{name} must be a nonnegative whole number. Use 0 for automatic.")


def text_tokens(text):
    # A rough UTF-8 estimate, not a provider tokenizer. Works without dependencies.
    return math.ceil(len(text.encode("utf-8")) / 4) if text else 0


def estimate_input(body):
    media = False

    def strip(value):
        nonlocal media
        if isinstance(value, dict):
            if value.get("type") in {"image_url", "video_url", "input_image", "input_audio"}:
                media = True
                return "[media]"
            return {k: strip(v) for k, v in value.items()}
        if isinstance(value, list):
            return [strip(v) for v in value]
        if isinstance(value, str) and value.startswith("data:"):
            media = True
            return "[media]"
        return value

    content = {k: strip(body[k]) for k in ("messages", "instructions", "input", "tools", "response_format") if k in body}
    return text_tokens(json.dumps(content, ensure_ascii=False)), media


def thinking_state(parameters, caps):
    reasoning = parameters.get("reasoning") or {}
    template = parameters.get("chat_template_kwargs") or {}
    native = parameters.get("thinking") or {}
    config = parameters.get("thinking_config") or {}
    disabled = (reasoning.get("enabled") is False or reasoning.get("effort") == "none"
                or parameters.get("reasoning_effort") == "none" or native.get("type") == "disabled"
                or config.get("thinkingBudget") == 0
                or any(template.get(k) is False for k in ("enable_thinking", "thinking", "do_reasoning")))
    supported = ("reasoning" in caps.get("parameters", {}) or "thinking" in caps.get("parameters", {})
                 or any(k in caps.get("template_parameters", {}) for k in ("enable_thinking", "thinking", "do_reasoning")))
    explicit = (reasoning.get("enabled") is True or reasoning.get("max_tokens") or reasoning.get("effort")
                or parameters.get("reasoning_effort") or native.get("type") in {"enabled", "adaptive"}
                or config or any(template.get(k) is True for k in ("enable_thinking", "thinking", "do_reasoning")))
    if not explicit and (caps.get("reasoning_options", {}).get("default_enabled") is False or caps.get("provider") == "Anthropic"):
        disabled = True
    return supported and not disabled


def thinking_mode(provider, model, caps):
    """Only send a numeric thinking control when its API contract supports one."""
    options = caps.get("reasoning_options", {})
    if provider == "OpenRouter":
        return "numeric" if options.get("supports_max_tokens") is True else "allowance"
    if provider == "Anthropic":
        native = caps.get("native_thinking") or {}
        adaptive = (native.get("types", {}).get("adaptive") or {}).get("supported")
        return "allowance" if adaptive or model.startswith(("claude-opus-4-6", "claude-sonnet-4-6", "claude-opus-5")) else "numeric"
    if provider == "Google Gemini":
        return "numeric" if model.removeprefix("models/").startswith("gemini-2.5-") else "allowance"
    if provider == "Fireworks AI" and options.get("supports_budget"):
        return "numeric"
    return "allowance"


def apply_budgets(provider, model, caps, parameters, input_budget=0, thinking_budget=0, output_budget=0, *, responses=False, endpoint="Auto"):
    validate_budgets((input_budget, thinking_budget, output_budget))
    result = copy.deepcopy(parameters)
    for name in ("reasoning", "thinking", "thinking_config", "chat_template_kwargs"):
        if name in result and not isinstance(result[name], dict):
            raise RMError(f"{name} must be a JSON object.")
    active = thinking_state(result, caps)
    mode = thinking_mode(provider, model, caps) if active else "off"
    existing = (result.get("reasoning", {}).get("max_tokens") or result.get("thinking", {}).get("budget_tokens")
                or result.get("thinking_config", {}).get("thinkingBudget") or 0)
    if type(existing) is not int:
        raise RMError("The existing thinking token limit must be a whole number.")
    if provider == "Anthropic" and mode == "numeric" and result.get("reasoning", {}).get("enabled") is True and not existing:
        existing = 1024
    allowance = (thinking_budget or max(0, existing)) if active else 0
    if thinking_budget and active and mode == "numeric":
        # A budget is more explicit than effort. Preserve other native options.
        if provider == "Anthropic" and "thinking" in result:
            if result["thinking"].get("type") == "adaptive":
                mode = "allowance"
            else:
                result["thinking"].update(type="enabled", budget_tokens=allowance)
        elif provider == "Google Gemini" and "thinking_config" in result:
            result["thinking_config"].pop("thinkingLevel", None)
            result["thinking_config"]["thinkingBudget"] = allowance
        else:
            reasoning = result.setdefault("reasoning", {})
            reasoning.pop("effort", None)
            reasoning.update(enabled=True, max_tokens=allowance)
            result.pop("reasoning_effort", None)
        if provider == "Anthropic" and mode == "numeric" and allowance < 1024:
            raise RMError("Thinking budget must be at least 1024 for this Claude model.")
    maximum = next((result[k] for k in ("max_completion_tokens", "max_tokens", "max_output_tokens") if result.get(k) is not None), None)
    if maximum is not None and (type(maximum) is not int or maximum < 1):
        raise RMError("The existing output token limit must be a positive whole number.")
    if output_budget:
        total = output_budget + allowance
        fields = caps.get("parameters", {})
        key = "max_output_tokens" if responses else "max_tokens" if "max_tokens" in fields else "max_completion_tokens"
        if not responses and key not in fields:
            raise RMError("This model does not advertise an output token limit. Set Output budget to 0.")
        for name in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
            result.pop(name, None)
        result[key] = maximum = total
    if provider == "Anthropic" and not maximum:
        maximum = min(4096, caps.get("endpoints", [{}])[0].get("max_tokens") or 4096)
    if (thinking_budget or output_budget) and allowance and mode == "numeric" and maximum and allowance >= maximum:
        raise RMError("Thinking budget needs room for an answer. Increase Output budget or the existing token limit.")
    limits = [ep["max_tokens"] for ep in caps.get("endpoints", []) if type(ep.get("max_tokens")) is int and ep["max_tokens"] > 0]
    if output_budget and limits and maximum > max(limits):
        raise RMError("Thinking and Output budgets exceed the advertised generation limit. Reduce the budgets.")
    plan = {
        "input": input_budget, "thinking": allowance, "output": output_budget,
        "thinking_mode": mode, "generation_limit": maximum,
        "thinking_possible": active,
    }
    endpoints = [ep for ep in caps.get("endpoints", []) if endpoint == "Auto" or ep["id"] == endpoint]
    def advertised(name):
        return max((ep[name] for ep in endpoints if type(ep.get(name)) is int and ep[name] > 0), default=0)
    # Display scales only: these values never become request parameters or guards.
    plan["display_limits"] = {"input": advertised("context_length"),
                              "thinking": maximum or advertised("max_tokens"),
                              "output": maximum or advertised("max_tokens")}
    if not plan["output"] and maximum:
        plan["output"] = max(0, maximum - plan["thinking"])
    if mode == "numeric" and not plan["thinking"]:
        plan["thinking_mode"] = "allowance"
    return result, plan


def check_input(body, plan):
    estimated, media = estimate_input(body)
    plan.update(input_estimate=estimated, input_has_media=media)
    if plan["input"] and estimated > plan["input"]:
        raise RMError("Input budget exceeded (estimated). Increase Input budget or shorten the prompt. No generation sent.")


def usage_report(provider, result, plan, content="", reasoning=""):
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}

    def count(obj, *names):
        for name in names:
            value = obj.get(name)
            if type(value) is int and value >= 0:
                return value
        return None

    total = count(usage, "completion_tokens", "output_tokens")
    used_input = count(usage, "prompt_tokens", "input_tokens")
    details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    if not isinstance(details, dict):
        details = {}
    used_thinking = count(details, "reasoning_tokens", "thinking_tokens")
    if used_thinking is None:
        used_thinking = count(usage, "reasoning_tokens")
    used_output = None
    if provider == "Google Gemini":
        used_input = count(usage, "promptTokenCount")
        used_thinking = count(usage, "thoughtsTokenCount")
        used_output = count(usage, "candidatesTokenCount")
    if provider == "Anthropic" and used_input is not None:
        used_input += (count(usage, "cache_creation_input_tokens") or 0) + (count(usage, "cache_read_input_tokens") or 0)
    input_source = "API usage" if used_input is not None else "Estimated text usage; media not counted" if plan.get("input_has_media") else "Estimated usage"
    if used_input is None:
        used_input = plan.get("input_estimate", 0)
    thinking_source = "API usage"
    if used_thinking is None:
        if reasoning:
            used_thinking = text_tokens(reasoning)
            thinking_source = "Estimated from returned reasoning; hidden thinking may differ"
        elif not plan["thinking_possible"]:
            used_thinking = 0
            thinking_source = "Thinking is off or not advertised"
        else:
            thinking_source = "Thinking usage not reported"
    output_source = "API usage"
    if used_output is None:
        if total is not None and used_thinking is not None and thinking_source == "API usage":
            used_output = max(0, total - used_thinking)
        elif total is not None and not plan["thinking_possible"]:
            used_output = total
        else:
            used_output = text_tokens(content)
            output_source = "Estimated from returned output"
    notes = {
        "input": "Estimated preflight check; never truncates prompts. Media tokens are checked only by the provider.",
        "thinking": "Numeric thinking target sent to API; provider rules apply." if plan["thinking_mode"] == "numeric" else "Planning allowance; no separate API cap." if plan["thinking_mode"] == "allowance" else "Thinking is off or not advertised.",
        "output": "Shares the generation limit with thinking; the split is not guaranteed." if plan["thinking_possible"] else "Generation limit sent to API when configured.",
    }
    report = {}
    for name, used, source in (("input", used_input, input_source), ("thinking", used_thinking, thinking_source), ("output", used_output, output_source)):
        budget = plan[name]
        scale = budget or plan.get("display_limits", {}).get(name) or 0
        scale_source = "budget" if budget else "model_limit" if scale else "estimated"
        if not scale:
            # Round up to a power of two; a visual reference, never a claimed cap.
            scale = max(1024, 1 << max(0, (used or 1) - 1).bit_length())
        fraction = min(1.0, used / scale) if used is not None else 0
        note = " Usage exceeded this allowance." if budget and used is not None and used > budget else ""
        if not budget:
            note = " Automatic display scale: " + ("known context/generation limit" if scale_source == "model_limit" else "estimated from this run") + "; no new request limit."
        report[name] = {"budget": budget, "scale": scale, "scale_source": scale_source, "used": used, "fraction": fraction, "tooltip": f"{source}. {notes[name]}{note}"}
    return report
