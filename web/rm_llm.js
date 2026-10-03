import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { creativityToSampling, samplingToCreativity } from "./sampling.js";

const states = new WeakMap();
const nodeDefinitions = new Map();
const observedGraphs = new WeakSet();
const NODE_ID = "RM_LLM_040";
const defaults = { OpenRouter: "OPENROUTER_API_KEY", Featherless: "FEATHERLESS_API_KEY", LithosAI: "LITHOSAI_API_KEY" };
const css = document.createElement("style");
css.textContent = `
.rm040-llm { color:var(--input-text,#ddd); background:var(--comfy-menu-bg,#222); padding:10px; box-sizing:border-box; font:13px sans-serif; overflow:auto; width:100%; height:100%; min-width:0; min-height:0; }
.rm040-llm label { display:block; margin:6px 0 3px; }
.rm040-llm input:not([type=checkbox]),.rm040-llm select,.rm040-llm textarea,.rm040-llm button { color:var(--input-text,#ddd); background:var(--comfy-input-bg,#333); border:1px solid var(--border-color,#666); border-radius:4px; padding:6px; box-sizing:border-box; max-width:100%; }
.rm040-llm textarea { width:100%; resize:vertical; min-height:65px; }
.rm040-llm select,.rm040-llm .rm040-wide { width:100%; }
.rm040-llm button { cursor:pointer; text-align:left; white-space:normal; overflow-wrap:anywhere; }
.rm040-llm .rm040-row { display:flex; gap:6px; align-items:center; margin:5px 0; }
.rm040-llm .rm040-row > input:not([type=checkbox]) { min-width:0; flex:1; }
.rm040-llm .rm040-note { color:#b7bac1; font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; margin:7px 0; }
.rm040-llm .rm040-error { color:#ffb5a8; }
.rm040-llm .rm040-key-status-ready { border-color:#35b56a; background:#194d2d; }
.rm040-llm .rm040-key-status-missing { border-color:#d45b5b; background:#542424; }
.rm040-llm .rm040-key-status-unknown { border-color:#777; }
.rm040-llm .rm040-param { border-bottom:1px solid #444; padding:3px 0 7px; }
.rm040-llm .rm040-param label { display:flex; gap:5px; align-items:center; }
.rm040-llm .rm040-param textarea { min-height:45px; }
.rm040-llm.rm040-widget-row { padding:0 16px 4px 26px; overflow:hidden; display:flex; flex-direction:column; height:auto; background:transparent; pointer-events:none; }
.rm040-widget-row > * { pointer-events:auto; }
.rm040-widget-row[hidden] { display:none !important; }
.rm040-widget-row.rm040-model-heading { justify-content:center; text-align:center; padding:4px 16px; }
.rm040-model-name { display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; line-height:1.12; font-weight:500; }
.rm040-heading-pair { display:flex; flex-direction:column; gap:2px; flex:none; min-width:0; width:100%; }
.rm040-heading-pair + .rm040-heading-pair { margin-top:8px; }
.rm040-model-heading .rm040-note { font-size:12px; line-height:16px; margin:0 !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:center; }
.rm040-widget-row input[role=switch] { appearance:none; box-sizing:border-box; width:44px; height:24px; flex:none; border:1px solid #777; border-radius:12px; background:#444; cursor:pointer; margin:0; }
.rm040-widget-row input[role=switch]::before { content:""; display:block; width:18px; height:18px; border-radius:50%; background:#eee; margin:2px; transition:transform .12s; }
.rm040-widget-row input[role=switch]:checked { background:#237aaf; }
.rm040-widget-row input[role=switch]:checked::before { transform:translateX(20px); }
.rm040-widget-row input[role=switch]:disabled { opacity:.5; cursor:default; }
.rm040-widget-row input[type=range] { appearance:none; box-sizing:border-box; height:24px; padding:2px; margin:0; border:1px solid #777; border-radius:12px; background:linear-gradient(to right,#237aaf var(--rm040-fill,50%),#444 var(--rm040-fill,50%)); cursor:pointer; }
.rm040-widget-row input[type=range]::-webkit-slider-runnable-track { height:18px; background:transparent; border:0; }
.rm040-widget-row input[type=range]::-webkit-slider-thumb { appearance:none; width:18px; height:18px; border:0; border-radius:50%; background:#eee; }
.rm040-widget-row input[type=range]::-moz-range-track { height:18px; background:transparent; border:0; }
.rm040-widget-row input[type=range]::-moz-range-thumb { width:18px; height:18px; border:0; border-radius:50%; background:#eee; }
.rm040-widget-row input[type=range]:disabled { opacity:.5; cursor:default; }
.rm040-widget-row .rm040-section { font-size:18px; line-height:24px; font-weight:bold; width:100%; border:0; border-bottom:1px solid #666; background:transparent; padding:6px 0; }
.rm040-widget-row.rm040-compact > :not(label) { display:none; }
.rm040-widget-row .rm040-default { margin-left:auto; font-size:11px; padding:3px 6px; }
.rm040-widget-row > label { margin:0; line-height:20px; min-height:20px; }
.rm040-widget-row > label.rm040-media-unavailable { color:#888; }
.rm040-widget-row > textarea { flex:1; min-height:40px; resize:none; }
.rm040-widget-row .rm040-note { margin:3px 0; }
.rm040-widget-row.rm040-param { border-bottom:1px solid #444; }
.rm040-widget-row.rm040-param > .rm040-note:not(.rm040-error) { display:none; }
.rm040-llm [hidden] { display:none !important; }
.rm040-llm .rm040-model-dropdown { flex:none; margin-top:4px; border:1px solid var(--border-color,#666); border-radius:4px; overflow:hidden; box-sizing:border-box; background:var(--comfy-input-bg,#333); }
.rm040-llm .rm040-model-options { max-height:320px; overflow:auto; overscroll-behavior:contain; }
.rm040-llm .rm040-model-option { display:block; width:100%; height:32px; border:0; border-radius:0; padding:6px 8px; margin:0; text-align:left; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rm040-llm .rm040-model-option:hover,.rm040-llm .rm040-model-option[aria-selected=true] { background:var(--comfy-input-bg-hover,#444); }
.rm040-llm .rm040-model-empty { height:32px; padding:6px 8px; box-sizing:border-box; color:var(--descrip-text,#aaa); }
.rm040-llm .rm040-catalog-progress { height:12px; background:var(--comfy-input-bg,#333); }
.rm040-llm .rm040-catalog-progress-fill { height:100%; background:#35b56a; transition:width .3s; }
`;
document.head.append(css);

function element(tag, text, className) {
    const el = document.createElement(tag);
    if (tag === "button") el.type = "button";
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
    const response = await api.fetchApi(`/rm_llm_040/${action}`, {
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
    state.status.classList.toggle("rm040-error", error);
    layoutSections(state);
    state.node.graph?.setDirtyCanvas(true, true);
}

function selection(state) {
    const provider = modelSelection(state).provider || value(state.node, "provider");
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

function connectedStaticString(node, name) {
    try {
        const input = node.inputs?.find(candidate => candidate.name === name);
        const linkId = input?.link;
        if (linkId == null) return undefined;
        let link = linkId;
        if (typeof linkId !== "object") {
            const links = node.graph?.links;
            link = node.graph?.getLinkById?.(linkId)
                || (links instanceof Map ? links.get(linkId) : links?.[linkId])
                || node.graph?._links?.[linkId];
        }
        const origin = link && node.graph?.getNodeById?.(link.origin_id);
        if (!origin || !["PrimitiveString", "PrimitiveStringMultiline"].includes(origin.type)) return undefined;
        const widget = origin.widgets?.find(candidate => candidate.name === "value") || origin.widgets?.[0];
        const value = widget?.value ?? origin.widgets_values?.[0];
        return typeof value === "string" ? value.trim() : undefined;
    } catch {
        return undefined;
    }
}

function modelSelection(state) {
    return {
        provider: connected(state.node, "provider") ? connectedStaticString(state.node, "provider") ?? state.runtimeModel?.provider : value(state.node, "provider"),
        model: connected(state.node, "model_name") ? connectedStaticString(state.node, "model_name") ?? state.runtimeModel?.model : value(state.node, "model_name"),
    };
}

function receiveModel(state, model) {
    if (!model?.provider || !model?.model) return;
    const before = modelSelection(state);
    state.runtimeModel = model;
    const after = modelSelection(state);
    state.updateModelHeading?.();
    if (before.provider !== after.provider || before.model !== after.model || state.caps?.provider !== after.provider || state.caps?.model !== after.model) void loadCapabilities(state);
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
    if (state.caps?.provider === "OpenRouter" && definitions.reasoning) {
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
    const line = element("div", undefined, "rm040-row");
    const caption = element("span");
    const reset = element("button", "Default", "rm040-default");
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

function layoutSections(state, fit = false) {
    if (!state.rows.has("heading_standard")) return;
    syncSockets(state);
    const node = state.node;
    const sections = node.properties.rm_llm_sections ||= { model: false, standard: false, advanced: false };
    const topRows = ["model_heading"];
    const modelRows = ["provider", "model_name", "credential_source", "api_key_env", "section_0", "timeout_seconds", "section_4"];
    const simpleRows = ["image", "video", "system_prompt", "user_prompt", "creativity", templatePrefix + "enable_thinking", "reasoning.enabled"];
    const advancedOrder = ["temperature", "top_p", "agent_request", "stream_options", ...state.parameterRows, "parameters_json", "section_5"];
    const advanced = [...new Set([...advancedOrder, ...state.rows.keys()])].filter(name => !topRows.includes(name) && !simpleRows.includes(name) && !modelRows.includes(name) && !name.startsWith("heading_") && name !== "console_output");
    const ordered = [...topRows, "heading_model", ...modelRows, "heading_standard", ...simpleRows, "heading_advanced", ...advanced, "console_output"];
    const rows = ordered.flatMap(name => {
        const row = state.rows.get(name);
        return row ? [state.socketWidgets.get(name), row].filter(Boolean) : [];
    });
    // Backing widget order is part of the saved-workflow format; only move UI rows.
    const orderedWidgets = [...node.widgets.filter(w => !rows.includes(w)), ...rows];
    for (const [name, row] of state.rows) {
        const section = modelRows.includes(name) ? "model" : simpleRows.includes(name) ? "standard" : "advanced";
        if (name.startsWith("heading_")) {
            const key = name.slice(8), open = sections[key] !== false;
            const button = row.element.querySelector("button");
            button.textContent = `${open ? "\u25bc" : "\u25b6"} ${key === "model" ? "Model" : key === "standard" ? "Simple" : "Advanced"}`;
            button.setAttribute("aria-expanded", String(open));
            continue;
        }
        const unavailable = ["image", "video"].includes(name) && !state.caps?.input_modalities?.includes(name) && !connected(node, name) || name === "api_key_env" && !connected(node, name) || name === "section_4" && !state.status.classList.contains("rm040-error");
        const folded = !topRows.includes(name) && sections[section] === false;
        setRowHidden(row, unavailable || folded && !connected(node, name));
        row.rmCompact = !row.hidden && (folded || name === "api_key_env");
        row.element.classList.toggle("rm040-compact", row.rmCompact);
        row.element.dataset.section = section;
        row.element.style.minHeight = `${row.hidden ? 0 : row.options.getMinHeight()}px`;
    }
    if (state.model.disabled || state.rows.get("model_name")?.hidden || state.rows.get("model_name")?.rmCompact) state.modelPicker?.close(false);
    // Reinsert existing widgets through the native API: it tells the renderer
    // to refresh widget sockets before drawing wires. Keep instances and order.
    node.widgets.splice(0, node.widgets.length);
    for (const existingWidget of orderedWidgets) node.addCustomWidget(existingWidget);
    bindRows(state);
    if (fit && node.graph) {
        node.setSize([node.size[0], node.computeSize()[1]]);
        node.graph.setDirtyCanvas(true, true);
    }
}

function setRowHidden(row, hidden) {
    // Canvas layout reads widget.hidden; Nodes 2.0 reads options.hidden.
    row.hidden = hidden;
    row.options.hidden = hidden;
    row.element.hidden = hidden;
}

function addRow(state, name, children, height, grow = false) {
    const row = element("div", undefined, "rm040-llm rm040-widget-row");
    row.dataset.setting = name;
    row.append(...children);
    let w;
    const rowHeight = () => w?.rmCompact ? 24 : (typeof height === "function" ? height() : height) + (row.querySelector(".rm040-error") ? 42 : 0);
    // Vue DOM widgets use CSS sizing, independently of LiteGraph's allocation.
    row.style.minHeight = `${rowHeight()}px`;
    w = state.node.addDOMWidget(`rm_row_${name}`, "rm_llm_row", row, {
        margin: 0, hideOnZoom: false, getMinHeight: rowHeight,
        getMaxHeight: () => grow && !w?.rmCompact ? Infinity : rowHeight(),
        getValue: () => "", setValue: () => {}, serialize: false,
    });
    w.serialize = false;
    state.rows.set(name, w);
    return w;
}

function bindRows(state) {
    const node = state.node;
    for (const [name, socketWidget] of state.socketWidgets) {
        if (node.inputs.some(input => input.name === name)) continue;
        node.removeWidget(socketWidget);
        state.socketWidgets.delete(name);
    }
    for (const input of node.inputs || []) {
        const row = state.rows.get(input.name);
        let socketWidget = state.socketWidgets.get(input.name);
        if (input.link != null || !row || socketWidget) {
            if (!socketWidget) {
                // Native DOM widgets hide when their socket is linked. A zero-height
                // canvas widget anchors the socket without hiding the visible row.
                socketWidget = node.addCustomWidget({
                    name: `rm_socket_${input.name}`, type: "rm_llm_socket", value: "",
                    serialize: false, options: {},
                    computeLayoutSize: () => ({ minHeight: 0, maxHeight: 0, minWidth: 0 }),
                    draw() {},
                });
                state.socketWidgets.set(input.name, socketWidget);
            }
            socketWidget.hidden = !row || row.hidden;
            socketWidget.options.hidden = socketWidget.hidden;
        }
        input.widget = { name: (socketWidget || row).name };
        input.alwaysVisible = !!row && !row.hidden;
    }
    node.graph?.setDirtyCanvas(true, true);
}

function syncMediaAvailability(state) {
    const modalities = state.caps?.input_modalities || [];
    state.mediaSlotDefaults ||= new Map();
    for (const [name, title] of [["image", "Image"], ["video", "Video"]]) {
        const input = state.node.inputs?.find(candidate => candidate.name === name);
        const row = state.rows.get(name);
        const label = row?.element.querySelector("label");
        if (!input) continue;
        if (!state.mediaSlotDefaults.has(name)) {
            // Older workflows saved our N/A colours as socket overrides.
            // They must not become the normal colour when vision is available.
            state.mediaSlotDefaults.set(name, {
                color_on: input.color_on === "#777777" ? undefined : input.color_on,
                color_off: input.color_off === "#555555" ? undefined : input.color_off,
            });
        }
        const unavailable = state.caps != null && input.link != null && !modalities.includes(name);
        const defaults = state.mediaSlotDefaults.get(name);
        if (unavailable) {
            input.color_on = "#777777";
            input.color_off = "#555555";
            if (label) {
                label.textContent = "N/A";
                label.title = `${title} input is unavailable for the selected model; the connection will be ignored.`;
                label.classList.add("rm040-media-unavailable");
            }
        } else {
            if (defaults.color_on === undefined) delete input.color_on;
            else input.color_on = defaults.color_on;
            if (defaults.color_off === undefined) delete input.color_off;
            else input.color_off = defaults.color_off;
            if (label) {
                label.textContent = title;
                label.title = "";
                label.classList.remove("rm040-media-unavailable");
            }
        }
    }
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
        w.element.classList.add("rm040-param");
        state.parameterRows.add(name);
    }
    // Older workflows may retain an unconnected socket no longer declared by
    // the backend. Bind it too, so it cannot become a loose socket at the top.
    if (!state.rows.has("stream_options") && state.node.inputs?.some(input => input.name === "stream_options")) {
        const label = element("label", "stream_options");
        label.title = "Optional streaming configuration. Controls appear when advertised by the selected model.";
        addRow(state, "stream_options", [label], 24);
        state.parameterRows.add("stream_options");
    }
    // Keep saved connections attached to a row while capabilities are loading,
    // or when the selected model no longer advertises their controls.
    for (const input of state.node.inputs || []) {
        if (input.link == null || state.rows.has(input.name)) continue;
        const thinking = ["reasoning.enabled", templatePrefix + "enable_thinking"].includes(input.name);
        const label = element("label", thinking ? "Thinking/Reasoning" : input.name);
        label.title = "Value supplied by the connected node. Model support is checked during execution.";
        addRow(state, input.name, [label], 24);
        state.parameterRows.add(input.name);
    }
    layoutSections(state);
}

function syncSockets(state) {
    const sockets = { ...coreSockets, creativity: "FLOAT" };
    if (state.rows.has("agent_request")) sockets.agent_request = "RM_LLM_AGENT_REQUEST";
    delete sockets.api_key_env;
    for (const [name, type] of Object.entries(sockets)) {
        let input = state.node.inputs?.find(input => input.name === name);
        if (!input) { state.node.addInput(name, type); input = state.node.inputs.at(-1); }
        input.type = type;
    }
    const supported = settingDefinitions(state);
    for (const [name, schema] of Object.entries(supported)) {
        if (name in sockets) continue;
        const input = state.node.inputs?.find(input => input.name === name);
        if (!input) state.node.addInput(name, socketType(schema));
    }
    // Capability changes affect rows, never the identity/order of saved sockets.
    bindRows(state);
    syncMediaAvailability(state);
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
    state.creativity.style.setProperty("--rm040-fill", `calc(${actual}% + ${12 - .24 * actual}px)`);
}

function syncCreativity(state, edited) {
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
    const line = element("div", undefined, "rm040-row");
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
        const thinkingToggle = reasoningToggle || name === templatePrefix + "enable_thinking";
        const row = element("div", undefined, "rm040-param");
        const label = element("label", thinkingToggle ? "Thinking/Reasoning" : nested ? `Chat template · ${optionName}` : name);
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
        input.className = "rm040-wide";
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
        const help = element("div", undefined, "rm040-note");
        const guidance = name === "top_k" && state.caps.provider === "Featherless" ? "Whole number: -1 considers all tokens; a positive count such as 40 limits sampling." : kind === "integer" ? "Enter a whole number, or leave blank for provider default." : "Enter a value, leave blank for provider default, or connect another node.";
        const update = () => {
            state.invalid.delete(name);
            input.setCustomValidity(""); input.removeAttribute("aria-invalid"); help.classList.remove("rm040-error");
            input.disabled = connected(state.node, name) || connected(state.node, "parameters_json") || (reasoningToggle && (connected(state.node, "reasoning") || state.caps.reasoning_options?.mandatory)) || (["temperature", "top_p"].includes(name) && connected(state.node, "creativity")) || (nested && connected(state.node, "chat_template_kwargs"));
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
                    help.textContent = message; help.classList.add("rm040-error"); note(state, message, true); return;
                }
            }
            setValue(state.node, "parameters_json", JSON.stringify(saved));
            if (!state.invalid.size && state.status.classList.contains("rm040-error")) note(state, "Settings are valid. Connected inputs take precedence; blank fields use provider defaults.");
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
            if (name === "reasoning_effort" && input.value && !input.disabled) {
                saved.reasoning = { ...(saved.reasoning || {}), enabled: input.value !== "none" };
                delete saved.reasoning.effort;
                delete saved.reasoning.max_tokens;
                setValue(state.node, "parameters_json", JSON.stringify(saved));
            }
            if (["temperature", "top_p"].includes(name)) syncCreativity(state, name);
            if (["reasoning", "reasoning.enabled", "reasoning_effort"].includes(name) && !state.invalid.size) renderControls(state);
        };
        input.oninput = edited; input.onchange = edited; state.validators.set(name, update); update();
        row.append(label, switchLine || input, help); state.controls.append(row);
    }
    const info = state.caps.endpoints[0];
    state.capInfo.textContent = `Context: ${info?.context_length?.toLocaleString() ?? "Provider-defined"}  |  Output limit: ${info?.max_tokens?.toLocaleString() ?? "Provider-defined"}`;
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

function watchCatalog(provider, update, active = () => true) {
    let stopped = false;
    let timer;
    const poll = async () => {
        if (stopped || !active()) return;
        try {
            const result = await call("catalog_status", { provider });
            if (!stopped && active() && result.progress?.state) update(result.progress);
        } catch { /* A progress check must not replace the catalog result/error. */ }
        if (!stopped && active()) timer = setTimeout(poll, 1000);
    };
    timer = setTimeout(poll, 250);
    return () => { stopped = true; clearTimeout(timer); };
}

let modelListSequence = 0;
function installModelPicker(state) {
    const input = state.model;
    const dropdown = element("div", undefined, "rm040-model-dropdown");
    const list = element("div", undefined, "rm040-model-options");
    list.id = `rm040-model-options-${++modelListSequence}`;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", "Models");
    const progress = element("div", undefined, "rm040-catalog-progress");
    progress.setAttribute("role", "progressbar");
    progress.setAttribute("aria-valuemin", "0"); progress.setAttribute("aria-valuemax", "100");
    const fill = element("div", undefined, "rm040-catalog-progress-fill");
    progress.append(fill);
    dropdown.append(list, progress); dropdown.hidden = true;
    state.rows.get("model_name").element.append(dropdown);
    input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", list.id); input.setAttribute("aria-expanded", "false");
    const loads = new Map();
    let open = false, removed = false, matches = [], shown = 0, active = -1;
    let committed = modelSelection(state);
    function resize(height) {
        if (state.modelDropdownHeight === height) return;
        state.modelDropdownHeight = height;
        layoutSections(state, true);
    }
    function close(fit = true) {
        open = false; dropdown.hidden = true; active = -1;
        input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant");
        if (fit) resize(0);
        else state.modelDropdownHeight = 0;
    }
    function commit(model = input.value.trim()) {
        if (input.disabled) return close();
        const provider = value(state.node, "provider");
        if (provider !== committed.provider || model !== committed.model) {
            setValue(state.node, "parameters_json", "{}"); setValue(state.node, "endpoint", "Auto");
        }
        setValue(state.node, "model_name", model); input.value = model;
        const changed = provider !== committed.provider || model !== committed.model;
        committed = { provider, model }; close();
        if (changed || !state.caps) void loadCapabilities(state);
    }
    function appendOptions() {
        const end = Math.min(matches.length, shown + 50);
        for (; shown < end; shown++) {
            const model = matches[shown], index = shown;
            const option = element("button", model.id, "rm040-model-option");
            option.type = "button"; option.tabIndex = -1; option.id = `${list.id}-${index}`;
            option.title = `${model.name || model.id}${model.available_on_current_plan === false ? " (not on current plan)" : ""}`;
            option.setAttribute("role", "option"); option.setAttribute("aria-selected", String(index === active));
            option.onpointerdown = event => { event.preventDefault(); event.stopPropagation(); };
            option.onclick = () => commit(model.id);
            list.append(option);
        }
    }
    function render() {
        if (!open || removed) return;
        const provider = value(state.node, "provider"), models = state.models[provider] || [];
        const load = loads.get(provider);
        const q = input.value.toLocaleLowerCase().trim();
        matches = models.filter(model => `${model.id} ${model.name || ""}`.toLocaleLowerCase().includes(q));
        active = -1; shown = 0; input.removeAttribute("aria-activedescendant");
        list.replaceChildren(); list.scrollTop = 0;
        list.hidden = models.length === 0; progress.hidden = models.length !== 0;
        dropdown.title = load?.error || "";
        if (!models.length) {
            const p = load?.progress || {};
            const count = Math.max(0, Number(p.count || 0));
            // Without a published total, estimate the catalog size from progress.
            const total = Number(p.total) > 0 ? Number(p.total) : Math.max(10000, count * 1.25);
            const fraction = Math.min(0.98, Math.max(load?.fraction || 0.03, count / total));
            if (load) load.fraction = fraction;
            fill.style.width = `${fraction * 100}%`;
            const paused = ["paused", "failed"].includes(p.state) || load && !load.loading;
            const status = paused ? "Try later. Focus Model Name again to resume." : "Downloading model catalog";
            progress.setAttribute("aria-label", status); progress.setAttribute("aria-valuetext", status);
            progress.setAttribute("aria-valuenow", String(Math.round(fraction * 100)));
            progress.title = load?.error || status;
            resize(18);
        } else {
            if (matches.length) appendOptions();
            else list.append(element("div", "No matching models", "rm040-model-empty"));
            resize(Math.max(1, Math.min(10, matches.length)) * 32 + 6);
        }
    }
    async function loadCatalog(provider) {
        if (loads.get(provider)?.loading) return;
        const load = { loading: true, progress: {}, fraction: 0.03, error: "" };
        loads.set(provider, load);
        render();
        load.stop = watchCatalog(provider, p => {
            load.progress = p;
            state.updateCatalogCount?.(provider, p.count);
            if (provider === value(state.node, "provider") && !state.models[provider]?.length) render();
        }, () => !removed);
        try {
            const response = await call("models", { ...selection(state), provider });
            if (removed) return;
            state.models[provider] = response.models;
            state.updateCatalogCount?.(provider, response.models.length);
            load.progress = response.progress || {};
            load.error = response.warning || "";
        } catch (error) {
            load.error = error.message;
            load.progress.state = "failed";
        } finally {
            load.loading = false; load.stop();
            if (provider === value(state.node, "provider")) render();
        }
    }
    function show() {
        if (input.disabled || removed) return;
        open = true; dropdown.hidden = false; input.setAttribute("aria-expanded", "true"); render();
        const provider = value(state.node, "provider");
        if (!state.models[provider]?.length || loads.get(provider)?.error) void loadCatalog(provider);
    }
    input.onfocus = show;
    input.onclick = () => { if (!open) show(); };
    input.oninput = () => {
        if (input.value !== value(state.node, "model_name")) {
            setValue(state.node, "parameters_json", "{}"); setValue(state.node, "endpoint", "Auto");
        }
        setValue(state.node, "model_name", input.value);
        if (open) render(); else show();
    };
    input.onblur = () => commit();
    input.onkeydown = event => {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
        else if (event.key === "Enter") {
            event.preventDefault(); event.stopPropagation(); commit(active >= 0 ? matches[active].id : undefined);
        } else if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault(); event.stopPropagation();
            if (!open) show();
            if (!matches.length) return;
            active = Math.max(0, Math.min(matches.length - 1, active + (event.key === "ArrowDown" ? 1 : -1)));
            while (shown <= active) appendOptions();
            for (let index = 0; index < shown; index++) list.children[index].setAttribute("aria-selected", String(index === active));
            const option = list.children[active]; input.setAttribute("aria-activedescendant", option.id);
            option.scrollIntoView({ block: "nearest" });
        }
    };
    list.onscroll = () => { if (list.scrollTop + list.clientHeight >= list.scrollHeight - 32) appendOptions(); };
    list.onwheel = event => event.stopPropagation();
    state.modelPicker = {
        close,
        sync() { close(); committed = modelSelection(state); input.value = committed.model || ""; },
    };
    state.disposers.push(() => {
        removed = true; close(false);
        for (const load of loads.values()) load.stop?.();
    });
}

function addModelHeading(state) {
    const providerText = element("span", "", "rm040-model-name");
    const countText = element("span", "Models: —", "rm040-note");
    const providerPair = element("div", undefined, "rm040-heading-pair");
    providerPair.append(providerText, countText);
    const text = element("span", "", "rm040-model-name");
    const modelPair = element("div", undefined, "rm040-heading-pair");
    modelPair.append(text, state.capInfo);
    const row = addRow(state, "model_heading", [providerPair, modelPair], 128);
    row.element.classList.add("rm040-model-heading");
    const counts = new Map();
    let requestedProvider, removedNode = false;
    const updateCount = () => {
        const { provider } = modelSelection(state);
        const count = counts.get(provider) ?? state.models[provider]?.length;
        countText.textContent = `Models: ${count == null ? "—" : count.toLocaleString()}`;
    };
    state.updateCatalogCount = (provider, count) => {
        if (!removedNode && Number.isSafeInteger(count) && count >= 0) {
            counts.set(provider, count);
            updateCount();
        }
    };
    const fit = () => {
        if (!row.element.isConnected || row.element.clientWidth === 0) return;
        // Measure in CSS pixels so browser zoom and canvas zoom do not skew fitting.
        for (let size = 32; size >= 10; size--) {
            providerText.style.fontSize = text.style.fontSize = `${size}px`;
            if (text.scrollWidth <= text.clientWidth && providerText.scrollWidth <= providerText.clientWidth) break;
        }
    };
    state.updateModelHeading = () => {
        const { provider, model } = modelSelection(state);
        const previousProvider = state.provider.value;
        state.provider.value = provider || "";
        const envName = value(state.node, "api_key_env");
        let envChanged = false;
        if (connected(state.node, "provider") && defaults[provider] && !connected(state.node, "api_key_env") && Object.values(defaults).includes(envName) && envName !== defaults[provider]) {
            setValue(state.node, "api_key_env", defaults[provider]);
            state.env.value = defaults[provider];
            envChanged = true;
        }
        if (envChanged || previousProvider !== state.provider.value) void state.refreshCredentialStatus();
        providerText.textContent = provider || "Select a provider";
        updateCount();
        text.textContent = connected(state.node, "model_name") ? model ? `${model} (last execution)` : "Awaiting connected model" : String(model || "Select a model");
        if (document.activeElement !== state.model) state.model.value = model || "";
        state.model.placeholder = connected(state.node, "model_name") ? "Awaiting connected model" : "Type or select a model";
        text.title = text.textContent;
        fit();
        if (provider && requestedProvider !== provider) {
            requestedProvider = provider;
            // Read saved/local counts only; this does not start a catalog download.
            void call("catalog_status", { provider }).then(result => state.updateCatalogCount(provider, result.progress?.count)).catch(() => {});
        }
    };
    const observer = new ResizeObserver(fit);
    observer.observe(row.element);
    state.disposers.push(() => {
        removedNode = true;
        observer.disconnect();
    });
    state.updateModelHeading();
}

function setup(node, nodeData) {
    if (states.has(node)) return;
    for (const w of node.widgets || []) {
        w.hidden = true;
        w.options ||= {};
        w.options.hidden = true;
        if (w.inputEl) w.inputEl.style.display = "none";
    }
    const panel = element("div", undefined, "rm040-llm");
    const state = { node, panel, disposers: [], sessions: {}, models: {}, caps: null, revision: 0, invalid: new Map(), validators: new Map(), bindings: new Map(), rows: new Map(), socketWidgets: new Map(), parameterRows: new Set() };
    states.set(node, state);
    function label(text, control) { panel.append(element("label", text), control); return control; }
    function bound(name, tag = "input") {
        const input = document.createElement(tag);
        input.className = "rm040-wide";
        input.value = value(node, name) ?? "";
        input.oninput = () => setValue(node, name, name === "timeout_seconds" ? Number(input.value) : input.value);
        state.bindings.set(name, input);
        return input;
    }
    state.provider = document.createElement("select");
    for (const p of Object.keys(defaults)) {
        state.provider.add(new Option(p, p));
    }
    label("Provider", state.provider);
    state.bindings.set("provider", state.provider);
    state.model = document.createElement("input"); state.model.className = "rm040-wide";
    state.model.type = "text"; state.model.value = value(node, "model_name") || "";
    state.model.placeholder = "Type or select a model"; state.model.autocomplete = "off"; state.model.spellcheck = false;
    state.model.setAttribute("aria-label", "Model Name");
    state.bindings.set("model_name", state.model);
    label("Model Name", state.model);
    state.mode = document.createElement("select");
    state.mode.setAttribute("aria-label", "API Key System");
    for (const m of ["Environment variable", "Masked session key"]) state.mode.add(new Option(m, m));
    label("API Key System", state.mode);
    state.bindings.set("credential_source", state.mode);
    state.env = label("API-key environment variable name", bound("api_key_env"));
    const keyRow = element("div", undefined, "rm040-row");
    const password = document.createElement("input");
    password.type = "password"; password.autocomplete = "off"; password.placeholder = "Paste API key";
    password.setAttribute("aria-label", "API key"); password.spellcheck = false;
    const setKey = element("button", "Set");
    keyRow.append(password, setKey);
    label("API Key (Key hidden. Never shared in workflows.)", keyRow);
    const setKeyStatus = (status) => {
        setKey.classList.remove("rm040-key-status-ready", "rm040-key-status-missing", "rm040-key-status-unknown");
        setKey.classList.add(`rm040-key-status-${status}`);
        setKey.setAttribute("aria-label", status === "ready" ? "API key available" : status === "missing" ? "API key needed" : "API key status unknown");
    };
    const refreshCredentialStatus = async () => {
        const provider = state.provider.value;
        const credentialSource = state.mode.value;
        const revision = state.credentialRevision = (state.credentialRevision || 0) + 1;
        setKeyStatus("unknown");
        if (credentialSource === "Masked session key" && !state.sessions[provider]) {
            setKeyStatus("missing");
            return;
        }
        try {
            const result = await call("credential_status", {
                provider,
                credential_source: credentialSource,
                env_name: value(node, "api_key_env"),
                session: credentialSource === "Masked session key" ? state.sessions[provider] : undefined,
            });
            if (revision !== state.credentialRevision) return;
            setKeyStatus(result.key_present ? "ready" : "missing");
        } catch (error) {
            if (revision === state.credentialRevision) {
                setKeyStatus("missing");
                note(state, error.message, true);
            }
        }
    };
    state.refreshCredentialStatus = refreshCredentialStatus;
    state.env.addEventListener("change", () => void refreshCredentialStatus());
    const updateMode = () => {
        keyRow.hidden = false;
        const row = state.rows.get("section_0");
        if (row) layoutSections(state);
        state.env.disabled = state.mode.value === "Masked session key" || connected(node, "api_key_env");
        void refreshCredentialStatus();
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
                note(state, result.persistent
                    ? `${result.environment_variable} saved for this user and available now. It will be restored after restarting ComfyUI.`
                    : `${result.environment_variable} set for this ComfyUI process only. Restart ComfyUI to enable persistent setup, then set the key again.`);
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
    state.capInfo = element("div", "Context: —  |  Output limit: —", "rm040-note"); panel.append(state.capInfo);
    state.controls = element("div"); panel.append(state.controls);
    state.timeout = label("Request timeout (seconds)", bound("timeout_seconds"));
    state.timeout.type = "number"; state.timeout.min = "10"; state.timeout.max = "3600";
    state.status = element("div", "Ready. Model weights remain hosted by the provider.", "rm040-note"); panel.append(state.status);
    state.output = document.createElement("textarea"); state.output.readOnly = true; state.output.placeholder = "Response preview"; panel.append(state.output);
    const displayRows = new Map([[keyRow, "section_0"], [state.status, "section_4"], [state.output, "section_5"]]);
    for (const child of [...panel.children]) {
        if (child.parentElement !== panel || child === state.controls || child === state.capInfo) continue;
        const children = [child];
        if (child.tagName === "LABEL") children.push(child.nextElementSibling);
        const control = children.at(-1);
        const name = [...state.bindings].find(([, el]) => el === control)?.[0] || displayRows.get(control);
        const multiline = control.tagName === "TEXTAREA";
        addRow(state, name, children, name === "model_name" ? () => 58 + (state.modelDropdownHeight || 0) : multiline ? 108 : control === keyRow ? 64 : child.classList.contains("rm040-note") ? 36 : 58, multiline);
    }
    state.console = document.createElement("input");
    state.console.type = "checkbox";
    state.console.setAttribute("role", "switch");
    state.console.setAttribute("aria-label", "Console output");
    const consoleState = element("span", "Off");
    const consoleLine = element("div", undefined, "rm040-row");
    consoleLine.append(state.console, consoleState);
    state.console.onchange = () => {
        setValue(node, "console_output", state.console.checked);
        consoleState.textContent = state.console.checked ? "On" : "Off";
    };
    state.bindings.set("console_output", state.console);
    addRow(state, "console_output", [element("label", "Live console output"), consoleLine], 58);
    for (const name of ["image", "video"]) {
        addRow(state, name, [element("label", name === "image" ? "Image" : "Video")], 24);
    }
    if (nodeData.input.optional.agent_request) {
        const label = element("label", "agent_request");
        label.title = nodeData.input.optional.agent_request[1]?.tooltip || "Connected agent/tool request.";
        addRow(state, "agent_request", [label], 24);
    }
    for (const name of ["model", "standard", "advanced"]) {
        const button = element("button", undefined, "rm040-section");
        button.type = "button";
        button.onclick = () => {
            const sections = node.properties.rm_llm_sections;
            sections[name] = sections[name] === false;
            layoutSections(state, true);
        };
        addRow(state, `heading_${name}`, [button], 42);
    }
    addCreativity(state);
    addModelHeading(state);
    installModelPicker(state);
    installExecutionWidgets(state);
    state.sync = () => {
        state.validators.clear();
        state.invalid.clear();
        setValue(node, "endpoint", "Auto");
        state.updateModelHeading?.();
        state.provider.value = value(node, "provider");
        state.modelPicker.sync();
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
        // Parameter children were moved into DOM widgets; rebuild before mounting.
        if (state.caps) renderControls(state);
        else mountParameterRows(state);
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
        state.invalid.clear(); state.capInfo.textContent = "Context: —  |  Output limit: —";
        password.value = ""; state.sync(); note(state, "Type or select a model in Model Name.");
    };
    state.sync();
    node.setSize([Math.max(node.size[0], 500), node.computeSize()[1]]);
    layoutSections(state, true);
}

function installExecutionWidgets(state) {
    const node = state.node;
    const settings = widget(node, "parameters_json");
    const ticket = widget(node, "key_ticket");
    // These are this node's widget callbacks, not replacements for shared methods.
    settings.serializeValue = () => {
        if (!connected(node, "parameters_json")) {
            for (const validate of state.validators.values()) validate();
            if (state.invalid.size) throw new Error(`RM-LLM: ${[...state.invalid.values()].join(" ")}`);
        }
        return settings.value;
    };
    let queued = false;
    ticket.value = "";
    ticket.beforeQueued = () => { queued = (node.mode ?? 0) === 0; };
    ticket.afterQueued = () => { queued = false; };
    ticket.serializeValue = async () => {
        const forQueue = queued;
        queued = false;
        // Workflow saving reads widget.value; API export never prepares a ticket.
        if (!forQueue || app.processingQueue !== true) return "";
        const source = connectedStaticString(node, "credential_source") ?? value(node, "credential_source");
        if (source !== "Masked session key") return "";
        const provider = connectedStaticString(node, "provider") ?? value(node, "provider");
        if (connected(node, "provider") && !connectedStaticString(node, "provider")) {
            throw new Error("RM-LLM: use Environment variable for a provider determined during execution.");
        }
        const session = state.sessions[provider];
        if (!session) throw new Error("RM-LLM: API Key Needed!");
        const result = await call("ticket", { provider, session });
        return result.ticket;
    };
    state.disposers.push(() => { queued = false; });
}

function disposeNode(node) {
    const state = states.get(node);
    if (!state) return;
    ++state.revision;
    ++state.credentialRevision;
    for (const dispose of state.disposers) dispose();
    for (const [provider, session] of Object.entries(state.sessions)) {
        void call("key", { provider, session, clear: true }).catch(() => {});
    }
    state.sessions = {};
    states.delete(node);
}

function observeGraph(graph) {
    if (!graph?.events || observedGraphs.has(graph)) return;
    observedGraphs.add(graph);
    graph.events.addEventListener("node:before-removed", event => disposeNode(event.detail.node));
    graph.events.addEventListener("node:slot-links:changed", event => {
        const { nodeId, slotIndex, slotType } = event.detail;
        if (slotType !== 1) return;
        const node = graph.getNodeById(nodeId);
        const state = node && states.get(node);
        if (!state) return;
        const name = node.inputs?.[slotIndex]?.name;
        // The graph event fires while native connection bookkeeping is in progress.
        queueMicrotask(() => {
            if (states.get(node) !== state) return;
            syncConnectedControls(state);
            state.updateModelHeading();
            layoutSections(state, true);
            if (["provider", "model_name"].includes(name)) {
                state.runtimeModel = null;
                void loadCapabilities(state);
            }
        });
    });
    graph.events.addEventListener("subgraph-created", event => observeGraph(event.detail.subgraph));
    for (const subgraph of graph.subgraphs?.values?.() || []) observeGraph(subgraph);
}

function initializeNode(node) {
    if (node.comfyClass !== NODE_ID && node.type !== NODE_ID) return;
    const definition = nodeDefinitions.get(NODE_ID) || node.constructor.nodeData;
    if (!definition?.input?.optional) return;
    setup(node, definition);
    observeGraph(node.graph || app.rootGraph);
}

function receiveOutput(id, output) {
    const node = executionNode(app.rootGraph, id);
    const state = node && states.get(node);
    if (!state) return;
    receiveModel(state, output.rm_llm_model?.[0]);
    state.output.value = (output.text || []).join("\n");
}

function restoreStableInputs(graphData) {
    const definition = nodeDefinitions.get(NODE_ID);
    if (!definition) return;
    const specs = new Map();
    for (const group of ["required", "optional"]) {
        const inputs = definition.input[group] || {};
        for (const name of definition.input_order?.[group] || Object.keys(inputs)) specs.set(name, inputs[name]);
    }
    // Match native construction: declared sockets first, then our widget inputs.
    const nativeNames = [...specs].filter(([, [type, options]]) => options?.forceInput || ["IMAGE", "VIDEO", "RM_LLM_AGENT_REQUEST"].includes(type)).map(([name]) => name);
    const names = [...new Set([...nativeNames, ...Object.keys(coreSockets).filter(name => name !== "api_key_env"), "creativity"])];
    const normalize = graph => {
        const indices = new Map();
        for (const node of graph.nodes || []) {
            if (node.type !== NODE_ID) continue;
            const previous = node.inputs || [];
            const byName = new Map(previous.map(input => [input.name, input]));
            node.inputs = names.map(name => byName.get(name) || { name, type: specs.get(name)?.[0] || coreSockets[name], link: null });
            node.inputs.push(...previous.filter(input => !names.includes(input.name)));
            indices.set(String(node.id), previous.map(input => node.inputs.findIndex(candidate => candidate.name === input.name)));
            for (const input of node.inputs) {
                // UI anchors are recreated after loading. Native configure needs
                // the backend widget name, never a temporary rm_row/rm_socket name.
                if (specs.has(input.name) && !nativeNames.includes(input.name)) input.widget = { name: input.name };
                else delete input.widget;
            }
        }
        for (const link of [...(graph.links || []), ...(graph.floatingLinks || [])]) {
            const array = Array.isArray(link);
            const index = indices.get(String(array ? link[3] : link.target_id))?.[array ? link[4] : link.target_slot];
            if (index == null) continue;
            if (array) link[4] = index;
            else link.target_slot = index;
        }
        for (const subgraph of graph.definitions?.subgraphs || []) normalize(subgraph);
    };
    normalize(graphData);
}

app.registerExtension({
    name: "RM.LLM.040",
    beforeRegisterNodeDef(_nodeType, nodeData) {
        if (nodeData.name === NODE_ID) nodeDefinitions.set(NODE_ID, nodeData);
    },
    beforeConfigureGraph(graphData) {
        restoreStableInputs(graphData);
    },
    nodeCreated(node) {
        initializeNode(node);
    },
    loadedGraphNode(node) {
        initializeNode(node);
        const state = states.get(node);
        if (!state) return;
        state.sync();
    },
    afterConfigureGraph() {
        observeGraph(app.rootGraph);
        const visited = new Set();
        const fitGraph = graph => {
            if (!graph || visited.has(graph)) return;
            visited.add(graph);
            for (const node of graph.nodes || graph._nodes || []) {
                const state = states.get(node);
                if (state) layoutSections(state, true);
                if (node.subgraph) fitGraph(node.subgraph);
            }
        };
        fitGraph(app.rootGraph);
    },
    onNodeOutputsUpdated(outputs) {
        for (const [id, output] of Object.entries(outputs)) receiveOutput(id, output);
    },
    setup() {
        observeGraph(app.rootGraph);
        api.addEventListener("rm040-llm-model", ({ detail }) => {
            const node = executionNode(app.rootGraph, detail.node);
            const state = node && states.get(node);
            if (state) receiveModel(state, detail.model_info);
        });
        api.addEventListener("executed", ({ detail }) => {
            if (detail?.node != null && detail.output) receiveOutput(detail.node, detail.output);
        });
        api.addEventListener("executing", ({ detail }) => {
            const id = typeof detail === "object" ? detail?.node : detail;
            if (id == null) return;
            const node = executionNode(app.rootGraph, id);
            const state = node && states.get(node);
            if (state && (connected(node, "model_name") || connected(node, "provider"))) {
                state.runtimeModel = null;
                void loadCapabilities(state);
            }
        });
    },
});
