# RM-ComfyUI-LLM 0.3.0

**Version:** 0.3.0  
**Node:** `RM_LLM_V3`  
**Display name:** RM-LLM 0.3.0
**Category:** `RM/API`

A lightweight ComfyUI node for calling OpenRouter, Featherless, and LithosAI chat models. It supports live model discovery, model-specific controls, text prompts, supported image/video inputs, reasoning/thinking controls, streaming console output, and ComfyUI input connections.

## Install

Copy this folder into:

```text
ComfyUI/custom_nodes/RM-Comfyui-LLM
```

Restart ComfyUI and refresh the browser. The node is available under **RM/API → RM-LLM 0.3.0**.

The package uses dependencies already provided by ComfyUI. It does not download models or install Python packages.

## Providers

| Provider | API base | Default environment variable |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Featherless | `https://api.featherless.ai/v1` | `FEATHERLESS_API_KEY` |
| LithosAI | `https://api.lithosai.cloud/v1` | `LITHOSAI_API_KEY` |

Click **Model Name** to download the provider's current model catalog. Select a model to load its available controls and media capabilities.

## API keys

The node reads the key from the selected environment variable. Keys are never written to workflows.

RM-LLM 0.3.0 has one masked API-key field and a **Set** button. **API Key System** controls the destination: **Environment variable** places it in the running ComfyUI process without administrator or `sudo` access; **Masked session key** keeps it only in server memory for the current session. The key is not written to disk or saved in workflows. Environment setup must be repeated after restarting ComfyUI.

For persistent use, set the environment variable outside ComfyUI before starting it. The variable name can be changed in the node's **API Key System** section.

## Using the node

1. Select a provider and model.
2. Enter a system prompt and user prompt.
3. Connect an image or video only when the selected model advertises that input.
4. Adjust **Creativity**, **Thinking/Reasoning**, or model-specific controls.
5. Enable **Live console output** when you want streamed text and reasoning printed as it arrives.
6. Queue the workflow.

All visible settings can be connected to other ComfyUI nodes. Unsupported settings are rejected with a clear error. Empty settings are omitted so the provider can use its own defaults.

The outputs are:

- `response` — generated text
- `reasoning` — returned reasoning, when supplied by the model
- `response_json` — the complete provider response, including usage and tool calls when supplied

RM-LLM sends tool calls back in `response_json`; it does not execute external tools itself.

## Supported behavior

- OpenRouter endpoint routing and reasoning metadata.
- Featherless `chat_template_kwargs` discovery and thinking controls.
- LithosAI OpenAI-compatible chat controls, including `reasoning_effort`, sampling, token limits, tools, response formats, and streaming.
- Bounded retries for documented rate-limit and provider-server errors.
- Optional image and native video input where the selected provider/model supports it.
- Environment-variable credentials and temporary masked session credentials.

LithosAI currently reports text-only input because its published API documentation does not define image or video message parts.

## Compatibility

The node is designed for current ComfyUI installations with the standard `aiohttp`, NumPy, Pillow, PyTorch, and ComfyUI video APIs. The included PowerShell launcher is optional and Windows-specific; the node itself uses relative paths and environment variables.

`RM_LLM_V2` remains registered as a legacy node for existing v2 workflows. New workflows should use `RM_LLM_V3` (displayed as **RM-LLM 0.3.0**).

## License

MIT License. See [LICENSE](LICENSE).

## Documentation

- [OpenRouter API](https://openrouter.ai/docs)
- [Featherless API](https://featherless.ai/docs)
- [LithosAI API](https://docs.lithosai.com/)
- [LithosAI OpenAPI schema](https://docs.lithosai.com/openapi.yaml)
- [ComfyUI custom-node guide](https://docs.comfy.org/custom-nodes/walkthrough)
