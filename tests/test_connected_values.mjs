import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../web/connected_values.js", import.meta.url), "utf8");
const { inputLink, sourceMatches, displayControl, restoreControl } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
assert.equal(sourceMatches(["12", 0], { origin_id: 12, origin_slot: 0 }), true);
assert.equal(sourceMatches(["12", 0], { origin_id: 13, origin_slot: 0 }), false);
const label = { dataset: {} };
const control = { tagName: "INPUT", type: "number", value: "0.5", checked: false, placeholder: "Default", title: "original", style: { visibility: "" } };
let record = displayControl(control, label, null);
assert.equal(control.value, ""); assert.equal(control.placeholder, "Connected");
record = displayControl(control, label, { value: 0.8 }, record);
assert.equal(control.value, "0.8"); assert.equal(record.value, "0.5");
restoreControl(record); assert.equal(control.value, "0.5"); assert.equal(control.title, "original");
const toggle = { ...control, type: "checkbox", value: "manual", checked: true, style: { visibility: "" }, nextElementSibling: { textContent: "On" } };
record = displayControl(toggle, label, null);
assert.equal(toggle.style.visibility, "hidden"); assert.equal(toggle.nextElementSibling.textContent, "Connected");
record = displayControl(toggle, label, { value: false }, record);
assert.equal(toggle.checked, false); assert.equal(toggle.nextElementSibling.textContent, "Off");
restoreControl(record); assert.equal(toggle.checked, true); assert.equal(toggle.nextElementSibling.textContent, "On");
console.log("Connected display: source identity, pending values and manual restoration passed.");

const nativeLink = { origin_id: 408, origin_slot: 0 };
for (const graph of [
    { getLinkById: id => id === 27 ? nativeLink : null },
    { links: new Map([[27, nativeLink]]) },
    { links: { 27: nativeLink } },
]) {
    assert.equal(sourceMatches(["408", 0], inputLink(graph, 27)), true);
    assert.equal(sourceMatches(["408", 0], inputLink(graph, 28)), false);
}
assert.equal(inputLink(null, null), null);
console.log("Native, Map and legacy link lookup regression checks passed.");
