// Display-only classification of existing, sanitized request errors.
// Never render raw provider text here: it can echo request content.
export function providerStatus(error) {
    const message = String(error?.message ?? error ?? "");
    const code = Number(message.match(/Provider HTTP (\d{3})\b/i)?.[1]);
    if (message === "Request cancelled")
        return { tone: "warning", text: "Request cancelled", detail: "ComfyUI interrupted this operation." };
    if (/API Key Need(?:ed)?!/i.test(message))
        return { tone: "error", text: "API key needed", detail: "No key is available for the selected credential source." };
    if (code === 401)
        return { tone: "error", text: "Invalid API key", detail: "The provider rejected authentication. Check or replace the selected key." };
    if (code === 429 || /catalog.*(?:cooling down|rate-limited)/i.test(message))
        return { tone: "warning", text: "Rate limited — try later", detail: "The provider limited this request. A stored key can still be valid." };
    if (code === 404 || /no live chat endpoints/i.test(message))
        return { tone: "warning", text: "Model unavailable", detail: "The model or endpoint is unavailable on this provider. Check the model selection." };
    if (code === 402)
        return { tone: "warning", text: "Credits needed", detail: "The provider reported insufficient credits." };
    if (code === 403)
        return { tone: "warning", text: "Access denied", detail: "Check the account plan and model permissions. This does not necessarily mean the key is invalid." };
    if (code >= 500 && code <= 599)
        return { tone: "warning", text: "Provider unavailable", detail: "The provider reported a service or capacity failure. Try later." };
    if (/connection failed|timed out|failed to fetch|networkerror/i.test(message))
        return { tone: "warning", text: "Connection failed", detail: "The request could not reach the provider or timed out." };
    if (/try later/i.test(message))
        return { tone: "warning", text: "Try later", detail: "Live retrieval did not complete. Previously cached data may still be available." };
    return null;
}
