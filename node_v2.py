import json
import math

from comfy_execution.utils import get_executing_context
from server import PromptServer

from .node import RMLLM
from .agent import AgentRequest
from .service import RMError


def creativity_to_sampling(creativity):
    if type(creativity) not in (int, float) or not math.isfinite(creativity):
        raise RMError("Creativity must be a finite number from 0 to 100.")
    c = max(0.0, min(100.0, creativity)) / 100.0
    return {"temperature": math.floor(0.2 * 6.0 ** c * 100 + 0.5) / 100, "top_p": math.floor((1.0 - 0.1 * 10.0 ** (-c)) * 100 + 0.5) / 100}


class RMLLMV2(RMLLM):
    @classmethod
    def INPUT_TYPES(cls):
        inputs = super().INPUT_TYPES()
        inputs["optional"]["creativity"] = ("FLOAT", {
            "forceInput": True, "min": 0.0, "max": 100.0,
            "tooltip": "0–100: sets Temperature and top_p. Individually connected sampling inputs take precedence.",
        })
        inputs["optional"]["reasoning.enabled"] = ("BOOLEAN", {"forceInput": True, "tooltip": "Enable OpenRouter reasoning when supported by the selected model."})
        inputs["optional"]["agent_request"] = ("RM_LLM_AGENT_REQUEST", {
            "tooltip": "A connected tool conversation uses the Responses transport. System/user prompts and model settings remain on this RM-LLM node."})
        inputs["hidden"] = {"dynprompt": "DYNPROMPT"}
        return inputs

    async def generate(self, parameters_json, creativity=None, agent_request=None, dynprompt=None, **kwargs):
        model_info = {"provider": kwargs.get("provider"), "model": kwargs.get("model_name")}
        context = get_executing_context()
        if context is not None:
            display_id = dynprompt.get_display_node_id(context.node_id) if dynprompt is not None else context.node_id
            PromptServer.instance.send_sync("rm-llm-model", {
                "node": display_id, "model_info": model_info,
            }, PromptServer.instance.client_id)
        if creativity is not None:
            try:
                parameters = json.loads(parameters_json)
            except json.JSONDecodeError:
                raise RMError("Model settings are not valid JSON.") from None
            if not isinstance(parameters, dict):
                raise RMError("Model settings must be a JSON object.")
            parameters.update(creativity_to_sampling(creativity))
            parameters_json = json.dumps(parameters)
        if agent_request is not None:
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
            connected = {name: value for name, value in kwargs.items() if name not in {
                "provider", "model_name", "endpoint", "api_key_env", "credential_source",
                "system_prompt", "user_prompt", "timeout_seconds", "image", "video", "key_ticket", "console_output"}}
            if connected or kwargs.get("video") is not None:
                raise RMError("For tool conversations, put model settings in parameters_json; video input is not supported.")
            profile = dict(provider=kwargs["provider"], model=kwargs["model_name"], endpoint=kwargs["endpoint"],
                api_key_env=kwargs["api_key_env"], reasoning_effort=reasoning.get("effort", "medium"),
                max_output_tokens=maximum, input_ceiling=agent_request["input_ceiling"],
                timeout_seconds=kwargs["timeout_seconds"], extra_parameters=parameters, reasoning=reasoning)
            request = dict(instructions=kwargs["system_prompt"], input=conversation, tools=agent_request["tools"])
            result, = await AgentRequest().request(profile, request, image=kwargs.get("image"))
            text = result.get("text", "")
            report = text or json.dumps(result.get("calls") or {"status": result["status"], "message": result.get("message", "")}, ensure_ascii=False)
            return {"ui": {"text": [report], "rm_llm_model": [model_info]}, "result": (text, "", json.dumps(result, ensure_ascii=False))}
        result = await super().generate(parameters_json=parameters_json, **kwargs)
        if model_info["provider"] and model_info["model"]:
            result["ui"]["rm_llm_model"] = [model_info]
        return result
