# RM-ComfyUI-LLM

At RM, we were tired of the existing LLM nodes and found them all lacking, so we made our own. We update regularly — any feature you want, just ask.

Bring models from twelve API providers into your ComfyUI workflows. Choose a model, connect your prompts and use the controls that model supports.

## Supported APIs

Ten major LLM APIs in one node, plus two more for exploring unusual models and fast inference:

| Provider | What you can access |
|---|---|
| OpenAI | OpenAI chat and reasoning models |
| Google Gemini | Gemini models, with image/video inputs where supported |
| Anthropic | Claude through its native Messages API |
| OpenRouter | Models from multiple developers through one API |
| DeepSeek | DeepSeek chat and reasoning models |
| Groq | Hosted models with a focus on fast inference |
| Mistral AI | Mistral chat and vision models |
| xAI | Grok models |
| Together AI | Hosted open models |
| Fireworks AI | Public serverless models and manually entered account model IDs |

- **[Featherless](https://featherless.ai/):** explore a catalogue advertised at **40,000+ models**, including obscure community fine-tunes, creative-writing models and uncensored variants. Browse its [model catalogue](https://featherless.ai/models) to see what is available.
- **[LithosAI](https://www.lithosai.com/):** built for ultra-fast inference. Actual speed depends on the model and workload; RM-LLM's current LithosAI integration supports text input.

These are supported integrations, not a measured ComfyUI popularity ranking. Model availability and features depend on your provider and account.

## Features

- **Inline model search:** type to filter a scrollable catalogue or keep a manually entered model ID. Cached lists and recoverable downloads help when discovery is unavailable.
- **Model-specific controls:** supported sampling settings, Thinking/Reasoning and known chat-template options.
- **Creativity slider:** adjusts temperature and top_p together, with independent settings in Advanced.
- **Images and video:** connect reference media where the provider and model support it. Unsupported media connections become N/A and are omitted from the request.
- **Native ComfyUI integration:** connect prompts and settings from other nodes, with collapsible Model, Simple and Advanced sections, stable sockets and a built-in response preview.
- **Live console output:** stream generated text and returned reasoning as they arrive.
- **Keys kept out of workflows:** masked key entry, environment-variable credentials and temporary session keys.
- **Separate outputs:** generated text, returned reasoning and the full provider response, including usage when supplied.
- **Token budgets:** Input, Thinking and Output allowances in Advanced, with green usage bars shown after a run and simple tooltips explaining estimates.

## Install

Open a terminal in your ComfyUI `custom_nodes` directory and run:

```sh
git clone https://github.com/RevenueMonkey/RM-Comfyui-LLM.git
```

Restart ComfyUI, refresh your browser and find **RM-LLM** under **RM/API**. The package uses dependencies supplied by ComfyUI; it does not download model weights.

To update an existing Git installation, run `git pull --ff-only` inside its folder, then restart ComfyUI and refresh your browser. Update your existing copy rather than installing a duplicate of the same package.

## API keys

Choose a provider and **API Key System**, paste your key into the masked **API Key** field and press **Set**.

| Provider | Default environment variable |
|---|---|
| OpenRouter | `OPENROUTER_API_KEY` |
| Featherless | `FEATHERLESS_API_KEY` |
| LithosAI | `LITHOSAI_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GEMINI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Groq | `GROQ_API_KEY` |
| Mistral AI | `MISTRAL_API_KEY` |
| xAI | `XAI_API_KEY` |
| Together AI | `TOGETHER_API_KEY` |
| Fireworks AI | `FIREWORKS_API_KEY` |

**Environment variable** saves the key for the current user and makes it available immediately and after restart. Windows uses user environment variables; Linux uses an owner-only configuration file under `$XDG_CONFIG_HOME/rm-llm` (normally `~/.config/rm-llm`). No administrator or sudo access is needed. Variables supplied by your launcher take precedence. **Masked session key** keeps the key in server memory for that session only. Headless/API workflows should use environment variables.

Keys are excluded from saved workflows. Masking hides the entry on screen; it does not encrypt environment variables or the saved configuration file. Requests send the key to the selected API provider for authentication.

## Use

1. Select your provider and model, then set its API key.
2. Enter or connect the system and user prompts.
3. Connect supported reference media if needed.
4. Adjust Creativity and Thinking/Reasoning. Open Advanced for individual model controls and live console output.
5. Run the workflow.

| Output | Contents |
|---|---|
| `response` | Generated text |
| `reasoning` | Reasoning returned by the model, when available |
| `response_json` | Full provider response, including usage and tool calls when supplied |

Available controls and media support depend on the selected provider's API metadata and documented capabilities. The same model may expose different features through different providers. LithosAI's current integration supports text input. Tool calls are returned as data; RM-LLM does not execute external tools.

## Provider differences

### Token budgets

In Advanced, set **input_budget**, **thinking_budget** and **output_budget** in tokens. Leave a field blank or use **0** to keep existing/provider defaults. All three accept connections from other nodes. Green usage bars appear beneath these controls after a successful run, without numeric labels. Automatic mode uses known model limits or an estimated display scale, without adding request limits. Empty bars indicate zero or unknown usage; hover for the explanation.

- **Input:** stops before generation if the rough text estimate exceeds your budget. It never truncates prompts. The estimate includes conversation and tool text, but excludes media tokens; actual provider usage is preferred after the run. This is not a tokenizer-accurate context or cost guarantee.
- **Thinking:** sends a numeric target where supported; otherwise it is a planning allowance. Explicit Thinking/Reasoning Off and known default-off models stay off. Enable thinking separately when needed. Adaptive/effort-only models cannot enforce a numeric split.
- **Output:** a positive value replaces other output-token settings. When thinking is available, the configured thinking allowance is added to the shared generation limit. Unused thinking space may become output, or thinking may consume more than planned; neither part is guaranteed its share. With a zero Output budget, the existing generation limit stays in place.

Usage counts come from the API when supplied, including cached input and separate thinking counts where available. Otherwise returned text is estimated. Hidden reasoning with no usage breakdown is marked unknown, not zero. Bars saturate at full; tooltips identify usage above an allowance. They describe the last run, not a live spending meter. No extra token-counting API calls or tokenizer downloads are made.

For example, budgets of **2048 input**, **1024 thinking** and **512 output** make a short test easy to read. Usage of 833, 666 and 118 tokens fills approximately 41%, 65% and 23% respectively. Automatic mode may show only a small green marker when model limits are much larger than usage.

Controls marked `[API]` are provider/model controls, drawn from metadata or documented capabilities. Budgets and creativity are local convenience controls.

### API behaviour

- Claude uses its native Messages API; Gemini uses native GenerateContent. Their response JSON includes the preserved native response under `provider_response`, alongside the usual text/reasoning outputs.
- Model controls combine live metadata with reviewed API documentation. Where metadata does not advertise media, only documented model families are enabled; unknown model names are not assumed to support vision. New model families may need a capability-record update.
- Catalogues list supported chat/text models. Fireworks lists public serverless models; custom account model IDs can be entered manually. Together model metadata comes from its catalogue because it does not expose the same per-model lookup as other providers.
- Thinking/Reasoning appears where supported. Models with mandatory reasoning cannot be switched off. Advanced native thinking controls and the simple toggle are alternatives; do not set both. Reasoning text is available only when returned by the provider.
- Anthropic requires an output token limit: RM-LLM supplies 4096 when omitted, capped by its advertised limit. Manually budgeted thinking defaults to 1024 only when explicitly enabled, and requires a larger output limit. Models advertising adaptive thinking use it instead.
- Anthropic's paired Creativity slider is unavailable because its sampling controls cannot always be combined; use an individual Advanced control. Other models without both sampling controls also disable the slider.
- Gemini accepts inline image/video data up to its request-size limit; this integration does not upload files to provider storage. Large media must be resized or shortened.
- The existing `agent_request` conversation transport remains OpenRouter-only. Other providers can return tool calls through `response_json`; RM-LLM does not execute them.
- API contracts and model capabilities are documented in [provider sources](PROVIDER_SOURCES.md). No provider SDKs or additional custom nodes are required.

## Releases and compatibility

See [GitHub Releases](https://github.com/RevenueMonkey/RM-Comfyui-LLM/releases) for downloads and the [dated changelog](CHANGELOG.md) for version details. Changelog dates record changes, not Registry publication dates.

The current node uses the ID `RM_LLM_050`; the 0.5.1 patch keeps this ID and the existing routes/cache so 0.5.0 workflows remain compatible. Older workflows using `RM_LLM_040`, `RM_LLM_V3` or `RM_LLM_V2` are not automatically converted. Keep the older package if those workflows still need it; the new node has separate IDs and routes so both can coexist. For a separate installation, use a different folder name when cloning.

The current node and socket dragging have been user-tested on Windows. Provider adapters have offline contract tests; live testing of every provider/account combination is not complete. The node uses standard ComfyUI dependencies and native extension hooks. Linux/macOS runtime verification is still incomplete; the included PowerShell launcher is optional and Windows-specific.

## Support and license

Report problems in [GitHub Issues](https://github.com/RevenueMonkey/RM-Comfyui-LLM/issues), including the package version, ComfyUI/frontend versions, provider, model and error text. Remove keys and private prompts from anything you share.

[MIT License](LICENSE).
