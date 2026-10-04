import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../web/provider_status.js", import.meta.url), "utf8");
const { providerStatus } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
for (const [error, text, tone] of [
    ["API Key Needed!", "API key needed", "error"],
    ["Provider HTTP 401. detail: private-request-value", "Invalid API key", "error"],
    ["Provider HTTP 429.", "Rate limited — try later", "warning"],
    ["Featherless catalog is cooling down. Try later.", "Rate limited — try later", "warning"],
    ["Provider HTTP 404.", "Model unavailable", "warning"],
    ["This model has no live chat endpoints.", "Model unavailable", "warning"],
    ["Provider HTTP 402.", "Credits needed", "warning"],
    ["Provider HTTP 403.", "Access denied", "warning"],
    ["Provider HTTP 503.", "Provider unavailable", "warning"],
    ["Provider connection failed or timed out.", "Connection failed", "warning"],
]) {
    const result = providerStatus(new Error(error));
    assert.equal(result.text, text);
    assert.equal(result.tone, tone);
    assert.ok(!JSON.stringify(result).includes("private-request-value"));
}
for (const error of [null, "", "Input budget exceeded", "Provider HTTP 400. Check request settings."])
    assert.equal(providerStatus(error), null);
console.log("Provider status: 14 classification/privacy cases passed.");

// Exercise the actual request wrapper with mocked fetches; no server or API calls.
const ui = readFileSync(new URL("../web/rm_llm.js", import.meta.url), "utf8");
const callSource = ui.slice(ui.indexOf("async function call("), ui.indexOf("\nfunction note("));
const changes = [];
const state = { statusContext: 1, reportProviderStatus: (error, scope) => changes.push([error?.message ?? null, scope]) };
let finish;
const api = { fetchApi: () => new Promise(resolve => { finish = resolve; }) };
const call = new Function("api", `${callSource}; return call;`)(api);
let request = call("models", {}, state);
state.statusContext++;
finish({ ok: false, json: async () => ({ error: "Provider HTTP 401." }) });
await assert.rejects(request, /401/);
assert.deepEqual(changes, [], "An old provider response must not update current status");
request = call("capabilities", {}, state);
finish({ ok: false, json: async () => ({ error: "Provider HTTP 429." }) });
await assert.rejects(request, /429/);
assert.deepEqual(changes.pop(), ["Provider HTTP 429.", "capabilities"]);
request = call("models", {}, state);
finish({ ok: true, json: async () => ({ models: [] }) });
await request;
assert.deepEqual(changes.pop(), [null, "models"], "Success clears only its own request scope");
assert.equal(changes.length, 0);
console.log("Request status: stale response, error and recovery checks passed.");
