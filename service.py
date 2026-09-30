"""Provider metadata and in-memory credentials. No credentials are written to disk."""
import asyncio
import copy
import html
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import aiohttp
from aiohttp import web
from server import PromptServer
from .template_options import DOC_URL, discover_template_options, parse_family_records

ROOT = Path(__file__).resolve().parent
PROVIDERS = {
    "OpenRouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "Featherless": ("https://api.featherless.ai/v1", "FEATHERLESS_API_KEY"),
    "LithosAI": ("https://api.lithosai.cloud/v1", "LITHOSAI_API_KEY"),
}
RECORD_PATH = ROOT / "capability_records.json"
LOCK = threading.RLock()
DETAILS = {}
SESSIONS = {}
TICKETS = {}
SESSION_TTL = 12 * 3600
TICKET_TTL = 24 * 3600
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


class RMError(ValueError):
    pass


class ProviderHTTPError(RMError):
    def __init__(self, status, message, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def provider_error(status, raw, key="", retry_header=None, *, http_status=None):
    hints = {
        400: "Check the request settings or whether the model is ready for inference.",
        401: "API key is missing or invalid.",
        402: "Insufficient credits.",
        403: "Access denied; check key, plan, model gating, or provider access.",
        404: "Model or endpoint is unavailable. Refresh the catalog.",
        429: "Rate or concurrency limit reached. Try again later.",
        500: "The provider encountered an internal error.",
        502: "The provider's upstream service failed.",
        503: "The provider has no available model capacity or is temporarily unavailable.",
        504: "The provider's upstream service timed out.",
    }
    detail = ""
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        document = None
    if isinstance(document, dict):
        error = document.get("error", document)
        if isinstance(error, str):
            detail = error
        elif isinstance(error, dict):
            message = error.get("message") or error.get("detail") or error.get("error")
            if isinstance(message, str):
                detail = message
            code = error.get("code") or error.get("type")
            if isinstance(code, (str, int)):
                detail += f" (code: {code})"
    # Do not print HTML error pages, whole JSON bodies, headers or request payloads.
    # Redact before truncation so a long credential cannot leave a partial prefix.
    if key:
        detail = detail.replace(key, "[REDACTED]")
        detail = detail.replace(json.dumps(key)[1:-1], "[REDACTED]")
    detail = re.sub(r"(?i)Bearer\s+[^\s,;]+", "Bearer [REDACTED]", detail)
    detail = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", detail).strip()[:700]
    retry_after = None
    if retry_header:
        try:
            retry_after = max(0.0, float(retry_header))
            if not 0 <= retry_after < float("inf"):
                retry_after = None
        except ValueError:
            try:
                retry_after = max(0.0, (parsedate_to_datetime(retry_header) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    prefix = (f"Provider API error {status or '(unspecified code)'} (HTTP {http_status})."
              if http_status is not None else f"Provider HTTP {status}.")
    message = f"{prefix} {hints.get(status, 'Request rejected by the provider.')}"
    if detail:
        message += f" Provider detail: {detail}"
    return ProviderHTTPError(status, message, retry_after)


def provider_info(provider):
    if provider not in PROVIDERS:
        raise RMError("Select OpenRouter, Featherless, or LithosAI.")
    return PROVIDERS[provider]


def environment_key(provider, name="", required=False):
    name = name.strip() or provider_info(provider)[1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
        raise RMError("Enter an environment variable name, not an API key.")
    key = os.environ.get(name, "").strip()
    if key and (len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key)):
        raise RMError("The API-key environment variable contains an invalid credential value.")
    if required and not key:
        raise RMError(f"{name} is not set in the ComfyUI process. Use the masked key field or the supplied launcher.")
    return key


def set_process_environment_key(provider, name, key):
    """Set a provider key for this ComfyUI process without saving it in a workflow."""
    provider_info(provider)
    name = name.strip() or provider_info(provider)[1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
        raise RMError("Enter an environment variable name, not an API key.")
    if not isinstance(key, str) or not 1 <= len(key.strip()) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key.strip()):
        raise RMError("API key must be nonempty text without spaces or control characters.")
    os.environ[name] = key.strip()
    return name


def prune_credentials():
    now = time.monotonic()
    for table in (SESSIONS, TICKETS):
        for token in list(table):
            if table[token][0] <= now:
                del table[token]


def store_session(provider, key):
    provider_info(provider)
    if not isinstance(key, str) or not 1 <= len(key.strip()) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key.strip()):
        raise RMError("API key must be nonempty text without spaces or control characters.")
    with LOCK:
        prune_credentials()
        if len(SESSIONS) >= 256:
            raise RMError("Too many active key sessions. Clear unused sessions or restart ComfyUI.")
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = (time.monotonic() + SESSION_TTL, provider, key.strip())
    return token


def session_key(provider, token):
    with LOCK:
        prune_credentials()
        entry = SESSIONS.get(token)
        if not entry or entry[1] != provider:
            raise RMError("The masked key session expired. Enter the key again.")
        return entry[2]


def issue_ticket(provider, session):
    with LOCK:
        key = session_key(provider, session)
        if len(TICKETS) >= 1024:
            raise RMError("Too many queued key tickets. Wait for queued requests to finish.")
        token = secrets.token_urlsafe(32)
        TICKETS[token] = (time.monotonic() + TICKET_TTL, provider, key)
    return token


def consume_key(provider, ticket, env_name):
    if not ticket:
        return environment_key(provider, env_name, required=True)
    with LOCK:
        prune_credentials()
        entry = TICKETS.pop(ticket, None)
    if not entry or entry[1] != provider:
        raise RMError("The request's key ticket expired or was already used. Queue it again from the original node.")
    return entry[2]


async def request_json(url, key="", body=None, timeout=45):
    headers = {"User-Agent": "RM-LLM/1.0", "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout, connect=20)) as client:
            async with client.request("POST" if body is not None else "GET", url, headers=headers, json=body, allow_redirects=False) as response:
                if response.status != 200:
                    error_body = bytearray()
                    async for chunk in response.content.iter_chunked(4096):
                        error_body.extend(chunk)
                        if len(error_body) >= 16384:
                            break
                    retry_header = response.headers.get("Retry-After")
                    if retry_header is None and response.headers.get("Retry-After-Ms") is not None:
                        try:
                            retry_header = str(float(response.headers["Retry-After-Ms"]) / 1000.0)
                        except ValueError:
                            pass
                    raise provider_error(response.status, error_body[:16384], key, retry_header)
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise RMError("Provider response exceeds 64 MiB.")
                result = json.loads(data)
                if not isinstance(result, dict):
                    raise RMError("Provider returned an unexpected JSON response.")
                if result.get("error"):
                    error = result["error"]
                    code = str(error.get("code", "")) if isinstance(error, dict) else ""
                    status = int(code) if code.isdecimal() and 400 <= int(code) <= 599 else 0
                    raise provider_error(status, data, key, response.headers.get("Retry-After"), http_status=200)
                return result
    except (aiohttp.ClientError, TimeoutError):
        raise RMError("Provider connection failed or timed out. Check connectivity or increase timeout_seconds. No automatic retry was made.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RMError("Provider returned invalid JSON.") from None


def read_records():
    with LOCK:
        return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


async def refresh_records(provider):
    records = read_records()
    if provider == "OpenRouter":
        doc = await request_json("https://openrouter.ai/openapi.json")
        schemas = doc["components"]["schemas"]
        properties = schemas["ChatRequest"]["properties"]
        definitions = {}
        for name, prop in properties.items():
            prop = copy.deepcopy(prop)
            if "$ref" in prop:
                prop = copy.deepcopy(schemas[prop["$ref"].rsplit("/", 1)[-1]])
            definitions[name] = prop
        definitions.setdefault("include_reasoning", {"type": "boolean"})
        records[provider]["parameters"] = definitions
    elif provider == "Featherless":
        # Read the parameter table, not examples or mentions elsewhere on the site.
        url = records[provider]["source"]
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as client:
                async with client.get(url, allow_redirects=False) as response:
                    if response.status != 200:
                        raise RMError("Featherless documentation refresh failed. The previous record is unchanged.")
                    page = await response.text()
        except (aiohttp.ClientError, TimeoutError):
            raise RMError("Featherless documentation could not be reached. The previous record is unchanged.") from None
        params = {}
        for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, flags=re.S):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.S)
            if len(cells) < 3:
                continue
            values = [html.unescape(re.sub(r"<[^>]+>", "", cell)).strip() for cell in cells[:3]]
            name, kind, description = values
            if name in {"model", "messages", "prompt", "stream"} or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                continue
            types = {"float": "number", "integer": "integer", "boolean": "boolean", "object": "object", "array": "array", "string": "string"}
            if kind.lower() in types:
                params[name] = {"type": types[kind.lower()], "description": description}
        if not {"temperature", "max_tokens", "chat_template_kwargs"} <= params.keys():
            raise RMError("Featherless documentation format changed. The previous record is unchanged.")
        records[provider]["parameters"] = params
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers={"User-Agent": "RM-LLM/1.0"}) as client:
                async with client.get(DOC_URL, allow_redirects=False) as response:
                    if response.status != 200:
                        raise RMError("Chat-template documentation refresh failed; previous record retained.")
                    records[provider]["template_options"] = parse_family_records(await response.text())
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise RMError("Chat-template documentation refresh failed; previous record retained.") from None
    else:
        # LithosAI publishes its parameter contract as OpenAPI. Keep the
        # reviewed local record stable; model availability remains live.
        pass
    records[provider]["refreshed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with LOCK:
        # Merge the provider only, so concurrent refreshes cannot overwrite each other.
        current = read_records()
        current[provider] = records[provider]
        temporary = RECORD_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(RECORD_PATH)
        DETAILS.clear()
    return records[provider]


async def fetch_catalog(provider, key=""):
    base, _ = provider_info(provider)
    url = base + ("/models?page=1&per_page=1000" if provider == "Featherless" else "/models")
    models = {}
    seen = set()
    while url:
        parsed, origin = urlsplit(url), urlsplit(base)
        if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc) or not parsed.path.startswith(origin.path + "/models"):
            raise RMError("Provider supplied an invalid pagination URL.")
        if url in seen or len(seen) >= 1000:
            raise RMError("Provider model pagination did not finish.")
        seen.add(url)
        data = await request_json(url, key)
        if not isinstance(data.get("data"), list):
            raise RMError("Provider model catalog has an unexpected format.")
        for model in data["data"]:
            if isinstance(model, dict) and isinstance(model.get("id"), str):
                models[model["id"]] = model
        pagination = data.get("pagination") or {}
        if pagination:
            total_pages = pagination.get("total_pages")
            if not isinstance(total_pages, int) or not 1 <= total_pages <= 1000:
                raise RMError("Provider returned invalid model pagination.")
            # Featherless can return fewer than per_page items after filtering.
            # Only total_pages determines when this catalog is complete.
            for first in range(2, total_pages + 1, 5):
                pages = await asyncio.gather(*(request_json(base + f"/models?page={page}&per_page=1000", key) for page in range(first, min(first + 5, total_pages + 1))))
                for page in pages:
                    if not isinstance(page.get("data"), list):
                        raise RMError("Provider model page has an unexpected format.")
                    for model in page["data"]:
                        if isinstance(model, dict) and isinstance(model.get("id"), str):
                            models[model["id"]] = model
            break
        link = (data.get("links") or {}).get("next")
        url = (origin.scheme + "://" + origin.netloc + link if link and link.startswith("/") else link)
    if not models:
        raise RMError("Provider returned an empty model catalog.")
    return [{"id": m["id"], "name": m.get("name", m["id"]), "available_on_current_plan": m.get("available_on_current_plan")} for m in sorted(models.values(), key=lambda m: m["id"].casefold())]


async def model_capabilities(provider, model, refresh=False, key=""):
    base, _ = provider_info(provider)
    if not isinstance(model, str) or not model or len(model) > 512 or any(ord(c) < 32 for c in model):
        raise RMError("Select a model from the catalog.")
    cache_key = (provider, model)
    with LOCK:
        cached = DETAILS.get(cache_key)
        if cached and not refresh and time.monotonic() - cached[0] < 300:
            return copy.deepcopy(cached[1])
    records = read_records()[provider]
    encoded = quote(model, safe="/")
    if provider == "OpenRouter":
        raw = (await request_json(base + "/models/" + encoded + "/endpoints", key))["data"]
        modalities = raw.get("architecture", {}).get("input_modalities", ["text"])
        endpoints = []
        for endpoint in raw.get("endpoints", []):
            tag = endpoint.get("tag")
            if not tag:
                continue
            params = list(endpoint.get("supported_parameters") or [])
            endpoints.append({"id": tag, "name": endpoint.get("provider_name", tag), "parameters": params, "context_length": endpoint.get("context_length"), "max_tokens": endpoint.get("max_completion_tokens"), "pricing": endpoint.get("pricing"), "status": endpoint.get("status")})
        params = sorted({p for ep in endpoints for p in ep["parameters"]})
        if not endpoints:
            raise RMError("This model has no live chat endpoints. Refresh or select another model.")
        outputs = raw.get("architecture", {}).get("output_modalities", ["text"])
        if "text" not in outputs:
            raise RMError("This model does not produce LLM text through chat completions.")
        source = "Live OpenRouter model endpoints"
    elif provider == "LithosAI":
        raw = await request_json(base + "/models/" + encoded, key)
        raw = raw.get("data", raw)
        params = list(records["parameters"])
        modalities = ["text"]
        endpoints = [{"id": "LithosAI", "name": "LithosAI", "parameters": params,
                      "context_length": raw.get("context_length"),
                      "max_tokens": raw.get("max_completion_tokens"),
                      "pricing": raw.get("pricing")}]
        source = "LithosAI OpenAI-compatible API; model metadata and availability are live"
    else:
        raw = await request_json(base + "/models/" + encoded, key)
        raw = raw.get("data", raw)
        features = raw.get("features") or {}
        modalities = list(raw.get("input_modalities") or ["text"])
        if raw.get("vision_supported") or features.get("image_input"):
            modalities = sorted(set(modalities) | {"image"})
        # Featherless documents image chat, but no native video chat transport.
        modalities = [m for m in modalities if m != "video"]
        params = list(records["parameters"])
        if features.get("tool_use"):
            params += ["tools", "tool_choice"]
        endpoints = [{"id": "Featherless", "name": "Featherless", "parameters": params, "context_length": raw.get("context_length"), "max_tokens": raw.get("max_completion_tokens"), "pricing": raw.get("pricing")}]
        source = "Live Featherless modalities; generation controls from Featherless documentation (not per-model guarantees)"
    definitions = {}
    for name in params:
        if name == "structured_outputs":
            continue  # A capability flag; configuration is the response_format parameter.
        definitions[name] = records["parameters"].get(name, {"description": "Advertised by the endpoint. Enter its value as JSON; provider-specific limits apply."})
    result = {"provider": provider, "model": model, "input_modalities": modalities, "endpoints": endpoints, "parameters": definitions, "source": source, "documentation": records["source"], "record_updated": records["refreshed_at"]}
    if provider == "OpenRouter" and "reasoning" in definitions:
        catalog = await request_json(base + "/models", key)
        metadata = next((item.get("reasoning") for item in catalog.get("data", []) if item.get("id") == model), None)
        if isinstance(metadata, dict):
            result["reasoning_options"] = metadata
    if "chat_template_kwargs" in definitions:
        result["template_parameters"], result["template_note"], result["system_role_rejected"] = await discover_template_options(provider, model, raw, records)
    with LOCK:
        DETAILS[cache_key] = (time.monotonic(), result)
        if len(DETAILS) > 256:
            del DETAILS[next(iter(DETAILS))]
    return copy.deepcopy(result)


def check_local_request(request, secret=False):
    if request.headers.get("X-RM-LLM") != "1":
        raise web.HTTPForbidden(text="RM-LLM request header required.")
    origin = request.headers.get("Origin")
    if origin and origin != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden(text="Cross-origin requests are not allowed.")
    if secret and request.scheme != "https" and request.remote not in {"127.0.0.1", "::1"}:
        raise RMError("Enter keys using localhost or HTTPS. Environment variables are available for other connections.")


async def api_request(request):
    try:
        check_local_request(request, secret=request.match_info["action"] in {"key", "ticket"})
        if request.content_length and request.content_length > 16384:
            raise RMError("Request is too large.")
        data = await request.json()
        provider = data.get("provider", "OpenRouter")
        provider_info(provider)
        action = request.match_info["action"]
        if action == "key":
            if data.get("clear"):
                with LOCK:
                    SESSIONS.pop(data.get("session", ""), None)
                result = {"cleared": True}
            else:
                result = {"session": store_session(provider, data.get("key")), "expires_in": SESSION_TTL}
        elif action == "set_env":
            name = set_process_environment_key(provider, data.get("env_name", ""), data.get("key"))
            result = {"environment_variable": name}
        elif action == "ticket":
            result = {"ticket": issue_ticket(provider, data.get("session", ""))}
        elif action == "models":
            key = session_key(provider, data["session"]) if data.get("session") else environment_key(provider, data.get("env_name", ""))
            result = {"models": await fetch_catalog(provider, key)}
        elif action == "capabilities":
            key = session_key(provider, data["session"]) if data.get("session") else environment_key(provider, data.get("env_name", ""), required=True)
            result = await model_capabilities(provider, data.get("model", ""), refresh=True, key=key)
        elif action == "refresh":
            result = await refresh_records(provider)
        else:
            raise web.HTTPNotFound()
        return web.json_response(result, headers={"Cache-Control": "no-store"})
    except (RMError, json.JSONDecodeError) as error:
        return web.json_response({"error": str(error)}, status=400, headers={"Cache-Control": "no-store"})


def register_routes():
    PromptServer.instance.routes.post("/rm_llm/{action}")(api_request)
