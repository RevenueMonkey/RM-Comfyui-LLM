# RM-ComfyUI-LLM v2

This package exposes **RM-LLM v2** (`RM_LLM_V2`) and **RM-LLM v3** (`RM_LLM_V3`). The former `RM_LLM` node is no longer registered or supported. Its shared Python request implementation remains internal because v2 and v3 inherit it; it is not available as a separate node. v2 keeps the OpenRouter and Featherless provider UI. v3 adds LithosAI.

Cross-platform ComfyUI custom node pack for OpenRouter, Featherless, and LithosAI. Add **RM-LLM** from **RM/API**. Uses existing aiohttp, Pillow, NumPy, PyTorch and ComfyUI video support; no dependency installation is required.

## Use

### RM-LLM v2

Add **RM-LLM v2** from **RM/API** for the existing v2 layout. Workflows using the removed `RM_LLM` class must be changed to v2 or v3.

### RM-LLM v3

Add **RM-LLM v3** from **RM/API** to use the same v2 layout and execution features with LithosAI. v3 supports OpenRouter, Featherless, and LithosAI. LithosAI uses `https://api.lithosai.cloud/v1`, the `LITHOSAI_API_KEY` environment variable by default, live `/models` discovery, and the documented OpenAI-compatible chat controls. LithosAI is reported as text-only because its published API schema does not document image or video message parts. Its documented `reasoning_effort`, tool, sampling, token-limit, response-format, and streaming fields are exposed dynamically. LithosAI rate-limit and server errors receive bounded retries using `Retry-After` or `Retry-After-Ms` when supplied.

**Model**, above Simple, groups Provider, Model Name, **API Key System**, masked key entry and status, request timeout, and model/capability refresh. The environment-variable-name field is hidden in v2; environment keys still use the selected provider's variable (or an existing saved custom name). Context and output limit appear on one line below the top model name, in a fixed 12px font, outside the collapsible sections. The Refresh toggle stays On while refreshing and returns Off afterwards, with the last successful refresh date/time beside it. Routine explanatory status text is hidden; errors remain visible. Model, Simple, and Advanced start collapsed when the node is created or a workflow is loaded. The selected model name is displayed in the space beside the output sockets, as plain text that scales to fit the available space, with padding but no background or border. Connected inputs keep their compact label/socket when collapsed. Simple starts with Image and Video when supported by the selected model, followed by System Prompt, User Prompt, **Creativity**, and the **Thinking/Reasoning** toggle at the bottom. Temperature and top_p appear first in **Advanced**, with **Live console output** at the bottom of that section. Thinking/Reasoning shows On/Off without the default suffix; hovering its caption identifies an omitted provider default. Creativity uses a longer pill slider matching the toggle's height and thumb.

Creativity uses `c = clamp(value, 0, 100) / 100`, `temperature = 0.2 × 6^c`, and `top_p = 1 − 0.1 × 10^(−c)`, rounded to two decimal places. The range is Temperature 0.2–1.2 and top_p 0.90–0.99. The slider has Min/Max labels and a blue fill to the left of its thumb, with no numeric label or Default button. Until edited, its initial position sends no sampling values. Clear Temperature and top_p in Advanced to restore provider defaults.

Moving Creativity updates both Advanced values. Editing either value independently moves Creativity using that value's inverse curve, preserving the other value. The slider's accessible value identifies custom pairs outside the shared curve, including Advanced values beyond its range. The most recently edited control determines the displayed slider position; it is not a measurement of model creativity. Values and the last edited control survive save/reload.

Creativity also exposes a FLOAT input socket. At execution, a connected Creativity sets both sampling values; individually connected Temperature/top_p take precedence. The slider is available when both controls are advertised. Unsupported settings still fail validation rather than being silently omitted. The UI cannot preview values from connected nodes before execution.

When Provider or Model Name is connected, v2 waits for the actual runtime selection instead of using the saved dropdown to discover controls. As execution reaches RM-LLM, the model heading, capability limits and supported sockets refresh for that provider/model, including loop passes and subgraphs. Until then, the UI says it is awaiting the connected model. The heading identifies the last executed model; upstream edits take effect on the next run. Disconnecting restores the local dropdown selection. Existing wires and saved settings are preserved; this does not change the request or add an LLM call. After installing this Python/frontend change, restart your existing ComfyUI once and reload the browser.

**Thinking/Reasoning** uses the supported provider control: Featherless `chat_template_kwargs.enable_thinking` or OpenRouter `reasoning.enabled`. Both are BOOLEAN sockets. OpenRouter default state and mandatory reasoning come from live model metadata; required reasoning is locked On and the backend rejects attempts to disable it. Untouched defaults stay omitted. Switching Off clears conflicting effort/budget settings while preserving other reasoning options. Reasoning effort stays in Advanced, filtered to the model's advertised effort levels. Selecting an effort enables reasoning. The raw reasoning JSON and returned-reasoning visibility controls also remain in Advanced. See [OpenRouter reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

### Original RM-LLM


**Standard** contains Image, Provider, Model Name, System Prompt, User Prompt, Enable Thinking, and Temperature when supported by the selected model. **Advanced** contains the remaining settings, API-key controls, and Console output at the bottom. Click the triangle before either title to expand or collapse it. Standard starts open and Advanced starts closed; section state is saved with the node. Collapsing never changes settings or disconnects wires: connected fields retain compact labels and sockets, while unconnected fields are hidden.

Boolean settings use On/Off switches. Untouched settings retain provider defaults; **Default** resets an explicit choice to omission. A known default is shown as On or Off (default); an unknown default is labelled Provider default.

1. Select **OpenRouter**, **Featherless**, or **LithosAI** in v3 and choose your API-key source.
2. Click **Model Name**. Each opening fetches the complete catalog, including pagination. Search matches every downloaded model ID/name; the menu renders up to 200 matches at a time. These are model listings, not model-weight downloads.
3. Select a model. Its live metadata supplies media capabilities and supported controls. OpenRouter uses automatic routing and requires providers to support enabled settings. There is no hosting-provider selector in the panel.
4. Enter system and user prompts. Connect **image** (all images in the batch) or native ComfyUI **VIDEO** when the model supports them. Unconnected unsupported sockets disappear. Existing connected sockets are preserved and unsupported inputs produce an execution error.
5. Enter values directly, or connect other nodes to the socket beside each setting label. Each setting uses a separate ComfyUI DOM widget with a bound input socket; prompts and structured text areas grow with the node, and the canvas handles the full node layout. Empty fields use provider defaults. Numeric settings expose INT/FLOAT sockets, booleans expose BOOLEAN sockets, and structured settings such as reasoning, response_format, tools and chat_template_kwargs expose STRING sockets accepting JSON text. Connected settings take precedence over the panel or parameters_json. Core fields, including system_prompt, user_prompt, provider, model_name, api_key_env and timeout_seconds, are also connectable. The panel disables connected controls. Selecting a model determines which setting sockets are displayed; existing connected sockets are preserved and unsupported settings are rejected at execution. Connected provider/model values refresh v2's controls when execution resolves them, as described above. Integer controls require whole numbers: Featherless top_k accepts -1 to consider all tokens or a positive count such as 40. Tool calls are returned in response_json; RM-LLM does not execute tools. Changing model/provider manually clears panel settings.
**Console output**, at the bottom of the node, is an On/Off boolean switch with a matching input socket. It defaults to Off. On requests live SSE streaming and immediately prints each arriving text/reasoning fragment, followed by elapsed time. Off uses the normal non-streaming request. The response, reasoning and response_json sockets still receive the assembled completion, including tool calls and usage when supplied. Streamed output is not printed again at completion. Interrupted, failed or truncated streams fail rather than returning partial success, and are never automatically replayed; Featherless HTTP 503 responses before streaming starts retain the existing bounded capacity retries. API keys are redacted; normal errors and retry warnings remain visible with the switch Off.

RM-LLM v3 also provides **Set environment variable** beside its masked key field. It validates the selected variable name and sets the key only in the current ComfyUI process, then clears the browser field. The key is not saved in the workflow or written to disk. This is a first-time convenience for local use; repeat it after restarting ComfyUI, or configure a persistent Windows/Linux environment variable outside the node.

6. Queue to generate. Outputs are **response**, **reasoning**, and **response_json** (including usage and tool calls). Each queued execution calls the provider again; ComfyUI's interrupt button cancels pending network work and retry waits. Featherless HTTP 503 capacity failures are retried up to three times, following its documented guidance. Retries respect Retry-After or wait 5/10/20 seconds, within the original request timeout. Other HTTP errors, connection failures and timeouts are not retried. Errors show the provider's JSON message with credentials redacted.

**Refresh models & capability records** refreshes the provider's documentation record, full catalog, and selected model metadata. Capability records include their source and refresh date. OpenRouter records come from its official OpenAPI schema; Featherless records are parsed from the parameter table in its completion documentation. If the documentation format changes, refresh fails with a clear message and preserves the previous record. Model availability always comes from live APIs. A failed dropdown refresh can show that browser session's previous catalog, explicitly labelled.

Featherless's API does not publish a complete per-model parameter schema. Its common generation controls are documented API options, not guarantees that every model supports every value. RM-LLM labels that distinction. It combines image flags with modality metadata because Featherless sometimes reports a vision model as text-only in input_modalities. Native video chat is enabled only for OpenRouter models advertising video. Some models also advertise audio/file inputs; this node currently implements text, IMAGE and VIDEO inputs.

## Model-specific chat-template controls

Selecting a Featherless model discovers known options inside `chat_template_kwargs` and displays separate **Chat template ? option** rows with matching typed sockets. Booleans use On/Off switches with a Default reset; numbers and text can be left blank to omit them. Socket names are namespaced, for example `chat_template_kwargs.enable_thinking`. Values are sent inside the `chat_template_kwargs` object, never as top-level provider parameters.

Discovery reads the selected model's public Hugging Face chat template (or tokenizer configuration), without rendering it or executing model code. It recognizes documented fields and additional scalar variables with literal defaults. Provider family documentation supplies fallback options. Hover a control for its evidence/source and any documented default. A public template can differ from Featherless's deployed template; unknown models do not inherit speculative controls, and reasoning budgets appear only when found in the model template. Fixed-thinking variants do not receive an on/off toggle.

The original JSON field remains available for custom options. Editing it synchronizes the discrete controls; clicking Default removes only that option. A connected whole JSON object takes precedence over panel JSON, and connected individual options take precedence over that object. An explicit enable_thinking input removes conflicting thinking/do_reasoning aliases. Unsupported connected options are rejected after a model change. OpenRouter continues to use its advertised reasoning controls; Featherless template kwargs are not assumed to pass through OpenRouter.

The existing refresh button refreshes provider family documentation, clears cached capabilities, and re-reads the selected model template. No packages or model weights are downloaded. The bundled Jinja2 library is used only to inspect the template's syntax tree.

Some Featherless models (including the Gemma 2 based AURAGROUPS/Dirty-Muse-Writer-v01-Uncensored-Erotica-NSFW) reject a separate `system` message. When the selected public template explicitly rejects that role, RM-LLM prepends System Prompt to User Prompt, separated by a blank line. Both input fields and their connections remain usable; the capability note explains the adaptation. Models without that detected restriction retain separate messages. This follows [Google's Gemma system-instruction guidance](https://ai.google.dev/gemma/docs/core/prompt-structure).

## API keys

**Environment variable:** Enter the variable's name in the node (default OPENROUTER_API_KEY or FEATHERLESS_API_KEY). Python reads its value using `os.environ.get(name)`. The value is never returned to the browser. An already-running ComfyUI process does not inherit later environment changes.

The included **Start-RM-LLM.ps1** reads existing process environment variables using the requested .NET API:

```powershell
[System.Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY', [System.EnvironmentVariableTarget]::Process)
```

It prompts securely for any missing keys, sets them only in the launcher's process environment, and starts the portable Python. Stop your existing ComfyUI before using this launcher:

```powershell
powershell -NoProfile -File <ComfyUI root>\ComfyUI\custom_nodes\RM-LLM\Start-RM-LLM.ps1
```

**Masked session key:** Select this source, paste the key, and click **Use key**. The field is cleared after submission. The key stays only in server memory, expiring after 12 hours or server restart. The browser holds an opaque session reference in memory, not localStorage, workflow JSON, or node properties. Each queue action obtains a separate, single-use credential ticket; queue/history contain only that ticket, never the key. Used tickets cannot be reused. Unused queued tickets expire after 24 hours. Clearing a key stops new tickets; tickets already issued for queued requests remain usable. Reloading a page requires re-entry. This mode is supported for nodes on the main canvas; subgraphs and headless API clients should use environment variables.

Masked key entry requires localhost or HTTPS. Credentials are sent only to the selected fixed provider HTTPS origin, and redirects are rejected. Like other custom nodes, this runs inside your trusted ComfyUI process; keys are accessible to that process and its installed code. Keys are never written into this package, generated media metadata, saved workflows, execution history, or error text.

## Limits and validation

Only text-producing chat-completion models can execute. Other catalog entries remain discoverable but report an unsupported endpoint/output error. Additional output data remains in response_json. Image/video encoding has a 48 MiB limit; provider limits may be lower. VIDEO is encoded as MP4/H.264 through ComfyUI's video interface and preserves the active trim/audio behavior of that interface. No image resizing, frame sampling, or silent text-only fallback is performed.

Sources: [OpenRouter models](https://openrouter.ai/docs/guides/overview/models), [OpenRouter schema](https://openrouter.ai/openapi.json), [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [video inputs](https://openrouter.ai/docs/guides/overview/multimodal/videos), [Featherless models](https://featherless.ai/docs/api-reference-models), [completion parameters](https://featherless.ai/docs/completions), [vision](https://featherless.ai/docs/vision), [chat template kwargs](https://featherless.ai/docs/chat-template-kwargs), [LithosAI API](https://docs.lithosai.com/), [LithosAI authentication](https://docs.lithosai.com/authentication), and [LithosAI OpenAPI schema](https://docs.lithosai.com/openapi.yaml).

Frontend layout uses ComfyUI DOM widgets and widget/input bindings: [ComfyUI widget documentation](https://docs.comfy.org/custom-nodes/js/javascript_objects_and_hijacking). RM-LLM v2's model heading is a resizable DOM text row above the model limits, without a background box. Section visibility is published through both `hidden` and `options.hidden` for canvas and Nodes 2.0, with CSS minimum heights for DOM rendering. A narrowly scoped CSS rule makes this node's Nodes 2.0 input sockets visible without hovering; that selector remains dependent on the frontend's DOM markup. The extension no longer changes private slot arrays or private layout flags. Imports are relative to the extension directory, including when ComfyUI is served under a URL prefix.

To update another computer, stop ComfyUI there and replace the files in its existing `custom_nodes/RM-LLM` directory with the updated package, then start ComfyUI and hard-refresh the browser (Ctrl+F5). Copy the node package, not this installation's Python environment or browser profiles. No package installation or saved-workflow edits are required. Masked session keys must be re-entered after a browser reload/server restart.

When RM-LLM feeds Easy Use's Show Anything, its replacement text widget is laid out after every result. This avoids a blank output caused by the widget retaining zero size or an off-canvas position in frontend 1.49.6. The hook applies only to Show Anything nodes connected directly to RM-LLM; it does not alter saved workflows or Easy Use files.

Streaming references: [OpenRouter SSE](https://openrouter.ai/docs/api_reference/streaming), [Featherless streaming example](https://featherless.ai/docs/litellm), and LithosAI's OpenAI-compatible streaming schema in its [OpenAPI document](https://docs.lithosai.com/openapi.yaml). The implementation uses the existing aiohttp dependency.

## Agent requests (Episode V4)

Agent Request always enables live Responses SSE streaming for every role, senior
and worker call. The console shows returned text/reasoning, function calls,
estimated input and output limits, elapsed time and returned token usage. While
the provider is silent, a status message appears every 15 seconds. Reasoning is
displayed only when the provider supplies it; encrypted reasoning is never printed.
Credentials are redacted, including across streaming fragments.

Only a terminal provider response can become an answer or tool call. Partial or
interrupted streams are never accepted or automatically replayed. No new model
fallback is introduced. Existing LLM v2 nodes retain their Console output switch.
See [OpenRouter Responses](https://openrouter.ai/docs/api/api-reference/responses/create-responses).

RM-LLM v2 also accepts an optional `agent_request` connection. In that mode its
visible system prompt, JSON conversation and model controls use the same existing
Responses transport, with console streaming on. It returns normalized tool calls
or the final answer in `response_json`; the connected workflow executes tools.
Environment-variable credentials are required for this mode. Without that
connection the ordinary chat/image/video path is unchanged. The exposed-node
integration was authored without running tests or provider calls, as requested.
