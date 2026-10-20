# Changelog

Dates identify the recorded changes, not Comfy Registry publication timestamps.

## [0.7.1] - 2026-10-20

- Omit unsupported retained/connected model settings, template options and unsupported optional provider features; retain connections and mark unsupported controls N/A.

- Use one provider selector/socket for Direct services and OpenRouter hosts, with precision annotations retained.

- Display values received through connected scalar inputs in their read-only controls, including text, numbers, dropdowns and toggles.
- Mark pending connections and last-run values; match updates to the source socket and restore manual settings on disconnect.
- Keep display values separate from saved widget settings; exclude credentials, media and agent objects from display events.
- Make the collapsible layout compatible with the Easy-Use UI: folded sections remove only disconnected ghost sockets using native ComfyUI input methods, while connected sockets and wires stay attached. Restore available sockets on expansion.
- User-verified the section folding and socket behaviour on Windows; other platforms remain unverified.

## [0.7.0] - 2026-10-17

- Show API-reported precision beside OpenRouter hosts, including Precision unknown when undisclosed.
- Stabilise RM-LLM labels and row dimensions against theme styling while preserving collapsible sections; Easy-Use visual verification remains user-led.
- Add router as the first inline dropdown: OpenRouter or Direct.
- Support model-first and hosting-provider-first discovery through OpenRouter's official endpoints, with a five-minute provider/filter cache.
- Enforce selected hosts and use endpoint-specific controls and limits; Auto retains automatic routing.
- Preserve legacy provider inputs, node IDs, widget order and workflow connections; add router and hosting_provider inputs at the end of the schema.
- Keep OpenRouter credentials separate from direct provider credentials. No local-server support or extra generation calls.

## [0.6.0] - 2026-10-04

- Give api_key_system the same inline searchable picker, reusing the Provider picker while preserving the two credential modes and key storage.
- Replace the Provider select with the same inline searchable list styling as Model: up to ten visible rows, provider subtitles and keyboard selection; stored provider names remain unchanged.

- Add a provider status line below request_timeout_seconds, with a coloured circle, short updates/errors and explanatory tooltips; use existing request results only.
- Preserve the existing Set button; separate provider status from key storage, including authentication failures, rate limits, model availability, service errors, credits and access restrictions.
- Ignore stale request results after selection or key changes; retain native ComfyUI execution diagnostics and existing node IDs/connections.

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
