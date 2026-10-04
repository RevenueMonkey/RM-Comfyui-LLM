# Provider contracts

Reviewed 2026-10-04. Live lists determine availability; documented model families
supplement incomplete capability metadata. This is not a guarantee of account
access or support for every option on every future model.

| Provider | Discovery and request references |
|---|---|
| OpenAI | [Models](https://developers.openai.com/api/reference/resources/models), [Chat](https://developers.openai.com/api/reference/resources/chat) |
| Google Gemini | [Models](https://ai.google.dev/api/models), [GenerateContent](https://ai.google.dev/api/generate-content), [Thinking](https://ai.google.dev/gemini-api/docs/thinking) |
| Anthropic | [Models](https://platform.claude.com/docs/en/api/models/list), [Messages](https://platform.claude.com/docs/en/api/messages/create) |
| DeepSeek | [Chat](https://api-docs.deepseek.com/api/create-chat-completion/), [Thinking](https://api-docs.deepseek.com/guides/thinking_mode/) |
| Groq | [API reference](https://console.groq.com/docs/api-reference), [Vision](https://console.groq.com/docs/vision) |
| Mistral AI | [Models](https://docs.mistral.ai/api/endpoint/models), [Chat](https://docs.mistral.ai/api), [Reasoning](https://docs.mistral.ai/studio/conversations/reasoning) |
| xAI | [Models](https://docs.x.ai/developers/rest-api-reference/inference/models), [Reasoning](https://docs.x.ai/developers/model-capabilities/text/reasoning) |
| Together AI | [Models](https://docs.together.ai/reference/models), [Vision](https://docs.together.ai/docs/inference/vision/overview), [Reasoning](https://docs.together.ai/docs/inference/chat/reasoning) |
| Fireworks AI | [Models](https://docs.fireworks.ai/api-reference/list-models), [Chat](https://docs.fireworks.ai/api-reference/post-chatcompletions) |

The existing OpenRouter, Featherless and LithosAI records remain in
`capability_records.json`. New provider contracts are in `providers.py`.
Refreshing model metadata does not silently scrape and overwrite these reviewed
contracts or pretend their documentation date has changed.

## Offline validation

Run `python -B tests/test_providers.py` with ComfyUI's Python. The suite substitutes
ComfyUI host objects and provider responses; it does not start a server, read real
credentials, call model endpoints, or verify browser rendering. It covers node
registration, all-provider execution dispatch, credentials, catalogue pagination,
media/parameter translation, native streaming and incomplete-response handling.

Live account tests, frontend checks and Linux/macOS execution remain to be done
before publishing this preview.
