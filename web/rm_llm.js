import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { creativityToSampling, samplingToCreativity } from "./sampling.js";

const states = new WeakMap();
const defaults = { OpenRouter: "OPENROUTER_API_KEY", Featherless: "FEATHERLESS_API_KEY", LithosAI: "LITHOSAI_API_KEY" };
const css = document.createElement("style");
css.textContent = `
.rm-llm { color:var(--input-text,#ddd); background:var(--comfy-menu-bg,#222); padding:10px; box-sizing:border-box; font:13px sans-serif; overflow:auto; width:100%; height:100%; min-width:0; min-height:0; }
.rm-llm label,.rm-llm-dialog label { display:block; margin:6px 0 3px; }
.rm-llm input:not([type=checkbox]),.rm-llm select,.rm-llm textarea,.rm-llm button,.rm-llm-dialog input,.rm-llm-dialog button { color:var(--input-text,#ddd); background:var(--comfy-input-bg,#333); border:1px solid var(--border-color,#666); border-radius:4px; padding:6px; box-sizing:border-box; max-width:100%; }
.rm-llm textarea { width:100%; resize:vertical; min-height:65px; }
.rm-llm select,.rm-llm .rm-wide { width:100%; }
.rm-llm button { cursor:pointer; text-align:left; white-space:normal; overflow-wrap:anywhere; }
.rm-llm .rm-row { display:flex; gap:6px; align-items:center; margin:5px 0; }
.rm-llm .rm-row > input:not([type=checkbox]) { min-width:0; flex:1; }
.rm-llm .rm-note { color:#b7bac1; font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; margin:7px 0; }
.rm-llm .rm-error { color:#ffb5a8; }
.rm-llm .rm-controls { border-top:1px solid #555; padding-top:5px; }
.rm-llm .rm-param { border-bottom:1px solid #444; padding:3px 0 7px; }
.rm-llm .rm-param label { display:flex; gap:5px; align-items:center; }
.rm-llm .rm-param textarea { min-height:45px; }
.rm-llm.rm-widget-row { padding:0 16px 4px 26px; overflow:hidden; display:flex; flex-direction:column; background:transparent; pointer-events:none; }
.rm-widget-row > * { pointer-events:auto; }
.dom-widget:has(> .rm-widget-row) { pointer-events:none !important; }
.rm-widget-row[hidden] { display:none !important; }
/* Nodes 2.0 hides widget sockets on hover. Scope the exception to our rows. */
[data-testid=node-widget]:has(.rm-widget-row) > div:has(> .lg-slot--input),
.lg-node-widgets > div:has(.rm-widget-row) > div:has(> .lg-slot--input) { opacity:1; }
.rm-widget-row.rm-model-heading { justify-content:center; text-align:center; padding:4px 16px; }
.rm-model-name { display:block; overflow-wrap:anywhere; line-height:1.12; font-weight:500; }
.rm-widget-row input[role=switch] { appearance:none; box-sizing:border-box; width:44px; height:24px; flex:none; border:1px solid #777; border-radius:12px; background:#444; cursor:pointer; margin:0; }
.rm-widget-row input[role=switch]::before { content:""; display:block; width:18px; height:18px; border-radius:50%; background:#eee; margin:2px; transition:transform .12s; }
.rm-widget-row input[role=switch]:checked { background:#237aaf; }
.rm-widget-row input[role=switch]:checked::before { transform:translateX(20px); }
.rm-widget-row input[role=switch]:disabled { opacity:.5; cursor:default; }
.rm-widget-row input[type=range] { appearance:none; box-sizing:border-box; height:24px; padding:2px; margin:0; border:1px solid #777; border-radius:12px; background:linear-gradient(to right,#237aaf var(--rm-fill,50%),#444 var(--rm-fill,50%)); cursor:pointer; }
.rm-widget-row input[type=range]::-webkit-slider-runnable-track { height:18px; background:transparent; border:0; }
.rm-widget-row input[type=range]::-webkit-slider-thumb { appearance:none; width:18px; height:18px; border:0; border-radius:50%; background:#eee; }
.rm-widget-row input[type=range]::-moz-range-track { height:18px; background:transparent; border:0; }
.rm-widget-row input[type=range]::-moz-range-thumb { width:18px; height:18px; border:0; border-radius:50%; background:#eee; }
.rm-widget-row input[type=range]:disabled { opacity:.5; cursor:default; }
.rm-widget-row .rm-section { font-size:18px; line-height:24px; font-weight:bold; width:100%; border:0; border-bottom:1px solid #666; background:transparent; padding:6px 0; }
.rm-widget-row.rm-compact > :not(label) { display:none; }
.rm-widget-row .rm-default { margin-left:auto; font-size:11px; padding:3px 6px; }
.rm-widget-row > label { margin:0; line-height:20px; min-height:20px; }
.rm-widget-row > textarea { flex:1; min-height:40px; resize:none; }
.rm-widget-row .rm-note { margin:3px 0; }
.rm-widget-row.rm-model-limits .rm-note { font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rm-widget-row.rm-param { border-bottom:1px solid #444; }
.rm-widget-row.rm-param > .rm-note:not(.rm-error) { display:none; }
.rm-llm [hidden] { display:none !important; }
.rm-llm-dialog { width:min(760px,90vw); max-height:80vh; color:#ddd; background:#24262b; border:1px solid #777; border-radius:8px; padding:16px; font:14px sans-serif; }
.rm-llm-dialog::backdrop { background:#0008; }
.rm-llm-dialog input { width:100%; margin:10px 0; }
.rm-llm-dialog .rm-list { height:50vh; overflow:auto; }
.rm-llm-dialog .rm-list button { display:block; width:100%; text-align:left; padding:9px; margin:3px 0; overflow-wrap:anywhere; cursor:pointer; }
`;
document.head.append(css);

function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
}

function widget(node, name) {
    return node.widgets?.find(w => w.name === name);
}

function value(node, name) {
    return widget(node, name)?.value;
}

function setValue(node, name, val) {
    const w = widget(node, name);
    if (w) w.value = val;
    const field = states.get(node)?.parameters;
    if (name === "parameters_json" && field && document.activeElement !== field) field.value = val;
    if (name === "model_name") states.get(node)?.updateModelHeading?.();
    node.graph?.setDirtyCanvas(true, true);
}

async function call(action, body) {
    const response = await api.fetchApi(`/rm_llm/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-RM-LLM": "1" },
        body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || `RM-LLM HTTP ${response.status}`);
    return data;
}

function note(state, text, error = false) {
    state.status.textContent = text;
    state.status.classList.toggle("rm-error", error);
    if (state.v2) layoutSections(state);
    state.node.graph?.setDirtyCanvas(true, true);
}

function selection(state) {
    const provider = value(state.node, "provider");
    return {
        provider,
        env_name: value(state.node, "api_key_env"),
        session: value(state.node, "credential_source") === "Masked session key" ? state.sessions[provider] : undefined,
    };
}

const coreSockets = { provider: "STRING", model_name: "STRING", api_key_env: "STRING", credential_source: "STRING", system_prompt: "STRING", user_prompt: "STRING", parameters_json: "STRING", timeout_seconds: "INT", console_output: "BOOLEAN" };

function connected(node, name) {
    return node.inputs?.some(input => input.name === name && input.link != null) ?? false;
}

function modelSelection(state) {
    return {
        provider: connected(state.node, "provider") ? state.runtimeModel?.provider : value(state.node, "provider"),
        model: connected(state.node, "model_name") ? state.runtimeModel?.model : value(state.node, "model_name"),
    };
}

function receiveModel(state, model) {
    if (!model?.provider || !model?.model) return;
    const before = modelSelection(state);
    state.runtimeModel = model;
    const after = modelSelection(state);
    state.updateModelHeading?.();
    if (before.provider !== after.provider || before.model !== after.model) void loadCapabilities(state);
}

function executionNode(graph, id) {
    const path = String(id).split(":");
    for (const part of path.slice(0, -1)) graph = graph?.getNodeById(part)?.subgraph;
    return graph?.getNodeById(path.at(-1));
}

function socketType(schema) {
    const kinds = (Array.isArray(schema.type) ? schema.type : [schema.type]).filter(k => k && k !== "null");
    return kinds.length === 1 ? ({integer:"INT",number:"FLOAT",boolean:"BOOLEAN"})[kinds[0]] || "STRING" : "STRING";
}

const templatePrefix = "chat_template_kwargs.";
function templateValue(options, name) {
    if (name === "enable_thinking" && options) {
        const aliases = [options.enable_thinking, options.thinking, options.do_reasoning];
        if (aliases.includes(false)) return false;
        if (aliases.includes(true)) return true;
    }
    return options?.[name];
}
function settingDefinitions(state) {
    const definitions = { ...(state.caps?.parameters || {}) };
    for (const [name, schema] of Object.entries(state.caps?.template_parameters || {})) definitions[templatePrefix + name] = schema;
    if (state.v2 && state.caps?.provider === "OpenRouter" && definitions.reasoning) {
        const options = state.caps.reasoning_options || {};
        definitions["reasoning.enabled"] = { type: "boolean", default: options.mandatory ? true : options.default_enabled, description: options.mandatory ? "This model requires reasoning; it cannot be disabled." : "Enable or disable model reasoning. This does not control whether reasoning text is returned." };
        if (definitions.reasoning_effort && Array.isArray(options.supported_efforts)) {
            definitions.reasoning_effort = { ...definitions.reasoning_effort, enum: options.supported_efforts, default_note: options.default_effort };
        }
    }
    return definitions;
}

// Keep omission distinct from an explicit Off, without an override checkbox.
function booleanSwitch(initial, schema, plainCaption = false) {
    const input = document.createElement("input");
    input.type = "checkbox"; input.setAttribute("role", "switch");
    const line = element("div", undefined, "rm-row");
    const caption = element("span");
    const reset = element("button", "Default", "rm-default");
    reset.type = "button"; reset.title = "Use provider default (omit this setting)";
    let stored = "";
    const knownDefault = typeof schema.default === "boolean" ? schema.default : /^(true|false)$/i.test(schema.default_note || "") ? schema.default_note.toLowerCase() === "true" : undefined;
    Object.defineProperty(input, "value", {
        get: () => stored,
        set: v => {
            stored = v == null || v === "" ? "" : String(v);
            input.checked = stored === "" ? knownDefault === true : stored === "true";
            caption.textContent = plainCaption ? (input.checked ? "On" : "Off") : stored === "" ? knownDefault === undefined ? "Provider default" : `${input.checked ? "On" : "Off"} (default)` : input.checked ? "On" : "Off";
            caption.title = stored === "" ? "Provider default; this setting is omitted." : "Explicit setting";
            reset.hidden = stored === "";
        },
    });
    input.value = initial;
    input.addEventListener("input", () => { input.value = input.checked; });
    reset.onclick = () => { if (!input.disabled) { input.value = ""; input.dispatchEvent(new Event("change")); } };
    line.append(input, caption, reset);
    return { input, line };
}

const standardRows = ["image", "provider", "model_name", "system_prompt", "user_prompt", templatePrefix + "enable_thinking", "temperature"];

function layoutSections(state, fit = false) {
    if (!state.rows.has("heading_standard")) return;
    const node = state.node;
    const sections = node.properties.rm_llm_sections ||= state.v2 ? { model: false, standard: false, advanced: false } : { standard: true, advanced: false };
    const topRows = state.v2 ? ["model_heading", "section_3"] : [];
    const modelRows = state.v2 ? ["provider", "model_name", "credential_source", "api_key_env", "section_0", "section_1", "timeout_seconds", "section_2", "section_4"] : [];
    const simpleRows = state.v2 ? ["image", "video", "system_prompt", "user_prompt", "creativity", templatePrefix + "enable_thinking", "reasoning.enabled"] : standardRows;
    const advancedOrder = [...(state.v2 ? ["temperature", "top_p"] : []), "video", "credential_source", "api_key_env", "section_0", "section_1", ...state.parameterRows, "parameters_json", "section_2", "section_3", "timeout_seconds", "section_4", "section_5"];
    const advanced = [...new Set([...advancedOrder, ...state.rows.keys()])].filter(name => !topRows.includes(name) && !simpleRows.includes(name) && !modelRows.includes(name) && !name.startsWith("heading_") && name !== "console_output");
    const ordered = [...topRows, ...(state.v2 ? ["heading_model", ...modelRows] : []), "heading_standard", ...simpleRows, "heading_advanced", ...advanced, "console_output"];
    const rows = ordered.map(name => state.rows.get(name)).filter(Boolean);
    // Backing widget order is part of the saved-workflow format; only move UI rows.
    const orderedWidgets = [...node.widgets.filter(w => !rows.includes(w)), ...rows];
    for (const [name, row] of state.rows) {
        const section = modelRows.includes(name) ? "model" : simpleRows.includes(name) ? "standard" : "advanced";
        if (name.startsWith("heading_")) {
            const key = name.slice(8), open = sections[key] !== false;
            const button = row.element.querySelector("button");
            button.textContent = `${open ? "\u25bc" : "\u25b6"} ${key === "model" ? "Model" : key === "standard" ? state.v2 ? "Simple" : "Standard" : "Advanced"}`;
            button.setAttribute("aria-expanded", String(open));
            continue;
        }
        const unavailable = state.v2 && name === "section_1" && value(node, "credential_source") !== "Masked session key" || ["image", "video"].includes(name) && !node.inputs?.some(i => i.name === name) || state.v2 && name === "api_key_env" && !connected(node, name) || state.v2 && name === "section_4" && !state.status.classList.contains("rm-error");
        const folded = !topRows.includes(name) && sections[section] === false;
        setRowHidden(row, unavailable || folded && !connected(node, name));
        row.rmCompact = !row.hidden && (folded || state.v2 && name === "api_key_env");
        row.element.classList.toggle("rm-compact", row.rmCompact);
        row.element.dataset.section = section;
        row.element.style.minHeight = `${row.hidden ? 0 : row.options.getMinHeight()}px`;
    }
    // Publish a structural change after visibility edits. Nodes 2.0 observes
    // the widget array, but does not observe fields on legacy widget objects.
    node.widgets.splice(0, node.widgets.length);
    node.widgets.push(...orderedWidgets);
    bindRows(state);
    if (fit && node.graph) node.setSize([node.size[0], node.computeSize()[1]]);
}

function setRowHidden(row, hidden) {
    // Canvas layout reads widget.hidden; Nodes 2.0 reads options.hidden.
    row.hidden = hidden;
    row.options.hidden = hidden;
    row.element.hidden = hidden;
}

function installSectionSlots(state) {
    const node = state.node;
    const inputPos = node.getInputPos;
    node.getInputPos = function (index) {
        // Hidden, unconnected fields must not leave active hit targets over other rows.
        if (!this.collapsed && state.rows.get(this.inputs[index]?.name)?.hidden) return [NaN, NaN];
        return inputPos.call(this, index);
    };
}

function addRow(state, name, children, height, grow = false) {
    const row = element("div", undefined, "rm-llm rm-widget-row");
    row.dataset.setting = name;
    row.append(...children);
    let w;
    const rowHeight = () => w?.rmCompact ? 24 : height + (row.querySelector(".rm-error") ? 42 : 0);
    // Vue DOM widgets use CSS sizing, independently of LiteGraph's allocation.
    row.style.minHeight = `${height}px`;
    w = state.node.addDOMWidget(`rm_row_${name}`, "rm_llm_row", row, {
        margin: 0, hideOnZoom: false, getMinHeight: rowHeight,
        getMaxHeight: () => grow && !w?.rmCompact ? Infinity : rowHeight(),
        getValue: () => "", setValue: () => {}, serialize: false,
    });
    w.serialize = false;
    w.serializeValue = () => undefined;
    // A linked row stays visible so its setting and source remain identifiable.
    w.isVisible = () => !w.hidden && !state.node.flags?.collapsed;
    state.rows.set(name, w);
    return w;
}

function bindRows(state) {
    for (const input of state.node.inputs || []) {
        const row = state.rows.get(input.name);
        if (row) { input.widget = { name: row.name }; input.alwaysVisible = !row.hidden; }
        else delete input.widget;
    }
    if (state.node.graph) state.node.arrange?.();
    state.node.graph?.setDirtyCanvas(true, true);
}

function mountParameterRows(state) {
    for (const name of state.parameterRows) {
        state.node.removeWidget(state.rows.get(name));
        state.rows.delete(name);
    }
    state.parameterRows.clear();
    for (const row of [...state.controls.children]) {
        const control = row.querySelector("input,select,textarea");
        const name = control?.getAttribute("aria-label") || "unsupported_settings";
        const w = addRow(state, name, [...row.childNodes], control?.tagName === "TEXTAREA" ? 108 : 62, control?.tagName === "TEXTAREA");
        w.element.classList.add("rm-param");
        state.parameterRows.add(name);
    }
    layoutSections(state);
}

function syncSockets(state) {
    const sockets = state.v2 ? { ...coreSockets, creativity: "FLOAT" } : coreSockets;
    if (state.v2) delete sockets.api_key_env;
    for (const [name, type] of Object.entries(sockets)) {
        let input = state.node.inputs?.find(input => input.name === name);
        if (!input) { state.node.addInput(name, type); input = state.node.inputs.at(-1); }
        input.type = type;
    }
    for (const name of ["endpoint", "key_ticket", ...(state.v2 ? ["api_key_env"] : [])]) {
        const index = state.node.inputs?.findIndex(input => input.name === name) ?? -1;
        if (index >= 0 && state.node.inputs[index].link == null) state.node.removeInput(index);
    }
    const supported = settingDefinitions(state);
    for (const [name, schema] of Object.entries(supported)) {
        if (name in sockets) continue;
        state.parameterNames.add(name);
        const input = state.node.inputs?.find(input => input.name === name);
        if (!input) state.node.addInput(name, socketType(schema));
    }
    for (const name of state.parameterNames) {
        if (name in sockets) continue;
        const index = state.node.inputs?.findIndex(input => input.name === name) ?? -1;
        if (!(name in supported) && index >= 0 && state.node.inputs[index].link == null) state.node.removeInput(index);
    }
    for (const [name, type] of [["image", "IMAGE"], ["video", "VIDEO"]]) {
        const index = state.node.inputs?.findIndex(input => input.name === name) ?? -1;
        if (state.caps?.input_modalities.includes(name)) {
            if (index < 0) state.node.addInput(name, type);
        } else if (index >= 0 && state.node.inputs[index].link == null) state.node.removeInput(index);
    }
    bindRows(state);
}

function syncConnectedControls(state) {
    for (const [name, control] of state.bindings) {
        control.disabled = connected(state.node, name) || (name === "api_key_env" && value(state.node, "credential_source") === "Masked session key");
        control.title = connected(state.node, name) ? "Value supplied by the connected node." : "";
    }
    for (const validate of state.validators.values()) validate();
    syncCreativity(state);
}

function setCreativityPosition(state, position) {
    state.creativity.value = position;
    const actual = Number(state.creativity.value);
    state.creativity.style.setProperty("--rm-fill", `calc(${actual}% + ${12 - .24 * actual}px)`);
}

function syncCreativity(state, edited) {
    if (!state.v2) return;
    const available = ["temperature", "top_p"].every(name => Object.hasOwn(state.caps?.parameters || {}, name));
    const linked = connected(state.node, "creativity");
    const external = connected(state.node, "parameters_json");
    const individuallyLinked = ["temperature", "top_p"].some(name => connected(state.node, name));
    state.creativity.disabled = !available || linked || external;
    if (linked || external) { state.creativity.setAttribute("aria-valuetext", "Connected"); return; }
    if (!available) { state.creativity.setAttribute("aria-valuetext", "Requires Temperature and top_p"); return; }
    let saved;
    try { saved = JSON.parse(value(state.node, "parameters_json")); } catch { return; }
    if (!saved || typeof saved !== "object" || Array.isArray(saved)) return;
    if (edited) {
        state.node.properties.rm_llm_sampling_source = edited;
        delete state.node.properties.rm_llm_creativity_position;
    }
    const preferred = state.node.properties.rm_llm_sampling_source || "temperature";
    const source = typeof saved[preferred] === "number" ? preferred : typeof saved.temperature === "number" ? "temperature" : "top_p";
    if (typeof saved[source] !== "number") {
        setCreativityPosition(state, 50);
        state.creativity.setAttribute("aria-valuetext", individuallyLinked ? "Connected sampling" : "Provider default");
        return;
    }
    const lastPosition = state.node.properties.rm_llm_creativity_position;
    const lastPair = Number.isFinite(lastPosition) ? creativityToSampling(lastPosition) : null;
    const position = lastPair && ["temperature", "top_p"].every(name => saved[name] === lastPair[name]) ? lastPosition : samplingToCreativity(source, saved[source]);
    if (Number.isNaN(position)) { state.creativity.setAttribute("aria-valuetext", "Custom"); return; }
    setCreativityPosition(state, position);
    const pair = creativityToSampling(position);
    const matched = !individuallyLinked && ["temperature", "top_p"].every(name => typeof saved[name] === "number" && Math.abs(saved[name] - pair[name]) < 1e-7);
    state.creativity.setAttribute("aria-valuetext", `${position.toFixed(1)}${matched ? "" : " · Custom"}`);
}

function addCreativity(state) {
    state.creativity = document.createElement("input");
    Object.assign(state.creativity, { type: "range", min: "0", max: "100", step: "0.1", value: "50" });
    state.creativity.setAttribute("aria-label", "Creativity");
    state.creativity.title = "Sets Temperature and top_p. Editing either Advanced value updates this slider without changing the other. Individually connected inputs take precedence.";
    state.creativity.oninput = () => {
        if (state.creativity.disabled) return;
        let saved;
        try { saved = JSON.parse(value(state.node, "parameters_json")); }
        catch { note(state, "Fix Additional settings JSON before changing Creativity.", true); return; }
        if (!saved || typeof saved !== "object" || Array.isArray(saved)) return;
        Object.assign(saved, creativityToSampling(Number(state.creativity.value)));
        state.node.properties.rm_llm_creativity_position = Number(state.creativity.value);
        state.node.properties.rm_llm_sampling_source = "temperature";
        setValue(state.node, "parameters_json", JSON.stringify(saved));
        renderControls(state);
    };
    const line = element("div", undefined, "rm-row");
    line.append(element("span", "Min"), state.creativity, element("span", "Max"));
    addRow(state, "creativity", [element("label", "Creativity"), line], 62);
}

function renderControls(state) {
    state.controls.replaceChildren();
    state.invalid.clear();
    state.validators.clear();
    if (!state.caps) return;
    let saved;
    try {
        saved = JSON.parse(value(state.node, "parameters_json") || "{}");
        if (!saved || typeof saved !== "object" || Array.isArray(saved)) throw new Error();
        if (Object.hasOwn(saved, "chat_template_kwargs") && (!saved.chat_template_kwargs || typeof saved.chat_template_kwargs !== "object" || Array.isArray(saved.chat_template_kwargs))) throw new Error();
    } catch { state.invalid.set("settings JSON", "Saved model settings must be a JSON object."); note(state, "Saved model settings must be a JSON object.", true); return; }
    const definitions = settingDefinitions(state);
    const names = Object.keys(definitions);
    const templateControls = new Map();
    let reasoningControl, reasoningRaw;
    const unknown = Object.keys(saved).filter(name => !names.includes(name));
    if (unknown.length) {
        state.invalid.set("unsupported settings", `Remove unsupported settings: ${unknown.join(", ")}.`);
        const clear = element("button", `Clear unsupported settings: ${unknown.join(", ")}`);
        clear.onclick = () => {
            for (const name of unknown) delete saved[name];
            setValue(state.node, "parameters_json", JSON.stringify(saved));
            renderControls(state);
        };
        state.controls.append(clear);
    }
    for (const name of names.sort()) {
        const schema = definitions[name] || {};
        const nested = name.startsWith(templatePrefix);
        const optionName = nested ? name.slice(templatePrefix.length) : name;
        const reasoningToggle = name === "reasoning.enabled";
        const thinkingToggle = state.v2 && (reasoningToggle || name === templatePrefix + "enable_thinking");
        const row = element("div", undefined, "rm-param");
        const label = element("label", thinkingToggle ? "Thinking/Reasoning" : name === templatePrefix + "enable_thinking" ? "Enable Thinking" : name === "temperature" ? state.v2 ? "temperature" : "Temperature" : nested ? `Chat template · ${optionName}` : name);
        label.title = [schema.description || "Enter a value or connect a node to this input.", schema.evidence, schema.source, schema.default_note ? `Default: ${schema.default_note}` : ""].filter(Boolean).join("\n");
        const kinds = (Array.isArray(schema.type) ? schema.type : [schema.type]).filter(t => t !== "null");
        const kind = kinds.length === 1 ? kinds[0] : undefined;
        const initial = reasoningToggle ? saved.reasoning?.enabled ?? ((saved.reasoning?.effort ?? saved.reasoning_effort) === "none" ? false : saved.reasoning?.effort || saved.reasoning_effort || saved.reasoning?.max_tokens ? true : undefined) : nested ? templateValue(saved.chat_template_kwargs, optionName) : Object.hasOwn(saved, name) ? saved[name] : undefined;
        let input, switchLine;
        if (kind === "boolean") {
            ({ input, line: switchLine } = booleanSwitch(initial, schema, thinkingToggle));
        } else if (schema.enum && schema.enum.every(v => v === null || typeof v === "string")) {
            input = document.createElement("select");
            input.add(new Option(schema.default_note ? `Provider default (${schema.default_note})` : "Provider default", ""));
            for (const v of schema.enum.filter(v => v !== null)) input.add(new Option(String(v), String(v)));
            input.value = initial == null ? "" : String(initial);
        } else if (kind === "integer" || kind === "number") {
            input = document.createElement("input"); input.type = "number";
            input.step = kind === "integer" ? "1" : "any";
            input.value = initial == null ? "" : initial;
        } else if (kind === "string") {
            input = document.createElement("input"); input.type = "text"; input.value = initial ?? "";
        } else {
            input = document.createElement("textarea"); input.value = initial === undefined ? "" : JSON.stringify(initial, null, 2);
        }
        input.placeholder = "Provider default";
        input.className = "rm-wide";
        input.setAttribute("aria-label", name);
        input.title = label.title;
        if (nested) templateControls.set(optionName, input);
        const storeSetting = (v, remove = false) => {
            if (reasoningToggle) {
                const options = saved.reasoning || {};
                if (typeof options !== "object" || Array.isArray(options)) throw new Error();
                if (remove) delete options.enabled;
                else options.enabled = v;
                if (Object.keys(options).length) saved.reasoning = options;
                else delete saved.reasoning;
                if (reasoningRaw) reasoningRaw.value = saved.reasoning ? JSON.stringify(saved.reasoning, null, 2) : "";
            } else if (nested) {
                const options = saved.chat_template_kwargs || {};
                if (typeof options !== "object" || Array.isArray(options)) throw new Error();
                if (remove) delete options[optionName];
                else {
                    options[optionName] = v;
                    if (optionName === "enable_thinking") { delete options.thinking; delete options.do_reasoning; }
                }
                if (Object.keys(options).length) saved.chat_template_kwargs = options;
                else delete saved.chat_template_kwargs;
                const raw = templateControls.get("__raw");
                if (raw) raw.value = saved.chat_template_kwargs ? JSON.stringify(saved.chat_template_kwargs, null, 2) : "";
            } else {
                if (remove) delete saved[name]; else saved[name] = v;
                if (name === "chat_template_kwargs") for (const [key, control] of templateControls) {
                    if (key !== "__raw") control.value = templateValue(saved.chat_template_kwargs, key) ?? "";
                }
                if (name === "reasoning" && reasoningControl) reasoningControl.value = v?.enabled ?? "";
            }
        };
        if (reasoningToggle) reasoningControl = input;
        if (name === "reasoning") reasoningRaw = input;
        if (name === "chat_template_kwargs") templateControls.set("__raw", input);
        const help = element("div", undefined, "rm-note");
        const guidance = name === "top_k" && state.caps.provider === "Featherless" ? "Whole number: -1 considers all tokens; a positive count such as 40 limits sampling." : kind === "integer" ? "Enter a whole number, or leave blank for provider default." : "Enter a value, leave blank for provider default, or connect another node.";
        const update = () => {
            state.invalid.delete(name);
            input.setCustomValidity(""); input.removeAttribute("aria-invalid"); help.classList.remove("rm-error");
            input.disabled = connected(state.node, name) || connected(state.node, "parameters_json") || (reasoningToggle && (connected(state.node, "reasoning") || state.caps.reasoning_options?.mandatory)) || (state.v2 && ["temperature", "top_p"].includes(name) && connected(state.node, "creativity")) || (nested && connected(state.node, "chat_template_kwargs"));
            if (switchLine) switchLine.querySelector("button").disabled = input.disabled;
            if (input.disabled) { help.textContent = connected(state.node, name) ? "Value supplied by the connected node." : "Settings supplied by the parameters_json connection."; return; }
            help.textContent = guidance;
            if (input.value === "" && !input.validity.badInput) storeSetting(undefined, true);
            else {
                try {
                    let v = input.value;
                    if (kind === "boolean") v = v === "true";
                    else if (kind === "integer" || kind === "number") {
                        if (v === "" || !Number.isFinite(Number(v)) || (kind === "integer" && !Number.isSafeInteger(Number(v)))) throw new Error();
                        v = Number(v);
                    } else if (input.tagName === "TEXTAREA") v = JSON.parse(v);
                    if (name === "chat_template_kwargs" && (!v || typeof v !== "object" || Array.isArray(v))) throw new Error();
                    storeSetting(v);
                } catch {
                    const message = `${name}: ${kind === "integer" ? "enter a whole number" : kind === "number" ? "enter a number" : "enter valid JSON"}, or leave blank for provider default.`;
                    state.invalid.set(name, message); input.setCustomValidity(message); input.setAttribute("aria-invalid", "true");
                    help.textContent = message; help.classList.add("rm-error"); note(state, message, true); return;
                }
            }
            setValue(state.node, "parameters_json", JSON.stringify(saved));
            if (!state.invalid.size && state.status.classList.contains("rm-error")) note(state, "Settings are valid. Connected inputs take precedence; blank fields use provider defaults.");
        };
        const edited = () => {
            if (reasoningToggle && !input.disabled && input.value !== "") {
                const options = saved.reasoning || {};
                if (input.value === "false") {
                    delete options.effort; delete options.max_tokens; delete saved.reasoning_effort;
                } else {
                    if (options.effort === "none") delete options.effort;
                    if (saved.reasoning_effort === "none") delete saved.reasoning_effort;
                }
            }
            update();
            if (state.v2 && name === "reasoning_effort" && input.value && !input.disabled) {
                saved.reasoning = { ...(saved.reasoning || {}), enabled: input.value !== "none" };
                delete saved.reasoning.effort;
                delete saved.reasoning.max_tokens;
                setValue(state.node, "parameters_json", JSON.stringify(saved));
            }
            if (["temperature", "top_p"].includes(name)) syncCreativity(state, name);
            if (state.v2 && ["reasoning", "reasoning.enabled", "reasoning_effort"].includes(name) && !state.invalid.size) renderControls(state);
        };
        input.oninput = edited; input.onchange = edited; state.validators.set(name, update); update();
        row.append(label, switchLine || input, help); state.controls.append(row);
    }
    const info = state.caps.endpoints[0];
    const implemented = state.caps.input_modalities.filter(m => ["text", "image", "video"].includes(m));
    state.capInfo.textContent = state.v2 ? `Context: ${info?.context_length?.toLocaleString() ?? "Provider-defined"}  |  Output limit: ${info?.max_tokens?.toLocaleString() ?? "Provider-defined"}` : `${state.caps.source}\nRM-LLM inputs: ${implemented.join(", ")} | Context: ${info?.context_length ?? "provider-defined"} | Output limit: ${info?.max_tokens ?? "provider-defined"}\nConnect input sockets or enter values below. Blank fields use provider defaults. Structured inputs accept JSON text.`;
    if (!state.v2 && state.caps.template_note) state.capInfo.textContent += `\n${state.caps.template_note}`;
    mountParameterRows(state);
    syncCreativity(state);
}

async function loadCapabilities(state) {
    const { provider, model } = modelSelection(state);
    const revision = ++state.revision;
    state.validators.clear();
    state.invalid.clear();
    state.caps = null;
    state.capInfo.textContent = "Context: —  |  Output limit: —";
    state.controls.replaceChildren();
    mountParameterRows(state);
    state.updateModelHeading?.();
    if (!provider || !model) {
        syncSockets(state);
        syncConnectedControls(state);
        state.capInfo.textContent = "Awaiting connected model at execution";
        note(state, "Run upstream nodes to discover the connected model's settings.");
        return;
    }
    syncSockets(state);
    note(state, "Discovering model capabilities…");
    try {
        const caps = await call("capabilities", { ...selection(state), provider, model });
        if (state.revision !== revision) return;
        state.caps = caps;
        if (state.v2) state.lastRefreshed.textContent = `Last refreshed: ${new Date().toLocaleString()}`;
        syncSockets(state);
        renderControls(state);
        syncConnectedControls(state);
        layoutSections(state, true);
        note(state, `Capabilities refreshed. Record: ${caps.record_updated}`);
    } catch (error) {
        if (state.revision !== revision) return;
        state.caps = null;
        state.controls.replaceChildren();
        note(state, error.message, true);
    }
}

async function chooseModel(state) {
    const provider = value(state.node, "provider");
    const dialog = element("dialog", undefined, "rm-llm-dialog");
    const title = element("strong", `${provider} · model_name`);
    const close = element("button", "Close"); close.style.float = "right";
    const search = document.createElement("input");
    search.placeholder = "Search all model IDs and names…"; search.setAttribute("aria-label", "Search models");
    const status = element("p", "Fetching the full live catalog…");
    const list = element("div", undefined, "rm-list");
    dialog.append(title, close, search, status, list);
    document.body.append(dialog);
    close.onclick = () => dialog.close();
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    dialog.showModal(); search.focus();
    let models = state.models[provider] || [];
    let loadError = "";
    const render = () => {
        const q = search.value.toLocaleLowerCase().trim();
        const matches = models.filter(m => `${m.id} ${m.name}`.toLocaleLowerCase().includes(q));
        status.textContent = `${loadError}${models.length.toLocaleString()} models loaded · ${matches.length.toLocaleString()} matches${matches.length > 200 ? " · showing first 200; type to narrow" : ""}`;
        list.replaceChildren();
        for (const model of matches.slice(0, 200)) {
            const button = element("button", model.id + (model.available_on_current_plan === false ? " [not on current plan]" : ""));
            button.title = model.name;
            button.onclick = () => {
                if (provider !== value(state.node, "provider")) return dialog.close();
                if (model.id !== value(state.node, "model_name")) {
                    setValue(state.node, "parameters_json", "{}");
                    setValue(state.node, "endpoint", "Auto");
                }
                setValue(state.node, "model_name", model.id);
                state.model.textContent = model.id;
                dialog.close();
                void loadCapabilities(state);
            };
            list.append(button);
        }
    };
    search.oninput = render;
    try {
        const response = await call("models", selection(state));
        models = response.models;
        state.models[provider] = models;
    } catch (error) {
        loadError = `${error.message}${models.length ? " Showing the previous catalog. " : " "}`;
    }
    if (dialog.isConnected) render();
}

function addModelHeading(state) {
    const text = element("span", "", "rm-model-name");
    const row = addRow(state, "model_heading", [text], 64);
    row.element.classList.add("rm-model-heading");
    const fit = () => {
        if (!row.element.isConnected || row.element.clientWidth === 0) return;
        // Measure in CSS pixels so browser zoom and canvas zoom do not skew fitting.
        for (let size = 32; size >= 10; size--) {
            text.style.fontSize = `${size}px`;
            if (text.scrollHeight <= 56 && text.scrollWidth <= text.clientWidth) break;
        }
    };
    state.updateModelHeading = () => {
        const { provider, model } = modelSelection(state);
        text.textContent = connected(state.node, "model_name") ? model ? `${model} (last execution)` : "Awaiting connected model" : String(model || "Select a model");
        state.provider.value = provider || "";
        state.model.textContent = model || (connected(state.node, "model_name") ? "Awaiting connected model" : "Click to load all models…");
        text.title = text.textContent;
        fit();
    };
    const observer = new ResizeObserver(fit);
    observer.observe(row.element);
    const removed = state.node.onRemoved;
    state.node.onRemoved = function (...args) {
        observer.disconnect();
        return removed?.apply(this, args);
    };
    state.updateModelHeading();
}

function setup(node, nodeData) {
    if (states.has(node)) return;
    for (const w of node.widgets || []) {
        const saved = w;
        w.type = "hidden";
        w.hidden = true;
        w.options ||= {};
        w.options.hidden = true;
        w.computeSize = () => [0, -4];
        w.serializeValue = () => saved.name === "key_ticket" ? "" : saved.value;
        if (w.inputEl) w.inputEl.style.display = "none";
    }
    const panel = element("div", undefined, "rm-llm");
    const state = { node, panel, v2: ["RM_LLM_V2", "RM_LLM_V3"].includes(nodeData.name), v3: nodeData.name === "RM_LLM_V3", sessions: {}, models: {}, caps: null, revision: 0, invalid: new Map(), validators: new Map(), bindings: new Map(), rows: new Map(), parameterRows: new Set(), parameterNames: new Set(Object.keys(nodeData.input.optional).filter(n => !["image", "video", "key_ticket", "agent_request"].includes(n))) };
    states.set(node, state);
    function label(text, control) { panel.append(element("label", text), control); return control; }
    function bound(name, tag = "input") {
        const input = document.createElement(tag);
        input.className = "rm-wide";
        input.value = value(node, name) ?? "";
        input.oninput = () => setValue(node, name, name === "timeout_seconds" ? Number(input.value) : input.value);
        state.bindings.set(name, input);
        return input;
    }
    state.provider = document.createElement("select");
    for (const p of Object.keys(defaults)) {
        if (p === "LithosAI" && !state.v3) continue;
        state.provider.add(new Option(p, p));
    }
    label("Provider", state.provider);
    state.bindings.set("provider", state.provider);
    state.model = element("button", value(node, "model_name") || "Click to load all models…", "rm-wide");
    state.model.onclick = () => void chooseModel(state);
    state.bindings.set("model_name", state.model);
    label("Model Name", state.model);
    state.mode = document.createElement("select");
    state.mode.setAttribute("aria-label", state.v2 ? "API Key System" : "API key source");
    for (const m of ["Environment variable", "Masked session key"]) state.mode.add(new Option(m, m));
    label(state.v2 ? "API Key System" : "API key source", state.mode);
    state.bindings.set("credential_source", state.mode);
    state.env = label("API-key environment variable name", bound("api_key_env"));
    const keyRow = element("div", undefined, "rm-row");
    const password = document.createElement("input");
    password.type = "password"; password.autocomplete = "off"; password.placeholder = "Paste API key (never saved)";
    password.setAttribute("aria-label", "API key"); password.spellcheck = false;
    const setKey = element("button", "Set");
    keyRow.append(password, setKey); panel.append(keyRow);
    state.keyStatus = element("div", "Enter a key and click Set.", "rm-note"); panel.append(state.keyStatus);
    const updateMode = () => {
        keyRow.hidden = false;
        const row = state.rows.get("section_0");
        if (row) layoutSections(state);
        state.env.disabled = state.mode.value === "Masked session key" || connected(node, "api_key_env");
        const hasKey = state.sessions[state.provider.value];
        state.keyStatus.textContent = state.mode.value === "Masked session key"
            ? (hasKey ? "Masked key held in server memory for up to 12 hours." : "No masked key stored. Reloading this page requires re-entry.")
            : "Set a key to the selected environment variable in the running ComfyUI process.";
    };
    state.mode.onchange = () => { setValue(node, "credential_source", state.mode.value); updateMode(); };
    setKey.onclick = async () => {
        const provider = state.provider.value;
        setKey.disabled = true;
        try {
            const old = state.sessions[provider];
            if (state.mode.value === "Masked session key") {
                const result = await call("key", { provider, key: password.value });
                state.sessions[provider] = result.session;
                if (old) await call("key", { provider, session: old, clear: true });
                note(state, "Masked key stored in server memory. It has not been used for a paid request.");
            } else {
                const envName = value(node, "api_key_env") || defaults[provider];
                const result = await call("set_env", { provider, env_name: envName, key: password.value });
                if (old) await call("key", { provider, session: old, clear: true });
                delete state.sessions[provider];
                note(state, `${result.environment_variable} set for this ComfyUI process. Restarting ComfyUI requires setting it again.`);
            }
            password.value = "";
            updateMode();
        } catch (error) { note(state, error.message, true); }
        finally { setKey.disabled = false; }
    };
    state.system = label("System Prompt", bound("system_prompt", "textarea"));
    state.user = label("User Prompt", bound("user_prompt", "textarea"));
    state.parameters = label("Additional settings (JSON)", bound("parameters_json", "textarea"));
    state.parameters.onchange = () => { setValue(node, "parameters_json", state.parameters.value); renderControls(state); };
    const buttons = element("div", undefined, "rm-row");
    const refresh = state.v2 ? document.createElement("input") : element("button", "Refresh models & capability records");
    if (state.v2) {
        refresh.type = "checkbox"; refresh.setAttribute("role", "switch"); refresh.setAttribute("aria-label", "Refresh");
        refresh.title = "Refresh models and capabilities. Returns to Off when finished.";
        state.lastRefreshed = element("span", "Last refreshed: Not yet", "rm-note");
    }
    const refreshModels = async () => {
        if (refresh.disabled || state.v2 && !refresh.checked) return;
        refresh.disabled = true;
        const { provider } = modelSelection(state);
        if (!provider) {
            await loadCapabilities(state);
            refresh.disabled = false; refresh.checked = false;
            return;
        }
        note(state, "Refreshing provider documentation and full model catalog…");
        try {
            await call("refresh", { provider });
            const catalog = await call("models", { ...selection(state), provider });
            state.models[provider] = catalog.models;
            if (provider === modelSelection(state).provider) {
                await loadCapabilities(state);
                if (!value(node, "model_name")) {
                    if (state.v2) state.lastRefreshed.textContent = `Last refreshed: ${new Date().toLocaleString()}`;
                    note(state, `${catalog.models.length.toLocaleString()} models loaded. Select model_name.`);
                }
            }
        } catch (error) { note(state, error.message, true); }
        finally { refresh.disabled = false; if (state.v2) refresh.checked = false; }
    };
    if (state.v2) { refresh.onchange = refreshModels; buttons.append(element("span", "Refresh"), refresh, state.lastRefreshed); }
    else { refresh.onclick = refreshModels; buttons.append(refresh); }
    panel.append(buttons);
    state.capInfo = element("div", state.v2 ? "Context: —  |  Output limit: —" : "Select a model to discover its inputs and settings.", "rm-note"); panel.append(state.capInfo);
    state.controls = element("div", undefined, "rm-controls"); panel.append(state.controls);
    state.timeout = label("Request timeout (seconds)", bound("timeout_seconds"));
    state.timeout.type = "number"; state.timeout.min = "10"; state.timeout.max = "3600";
    state.status = element("div", "Ready. Model weights remain hosted by the provider.", "rm-note"); panel.append(state.status);
    state.output = document.createElement("textarea"); state.output.readOnly = true; state.output.placeholder = "Response preview"; panel.append(state.output);
    let section = 0;
    for (const child of [...panel.children]) {
        if (child.parentElement !== panel || child === state.controls) continue;
        const children = [child];
        if (child.tagName === "LABEL") children.push(child.nextElementSibling);
        const control = children.at(-1);
        const name = [...state.bindings].find(([, el]) => el === control)?.[0] || `section_${section++}`;
        const multiline = control.tagName === "TEXTAREA";
        addRow(state, name, children, multiline ? 108 : child === state.capInfo ? state.v2 ? 24 : 120 : state.v2 && (child === buttons || child === keyRow) ? 40 : child.classList.contains("rm-note") ? state.v2 ? 36 : 48 : 58, multiline);
    }
    if (state.v2) state.rows.get("section_3").element.classList.add("rm-model-limits");
    state.console = document.createElement("input");
    state.console.type = "checkbox";
    state.console.setAttribute("role", "switch");
    state.console.setAttribute("aria-label", "Console output");
    const consoleState = element("span", "Off");
    const consoleLine = element("div", undefined, "rm-row");
    consoleLine.append(state.console, consoleState);
    state.console.onchange = () => {
        setValue(node, "console_output", state.console.checked);
        consoleState.textContent = state.console.checked ? "On" : "Off";
    };
    state.bindings.set("console_output", state.console);
    addRow(state, "console_output", [element("label", state.v2 ? "Live console output" : "Console output"), consoleLine], 58);
    for (const name of ["image", "video"]) {
        const children = [element("label", name === "image" ? "Image" : "Video")];
        if (!state.v2) children.push(element("div", "Connect a matching node to the input socket.", "rm-note"));
        addRow(state, name, children, state.v2 ? 24 : 42);
    }
    for (const name of state.v2 ? ["model", "standard", "advanced"] : ["standard", "advanced"]) {
        const button = element("button", undefined, "rm-section");
        button.type = "button";
        button.onclick = () => {
            const sections = node.properties.rm_llm_sections;
            sections[name] = sections[name] === false;
            layoutSections(state, true);
        };
        addRow(state, `heading_${name}`, [button], 42);
    }
    if (state.v2) { addCreativity(state); addModelHeading(state); }
    installSectionSlots(state);
    state.sync = () => {
        state.validators.clear();
        state.invalid.clear();
        setValue(node, "endpoint", "Auto");
        state.updateModelHeading?.();
        state.provider.value = value(node, "provider");
        state.model.textContent = value(node, "model_name") || "Click to load all models…";
        state.mode.value = value(node, "credential_source");
        state.env.value = value(node, "api_key_env");
        state.system.value = value(node, "system_prompt"); state.user.value = value(node, "user_prompt");
        state.timeout.value = value(node, "timeout_seconds");
        state.parameters.value = value(node, "parameters_json");
        state.console.checked = value(node, "console_output") === true;
        state.console.onchange();
        setValue(node, "key_ticket", "");
        updateMode();
        syncSockets(state);
        syncConnectedControls(state);
        layoutSections(state);
        if (value(node, "model_name") || connected(node, "model_name") || connected(node, "provider")) void loadCapabilities(state);
    };
    state.provider.onchange = () => {
        ++state.revision;
        setValue(node, "provider", state.provider.value);
        setValue(node, "api_key_env", defaults[state.provider.value]);
        setValue(node, "model_name", ""); setValue(node, "endpoint", "Auto"); setValue(node, "parameters_json", "{}");
        state.caps = null; state.controls.replaceChildren(); state.validators.clear();
        mountParameterRows(state);
        state.invalid.clear(); state.capInfo.textContent = state.v2 ? "Context: —  |  Output limit: —" : "Select a model to discover its inputs and settings.";
        if (state.v2) state.lastRefreshed.textContent = "Last refreshed: Not yet";
        password.value = ""; state.sync(); note(state, "Click model_name to fetch this provider's catalog.");
    };
    state.sync();
    node.setSize([Math.max(node.size[0], 500), state.v2 ? node.computeSize()[1] : 700]);
}

app.registerExtension({
    name: "RM.LLM",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "easy showAnything") {
            const executed = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (...args) {
                const result = executed?.apply(this, args);
                // Easy Use replaces its text widget after each result. The current
                // frontend needs a layout pass for the replacement DOM widget.
                queueMicrotask(() => {
                    if (!this.graph || !this.inputs?.some((_, index) => ["RM_LLM_V2", "RM_LLM_V3"].includes(this.getInputNode(index)?.type))) return;
                    this.arrange?.();
                    this.setSize(this.size);
                    this.graph.setDirtyCanvas(true, true);
                });
                return result;
            };
            return;
        }
        if (!["RM_LLM_V2", "RM_LLM_V3"].includes(nodeData.name)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) { const result = created?.apply(this, args); setup(this, nodeData); return result; };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configured?.apply(this, args);
            const state = states.get(this);
            if (state?.v2) this.properties.rm_llm_sections = { model: false, standard: false, advanced: false };
            state?.sync();
            if (state?.v2) queueMicrotask(() => layoutSections(state, true));
            return result;
        };
        const connectionsChanged = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (...args) {
            connectionsChanged?.apply(this, args);
            const state = states.get(this);
            if (state) {
                syncConnectedControls(state); state.updateModelHeading?.(); layoutSections(state);
                if (args[0] === 1 && ["provider", "model_name"].includes(this.inputs?.[args[1]]?.name)) {
                    state.runtimeModel = null;
                    void loadCapabilities(state);
                }
            }
        };
        const executionStart = nodeType.prototype.onExecutionStart;
        nodeType.prototype.onExecutionStart = function (...args) {
            executionStart?.apply(this, args);
            const state = states.get(this);
            if (state && (connected(this, "model_name") || connected(this, "provider"))) {
                state.runtimeModel = null;
                void loadCapabilities(state);
            }
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (data) {
            executed?.call(this, data);
            const state = states.get(this);
            if (state) {
                receiveModel(state, data.rm_llm_model?.[0]);
                state.output.value = (data.text || []).join("\n");
            }
        };
    },
    setup() {
        api.addEventListener("rm-llm-model", ({ detail }) => {
            const node = executionNode(app.rootGraph, detail.node);
            const state = node && states.get(node);
            if (state) receiveModel(state, detail.model_info);
        });
        const original = api.queuePrompt;
        api.queuePrompt = async function (number, prompt, ...rest) {
            for (const [id, spec] of Object.entries(prompt.output || {})) {
                if (!["RM_LLM_V2", "RM_LLM_V3"].includes(spec.class_type)) continue;
                const node = app.graph.getNodeById(id);
                const state = node && states.get(node);
                spec.inputs.key_ticket = "";
                if (state && !Array.isArray(spec.inputs.parameters_json)) {
                    for (const validate of state.validators.values()) validate();
                    if (state.invalid.size) throw new Error(`RM-LLM: ${[...state.invalid.values()].join(" ")}`);
                    spec.inputs.parameters_json = value(node, "parameters_json");
                }
                if (spec.inputs.credential_source === "Masked session key") {
                    const provider = spec.inputs.provider;
                    const session = state?.sessions[provider];
                    if (!session) throw new Error("RM-LLM: enter a masked key and click Set in this node before queueing. For subgraphs/API execution use environment variables.");
                    const result = await call("ticket", { provider, session });
                    spec.inputs.key_ticket = result.ticket;
                }
            }
            return original.call(this, number, prompt, ...rest);
        };
    },
});
