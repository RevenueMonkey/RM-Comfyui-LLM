"""Read template metadata without rendering templates or loading model code."""
import copy
import html
import json
import re
from urllib.parse import quote

import aiohttp
from jinja2 import Environment, TemplateError, meta, nodes

DOC_URL = "https://featherless.ai/docs/chat-template-kwargs"
PREFIX = "chat_template_kwargs."
FIELDS = {
    "enable_thinking": {"type": "boolean", "description": "Enable the model's thinking mode."},
    "preserve_thinking": {"type": "boolean", "description": "Preserve reasoning in supplied conversation history."},
    "clear_thinking": {"type": "boolean", "description": "Clear reasoning from supplied conversation history."},
    "thinking_budget": {"type": "integer", "minimum": 0, "description": "Requested reasoning token budget."},
    "date_string": {"type": "string", "description": "Date supplied to the chat template."},
}
FAMILIES = [
    (r"qwen3[._-]?[56]", "qwen3.5"),
    (r"qwen3(?![._-][0-9]\b)", "qwen3"),
    (r"glm[._-]?(?:4[._-]7|5)", "glm"),
    (r"gemma[._-]?4", "gemma4"),
    (r"deepseek[._-]?v(?:3[._-][12]|4)", "deepseek"),
    (r"kimi[._-]?k2[._-][56]", "kimi"),
]
EXCLUDED = {"messages", "tools", "documents", "add_generation_prompt", "continue_final_message", "raise_exception", "strftime_now", "tokenize", "return_dict", "return_tensors"}


def parse_family_records(page):
    records = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 4:
            continue
        family = cells[0].lower()
        key = next((name for pattern, name in FAMILIES if re.search(pattern, family.replace(" ", "").replace("(", ""))), None)
        if key is None:
            continue
        fields = {}
        if cells[1] in {"enable_thinking", "thinking", "do_reasoning"}:
            fields["enable_thinking"] = {**FIELDS["enable_thinking"], "default_note": cells[2]}
        for option in ("preserve_thinking", "clear_thinking"):
            if option in cells[3]:
                fields[option] = dict(FIELDS[option])
        records[key] = {"family": cells[0], "fields": fields}
    if not {"gemma4", "qwen3.5", "glm"} <= records.keys():
        raise ValueError("Chat-template documentation format changed; previous record retained.")
    return {"source": DOC_URL, "families": records}


def inspect_template(template):
    environment = Environment()
    tree = environment.parse(template)
    names = meta.find_undeclared_variables(tree)
    fields = {}
    for name in names:
        if name in EXCLUDED or name.startswith("_") or name in {"constructor", "prototype"} or name.endswith(("_token", "_tokens")):
            continue
        canonical = "enable_thinking" if name in {"thinking", "do_reasoning"} else name
        if canonical in FIELDS:
            fields[canonical] = dict(FIELDS[canonical])
            continue
        # Expose other variables only when a literal default proves a scalar type.
        for item in tree.find_all(nodes.Filter):
            if item.name not in {"default", "d"} or not isinstance(item.node, nodes.Name) or item.node.name != name or not item.args or not isinstance(item.args[0], nodes.Const):
                continue
            value = item.args[0].value
            kind = {bool: "boolean", int: "integer", float: "number", str: "string"}.get(type(value))
            if kind:
                fields[name] = {"type": kind, "description": "Model-specific chat template variable.", "default_note": str(value)}
    return fields


def rejects_system_role(template):
    """Recognize a direct first-message system-role rejection; do not execute Jinja."""
    tree = Environment().parse(template)
    for statement in tree.body:
        if not isinstance(statement, nodes.If) or not isinstance(statement.test, nodes.Compare):
            continue
        test = statement.test
        if len(test.ops) != 1 or test.ops[0].op != "eq" or not isinstance(test.ops[0].expr, nodes.Const) or test.ops[0].expr.value != "system":
            continue
        role = test.expr
        if not isinstance(role, nodes.Getitem) or not isinstance(role.arg, nodes.Const) or role.arg.value != "role":
            continue
        first = role.node
        if not isinstance(first, nodes.Getitem) or not isinstance(first.node, nodes.Name) or first.node.name != "messages" or not isinstance(first.arg, nodes.Const) or first.arg.value != 0:
            continue
        for output in statement.body:
            if isinstance(output, nodes.Output) and any(isinstance(call, nodes.Call) and isinstance(call.node, nodes.Name) and call.node.name == "raise_exception" for call in output.nodes):
                return True
    return False


async def fetch_template(model):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", model):
        return None, "", False
    root = "https://huggingface.co/" + quote(model, safe="/") + "/raw/main/"
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "RM-LLM/1.0"}, timeout=aiohttp.ClientTimeout(total=8)) as client:
            for filename in ("chat_template.jinja", "tokenizer_config.json"):
                async with client.get(root + filename, allow_redirects=False) as response:
                    if response.status != 200:
                        continue
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > 2 * 1024 * 1024:
                            return None, "", False
                    text = data.decode("utf-8")
                    if filename.endswith(".json"):
                        text = json.loads(text).get("chat_template")
                        if isinstance(text, list):
                            text = next((item.get("template") for item in text if item.get("name") == "default"), None)
                        elif isinstance(text, dict):
                            text = text.get("default")
                    if isinstance(text, str):
                        return inspect_template(text), root + filename, rejects_system_role(text)
    except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError, ValueError, TemplateError):
        pass
    return None, "", False


async def discover_template_options(provider, model, metadata, record):
    if provider != "Featherless":
        return {}, "No provider-supported chat_template_kwargs discovery.", False
    fields = {}
    family_record = record.get("template_options", {})
    identity = (model + " " + str(metadata.get("model_class", ""))).lower()
    family = next((name for pattern, name in FAMILIES if re.search(pattern, identity)), None)
    family_info = family_record.get("families", {}).get(family, {})
    for name, schema in family_info.get("fields", {}).items():
        fields[name] = {**copy.deepcopy(schema), "source": family_record.get("source", DOC_URL), "evidence": "Provider documentation: " + family_info["family"]}
    discovered, url, system_rejected = await fetch_template(model)
    if discovered is not None:
        for name, schema in discovered.items():
            fields[name] = {**fields.get(name, {}), **schema, "source": url, "evidence": "Selected model's public chat template"}
    # These published variants have fixed reasoning behavior, despite broad family names.
    if re.search(r"deepseek[._-]?r1|kimi[._-]?k2[._-]?thinking|minimax[._-]?m2|gpt[._-]?oss|step[._-]?3[._-]?5|qwen3.*(?:instruct|thinking)[._-]2507", identity):
        fields.pop("enable_thinking", None)
    note = "Known chat-template options from model template/provider family documentation; the hosted template may differ."
    if discovered is None:
        note += " Public template unavailable; using documented family options only."
    if not fields:
        note += " No known typed options found; use the JSON field for custom options."
    if system_rejected:
        note += " This model's template rejects the system role; System Prompt instructions are prepended to User Prompt when sending."
    return fields, note, system_rejected
