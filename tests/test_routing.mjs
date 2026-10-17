import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../web/routing.js", import.meta.url), "utf8");
const { routerMode, hostMatches, selectedCapabilities } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
assert.equal(routerMode("", "OpenRouter"), "OpenRouter");
assert.equal(routerMode("", "Featherless"), "Direct");
assert.equal(routerMode("Direct", "OpenAI"), "Direct");
assert.equal(hostMatches("azure/region", "azure"), true);
assert.equal(hostMatches("azure-other", "azure"), false);
const caps = { provider: "OpenRouter", parameters: { temperature: {}, top_p: {} }, endpoints: [
    { id: "azure", parameters: ["temperature"], context_length: 10000, max_tokens: 1000 },
    { id: "azure/region", parameters: ["temperature", "top_p"], context_length: 8000, max_tokens: 900 },
    { id: "openai", parameters: ["top_p"], context_length: 20000, max_tokens: 2000 },
] };
const selected = selectedCapabilities(caps, "azure");
assert.deepEqual(Object.keys(selected.parameters), ["temperature"]);
assert.equal(selected.endpoints[0].context_length, 8000);
assert.equal(selected.endpoints[0].max_tokens, 900);
assert.equal(selectedCapabilities(caps, "missing"), null);
assert.equal(selectedCapabilities(caps, "Auto"), caps);
assert.equal(caps.endpoints.length, 3);
console.log("Frontend routing compatibility and endpoint capability checks passed.");
