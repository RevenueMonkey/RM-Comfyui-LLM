# Changelog

Dates identify the recorded changes, not Comfy Registry publication timestamps.

## [0.5.1] - 2026-10-04

- Use lowercase underscore input labels, mark model controls `[API]`, and supply a default user prompt for new nodes.
- Give automatic budgets a display scale so nonzero usage remains visible; use lowercase budget labels.

- Add connectable Input, Thinking and Output token budgets in Advanced; zero preserves existing/default limits.
- Map output and supported thinking targets to provider controls. Shared generation limits combine thinking and answer allowances; unsupported numeric thinking targets remain planning allowances.
- Check estimated text input before generation without truncating prompts or counting base64 media as text.
- Show three green usage bars within Advanced only after a successful run, using API counts where available and labelled estimates/unknowns otherwise. No numeric labels or extra API calls.
- Keep 0.5.0 node IDs, credentials, cache and native socket/collapse handling compatible.
- Add display-only provider subtitles to the dropdown; plain provider values, socket inputs and the header remain unchanged.

## [0.5.0] - 2026-10-04

- Add OpenAI, Google Gemini, Anthropic, DeepSeek, Groq, Mistral AI, xAI, Together AI and Fireworks AI, retaining OpenRouter, Featherless and LithosAI.
- Adapt authenticated model discovery and pagination to each provider, with cached catalogues and manual model IDs.
- Add native Claude/Gemini requests and streaming, supported media, reasoning controls and normalized outputs retaining native response data.
- Reuse the provider-specific environment/session key process and stable native frontend hooks.
- Register separate 0.5.0 node IDs and routes for installation alongside 0.4.0.
- Restore native socket dragging by keeping the HTML widget wrapper from intercepting socket clicks; confirmed working by the user.
- Expand the README with all twelve providers, Featherless model discovery and LithosAI's speed focus.
- Add offline provider contract tests. User-tested locally on Windows; full live provider/account coverage and non-Windows checks remain pending.

## [0.4.0] - 2026-10-03

- Use native ComfyUI extension hooks and widget layout for the collapsible Model, Simple and Advanced sections.
- Keep input sockets stable through section changes and browser refresh; update wire positions with their sockets.
- Add inline model search with manual model IDs, cached catalogues and download progress. Featherless catalogue downloads use public requests and retain completed pages for resuming.
- Improve persistent API-key setup and availability checks across providers on Windows and Linux. Keys remain outside saved workflows.
- Describe model discovery, supported image/video inputs, Thinking/Reasoning, linked Creativity controls and live console streaming in the package listing and README.
- Include the matching dated release notes when publishing to Comfy Registry.

This version registers separate 0.4.0 node IDs. Existing 0.3.x workflows are not automatically converted; retain the older package when using those nodes.

## [0.3.3] - 2026-10-02

- Improve Featherless model discovery and model-specific input layout.
- Retry streaming capacity rejections only before completion output starts.

## [0.3.2] - 2026-10-01

- Show API-key availability on the Set button and check the selected provider's credentials.

## [0.3.1] - 2026-09-30

- Fix the circular import that prevented the package from loading at startup.

## [0.3.0] - 2026-09-30

- Prepare the initial Registry package for OpenRouter, Featherless and LithosAI.
- Provide model-specific controls, prompts, supported media inputs, Thinking/Reasoning and live console output.
- Support environment-variable and masked session credentials without saving keys in workflows.
