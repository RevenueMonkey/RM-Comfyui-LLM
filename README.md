# RM-ComfyUI-LLM

Bring OpenRouter, Featherless and LithosAI models into your ComfyUI workflows. Choose a model, connect your prompts and use the controls that model supports.

## Features

- **Inline model search:** type to filter a scrollable catalogue or keep a manually entered model ID. Cached lists and recoverable downloads help when discovery is unavailable.
- **Model-specific controls:** supported sampling settings, Thinking/Reasoning and known chat-template options.
- **Creativity slider:** adjusts temperature and top_p together, with independent settings in Advanced.
- **Images and video:** connect reference media where the provider and model support it. Unsupported media connections become N/A and are omitted from the request.
- **Native ComfyUI integration:** connect prompts and settings from other nodes, with collapsible Model, Simple and Advanced sections, stable sockets and a built-in response preview.
- **Live console output:** stream generated text and returned reasoning as they arrive.
- **Keys kept out of workflows:** masked key entry, environment-variable credentials and temporary session keys.
- **Separate outputs:** generated text, returned reasoning and the full provider response, including usage when supplied.

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

## Releases and compatibility

See [GitHub Releases](https://github.com/RevenueMonkey/RM-Comfyui-LLM/releases) for downloads and the [dated changelog](CHANGELOG.md) for version details. Changelog dates record changes, not Registry publication dates.

The current node uses the ID `RM_LLM_040`. Older workflows using `RM_LLM_V3` or `RM_LLM_V2` are not automatically converted. Keep the older package if those workflows still need it; the new node has separate IDs and routes so both can coexist. For a separate installation, use a different folder name when cloning.

The current implementation has been tested locally on Windows with ComfyUI frontend 1.49.6. It uses standard ComfyUI dependencies and native extension hooks. Linux/macOS runtime verification is still incomplete; the included PowerShell launcher is optional and Windows-specific.

## Support and license

Report problems in [GitHub Issues](https://github.com/RevenueMonkey/RM-Comfyui-LLM/issues), including the package version, ComfyUI/frontend versions, provider, model and error text. Remove keys and private prompts from anything you share.

[MIT License](LICENSE).
