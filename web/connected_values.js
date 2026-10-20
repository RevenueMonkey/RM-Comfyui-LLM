export function inputLink(graph, id) {
    if (id == null) return null;
    if (typeof id === "object") return id;
    return graph?.getLinkById?.(id)
        ?? (graph?.links instanceof Map ? graph.links.get(id) : graph?.links?.[id])
        ?? null;
}

// Display overlays never write backing widgets or dispatch input/change events.
export function sourceMatches(source, link) {
    return !!link && Array.isArray(source) && String(source[0]) === String(link.origin_id) && source[1] === link.origin_slot;
}

export function restoreControl(record) {
    const { control, value, checked, placeholder, title, visibility, caption, captionText } = record;
    record.option?.remove();
    control.value = value;
    control.checked = checked;
    control.placeholder = placeholder;
    control.title = title;
    control.style.visibility = visibility;
    if (caption) caption.textContent = captionText;
    if (record.label) delete record.label.dataset.rmConnected;
}

export function displayControl(control, label, packet, record) {
    if (!record || record.control !== control) {
        const caption = control.type === "checkbox" ? control.nextElementSibling : null;
        record = { control, label, value: control.value, checked: control.checked,
            placeholder: control.placeholder, title: control.title, visibility: control.style.visibility,
            caption, captionText: caption?.textContent };
    }
    const known = packet && Object.hasOwn(packet, "value");
    const text = known ? String(packet.value) : "";
    record.option?.remove(); record.option = null;
    if (control.tagName === "SELECT" && known && ![...control.options].some(o => o.value === text)) {
        record.option = new Option(text, text); control.add(record.option);
    }
    control.value = text;
    if (control.type === "checkbox") {
        control.checked = known && packet.value === true;
        if (record.caption) record.caption.textContent = known ? (control.checked ? "On" : "Off") : "Connected";
    }
    control.style.visibility = !known && ["checkbox", "range"].includes(control.type) ? "hidden" : record.visibility;
    control.placeholder = known ? record.placeholder : "Connected";
    control.title = known ? "Value received from the connected input on the last run." : "Connected; awaiting a value from execution.";
    control.disabled = true;
    if (label) label.dataset.rmConnected = known ? "last run" : "connected";
    return record;
}
