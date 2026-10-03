# RM-ComfyUI-LLM 0.4.0

**Version:** 0.4.0

**Node:** `RM_LLM_040`

**Display name:** RM-LLM 0.4.0

**Category:** `RM/API`

A lightweight ComfyUI node for calling OpenRouter, Featherless, and LithosAI chat models. It supports live model discovery, model-specific controls, text prompts, supported image/video inputs, reasoning/thinking controls, streaming console output, and ComfyUI input connections.

## Install

Copy this folder into:

```text
ComfyUI/custom_nodes/RM-LLM-0.4.0
```

Restart ComfyUI and refresh the browser. The node is available under **RM/API → RM-LLM 0.4.0**.

The package uses dependencies already provided by ComfyUI. It does not download models or install Python packages.

This 0.4.0 copy uses ComfyUI extension hooks, graph events and node-owned widget callbacks. It does not modify another node, replace shared Run functions, or override node prototypes or socket-position methods. Its own response preview works without an output-display package. Sections change row visibility and native height while keeping input sockets and their order stable. Connected inputs remain visible when folded. Socket appearance follows the native renderer.

## Providers

| Provider | API base | Default environment variable |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Featherless | `https://api.featherless.ai/v1` | `FEATHERLESS_API_KEY` |
| LithosAI | `https://api.lithosai.cloud/v1` | `LITHOSAI_API_KEY` |

Type in **Model Name** to filter an inline catalog with up to ten rows visible and scrolling for more. Selecting a model replaces the text. Otherwise your typed model ID remains; press Enter or leave the field to load its controls and media capabilities. You can also connect a native **PrimitiveString** node to **model_name**. Successful catalogs are cached under ComfyUI's user directory and reused after restart.

The centered header shows the provider with its model count, followed by the selected model with its context and output limit. Provider and model names share a font size that adjusts to the available width.

Featherless catalog pages are requested without an API key. Authentication remains enabled for model capability checks and generation, and catalog authentication for OpenRouter and LithosAI is unchanged.

When no catalog is available, the dropdown shows a green download progress bar without numeric labels. Progress uses the reported total when available and an estimate otherwise; its tooltip shows download status. Simultaneous catalog requests share one download. Featherless page requests are spaced at least two seconds apart, and completed pages are retained separately under ComfyUI's user directory so an interrupted download can resume after restart. Progress polling reads local status only; it does not call the provider.

If catalog retrieval fails, the dropdown tooltip shows **Try later** and uses the last successful catalog when available, or retained models marked as an incomplete catalog. Featherless HTTP 429 starts a cooldown of at least 10 minutes, or longer if requested by the provider. Focus **Model Name** again afterward to resume at the unfinished page. The UI does not wait through the cooldown, and restarting ComfyUI cannot bypass it. Other providers' catalog retry behavior is unchanged.

## API keys

The node reads the key from the selected environment variable. Keys are never written to workflows.

One masked API-key field and **Set** button serve all three providers. **API Key System** controls the destination:

- **Environment variable:** saves the key for the current operating-system user and makes it available immediately. RM-LLM restores it when first needed after a restart. Windows uses user environment variables; Linux uses `$XDG_CONFIG_HOME/rm-llm/environment.json` (normally `~/.config/rm-llm/environment.json`), with owner-only directory/file permissions of `700`/`600`. No administrator or `sudo` access is needed. These values are persistent, unencrypted user settings, outside the node package.
- **Masked session key:** keeps the key only in server memory for the session; it is not saved to disk.

**API Key (Key hidden. Never shared in workflows.)** labels the masked entry and **Set** button for both systems. Keys are never returned to the browser or included in model caches. Environment variables supplied by your launcher take precedence over saved values. On Linux the saved file is loaded by RM-LLM, not by unrelated terminal programs. Set each provider's key once using its default variable name shown above, or connect a custom variable name to `api_key_env`.

## Using the node

1. Select a provider and model.
2. Enter a system prompt and user prompt.
3. Connect an image or video when the selected model advertises that input. If a model change leaves an existing media connection unsupported, RM-LLM labels it **N/A**, mutes its socket, and omits that media from the request while continuing with text.
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
- Bounded retries for rate-limit and provider-server errors. Featherless streaming capacity rejections are retried only before any completion output has started; partial output is never automatically repeated.
- Optional image and native video input where the selected provider/model supports it.
- Environment-variable credentials and temporary masked session credentials.

LithosAI currently reports text-only input because its published API documentation does not define image or video message parts.

## Compatibility

The node is designed for current ComfyUI installations with the standard `aiohttp`, NumPy, Pillow, PyTorch, and ComfyUI video APIs. The included PowerShell launcher is optional and Windows-specific; the node itself uses relative paths and environment variables.

The frontend requires ComfyUI's graph-event and DOM-widget APIs (the installed frontend 1.49.6 provides these). Windows has been checked offline; Linux/macOS and live browser execution remain to be verified. Python 3.10 async timeout handling is included. The normal ComfyUI Run action prepares temporary masked-session tickets through widget callbacks. Saved workflow JSON contains no key or ticket; API exports contain no newly prepared session ticket. Headless/API-only runs should use environment-variable credentials.

This local 0.4.0 copy registers separate node IDs and API routes so it can be tested alongside the existing package. Existing workflows are not changed. Add **RM-LLM 0.4.0** to test the new implementation.

## License

MIT License. See [LICENSE](LICENSE).

## Documentation

- [OpenRouter API](https://openrouter.ai/docs)
- [Featherless API](https://featherless.ai/docs)
- [LithosAI API](https://docs.lithosai.com/)
- [LithosAI OpenAPI schema](https://docs.lithosai.com/openapi.yaml)
- [ComfyUI custom-node guide](https://docs.comfy.org/custom-nodes/walkthrough)
