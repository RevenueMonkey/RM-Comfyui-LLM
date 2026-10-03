# Changelog

Dates identify the recorded changes, not Comfy Registry publication timestamps.

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
