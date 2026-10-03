"""Provider metadata, persistent user environment keys and temporary sessions."""
import asyncio
import copy
import html
import json
import logging
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
try:
    import folder_paths
except ImportError:  # pragma: no cover - allows lightweight offline imports
    folder_paths = None
from .template_options import DOC_URL, discover_template_options, parse_family_records
from .environment_store import read_persistent_environment, write_persistent_environment

ROOT = Path(__file__).resolve().parent
PROVIDERS = {
    "OpenRouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "Featherless": ("https://api.featherless.ai/v1", "FEATHERLESS_API_KEY"),
    "LithosAI": ("https://api.lithosai.cloud/v1", "LITHOSAI_API_KEY"),
}
RECORD_PATH = ROOT / "capability_records.json"
LOCK = threading.RLock()
DETAILS = {}
CATALOG_CACHE = {}
CATALOG_STATUS = {}
CATALOG_COOLDOWNS = {}
CATALOG_TASKS = {}
CATALOG_PROGRESS = {}
FEATHERLESS_PAGE_INTERVAL = 2.0
SESSIONS = {}
TICKETS = {}
SESSION_TTL = 12 * 3600
TICKET_TTL = 24 * 3600
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
CATALOG_TTL = 300
MISSING_API_KEY_ERROR = "API Key Needed!"


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
    if not key:
        try:
            key = read_persistent_environment(name).strip()
        except (OSError, ValueError):
            raise RMError("Could not read the saved API-key environment. Check user permissions or set the key again.") from None
    if key and (len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key)):
        raise RMError("The API-key environment variable contains an invalid credential value.")
    if required and not key:
        raise RMError(MISSING_API_KEY_ERROR)
    if key:
        os.environ[name] = key
    return key


def set_environment_key(provider, name, key):
    """Persist a user environment key and apply it to this ComfyUI process."""
    provider_info(provider)
    name = name.strip() or provider_info(provider)[1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
        raise RMError("Enter an environment variable name, not an API key.")
    if not isinstance(key, str) or not 1 <= len(key.strip()) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key.strip()):
        raise RMError("API key must be nonempty text without spaces or control characters.")
    with LOCK:
        try:
            write_persistent_environment(name, key.strip())
        except (OSError, ValueError):
            raise RMError("Could not save the API-key environment. Check user permissions; the key was not set.") from None
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
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise RMError("Provider connection failed or timed out. Check connectivity or increase timeout_seconds. No automatic retry was made.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RMError("Provider returned invalid JSON.") from None


def read_records():
    with LOCK:
        return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def catalog_cache_path():
    """Keep model catalogs in ComfyUI user data, never in the node package."""
    getter = getattr(folder_paths, "get_user_directory", None)
    user_dir = getter() if getter else ROOT
    path = Path(user_dir) / "RM-LLM-0.4.0" / "catalog_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_catalog_cache(provider):
    path = catalog_cache_path()
    # Reuse public catalogs from the previous installation without altering it.
    for candidate in (path, path.parent.parent / "RM-LLM" / path.name):
        try:
            document = json.loads(candidate.read_text(encoding="utf-8"))
            models = document.get(provider) if isinstance(document, dict) else None
            if isinstance(models, list) and all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in models):
                return models
        except (OSError, ValueError, TypeError):
            pass
    return None


def write_catalog_cache(provider, models):
    try:
        with LOCK:
            path = catalog_cache_path()
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                document = {}
            if not isinstance(document, dict):
                document = {}
            document[provider] = models
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
    except OSError:
        logging.warning("[RM-LLM] Could not save the local model catalog cache.")


def featherless_modalities(raw):
    """Normalize Featherless/Hugging Face vision metadata across schema variants."""
    def values(field):
        value = raw.get(field) or []
        return [value] if isinstance(value, str) else value if isinstance(value, list) else []

    modalities = values("input_modalities") or values("modalities") or ["text"]
    modalities = ["image" if value.casefold() == "vision" else value.casefold() for value in modalities if isinstance(value, str)]
    features = raw.get("features") or {}
    capabilities = values("capabilities")
    tasks = values("tasks")
    tags = values("tags")
    tokens = {str(value).casefold().replace("_", "-") for value in [*capabilities, *tasks, *tags]}
    vision_tokens = {"vision", "vision-language", "vision-language-model", "image-input", "image-text-to-text", "image-to-text", "visual-question-answering"}
    if (
        raw.get("vision_supported") is True
        or features.get("image_input") is True
        or bool(tokens & vision_tokens)
    ):
        modalities.append("image")
    return sorted({str(value).casefold() for value in modalities if value})


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
        except (aiohttp.ClientError, asyncio.TimeoutError):
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
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
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
        CATALOG_CACHE.pop(provider, None)
    return records[provider]


async def catalog_request(provider, url, key):
    if provider == "Featherless":
        # The public catalog does not need account authentication. Omit it for
        # every page, including callers that already resolved an API key.
        key = ""
        with LOCK:
            remaining = CATALOG_COOLDOWNS.get(provider, 0) - time.monotonic()
        if remaining > 0:
            raise ProviderHTTPError(429, "Featherless catalog is cooling down. Try later.", remaining)
    try:
        return await request_json(url, key)
    except ProviderHTTPError as error:
        if provider == "Featherless" and error.status == 429:
            # Return promptly to the UI instead of keeping 'Fetching' displayed
            # throughout a ten-minute sleep. Refresh cannot bypass the cooldown.
            delay = max(600.0, error.retry_after or 0.0)
            with LOCK:
                CATALOG_COOLDOWNS[provider] = time.monotonic() + delay
            logging.warning("[RM-LLM] Featherless catalog is rate-limited; try again after %.1f seconds.", delay)
            raise ProviderHTTPError(429, "Featherless catalog is rate-limited. Try later.", delay) from None
        raise


async def fetch_catalog(provider, key="", force=False):
    # Multiple nodes/pickers share one download. Closing a browser request must
    # not cancel the download another picker is still using.
    with LOCK:
        task = CATALOG_TASKS.get(provider)
        if task is None or task.done():
            task = asyncio.create_task(_catalog_result(provider, key, force))
            CATALOG_TASKS[provider] = task
            def finished(done):
                with LOCK:
                    if CATALOG_TASKS.get(provider) is done:
                        CATALOG_TASKS.pop(provider, None)
                if not done.cancelled():
                    done.exception()
            task.add_done_callback(finished)
    return copy.deepcopy(await asyncio.shield(task))


async def _catalog_result(provider, key, force):
    try:
        return await _fetch_catalog(provider, key, force)
    except RMError:
        progress = catalog_progress(provider)
        if progress.get("state") == "loading":
            set_catalog_progress(provider, state="failed")
        local = read_catalog_cache(provider)
        if local:
            with LOCK:
                CATALOG_CACHE[provider] = (time.monotonic(), local)
                CATALOG_STATUS[provider] = {"source": "local cache", "warning": "Try later. Showing the last successful catalog."}
            return copy.deepcopy(local)
        if provider == "Featherless":
            partial = read_catalog_checkpoint()
            if partial and partial["models"]:
                with LOCK:
                    CATALOG_STATUS[provider] = {"source": "partial catalog", "warning": "Try later. Showing retained models; catalog is incomplete."}
                return sorted(partial["models"], key=lambda model: model["id"].casefold())
        raise


def set_catalog_progress(provider, **fields):
    with LOCK:
        CATALOG_PROGRESS.setdefault(provider, {}).update(fields)


def catalog_progress(provider):
    with LOCK:
        progress = copy.deepcopy(CATALOG_PROGRESS.get(provider, {}))
    if not progress and provider == "Featherless":
        checkpoint = read_catalog_checkpoint()
        if checkpoint:
            progress = {"state": "paused", "count": len(checkpoint["models"]),
                        "page": checkpoint["next_page"], "total_pages": checkpoint["total_pages"],
                        "total": checkpoint["total_items"], "retry_at": checkpoint["retry_at"]}
    if not progress:
        with LOCK:
            cached = CATALOG_CACHE.get(provider)
        models = cached[1] if cached else read_catalog_cache(provider)
        if models is not None:
            progress = {"state": "cached", "count": len(models), "total": len(models), "retry_at": 0}
            set_catalog_progress(provider, **progress)
    progress["retry_seconds"] = max(0, int(progress.get("retry_at", 0) - time.time() + 0.999))
    return progress


def read_catalog_checkpoint():
    """Incomplete public metadata is separate from the last complete catalog."""
    try:
        path = catalog_cache_path().with_name("featherless_catalog_progress.json")
        if not path.exists() and not catalog_cache_path().exists():
            path = path.parent.parent / "RM-LLM" / path.name
        if path.stat().st_size > MAX_RESPONSE_BYTES:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("version") != 1:
            return None
        page, pages = document.get("next_page"), document.get("total_pages")
        models = document.get("models")
        if (not isinstance(page, int) or not isinstance(pages, int)
                or not 1 <= page <= max(1, pages) or not 0 <= pages <= 1000
                or not isinstance(models, list)
                or not all(isinstance(model, dict) and isinstance(model.get("id"), str) for model in models)
                or not all(isinstance(document.get(name), (int, float))
                           and 0 <= document[name] < float("inf") for name in ("retry_at", "last_request_at", "total_items"))):
            return None
        return document
    except (OSError, ValueError, TypeError):
        return None


def save_catalog_checkpoint(checkpoint):
    try:
        with LOCK:
            path = catalog_cache_path().with_name("featherless_catalog_progress.json")
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
    except OSError:
        logging.warning("[RM-LLM] Could not save Featherless catalog progress.")


def compact_catalog_model(model):
    return {"id": model["id"], "name": model.get("name", model["id"]),
            "available_on_current_plan": model.get("available_on_current_plan")}


async def fetch_featherless_catalog(base):
    provider = "Featherless"
    checkpoint = read_catalog_checkpoint() or {
        "version": 1, "models": [], "next_page": 1, "total_pages": 0,
        "total_items": 0, "retry_at": 0, "last_request_at": 0,
    }
    models = {model["id"]: compact_catalog_model(model) for model in checkpoint["models"]}
    set_catalog_progress(provider, state="loading", count=len(models), page=checkpoint["next_page"],
                         total_pages=checkpoint["total_pages"], total=checkpoint["total_items"], retry_at=0, reason="")
    remaining = checkpoint["retry_at"] - time.time()
    if remaining > 0:
        with LOCK:
            CATALOG_COOLDOWNS[provider] = max(CATALOG_COOLDOWNS.get(provider, 0), time.monotonic() + remaining)
        set_catalog_progress(provider, state="paused", retry_at=checkpoint["retry_at"])
        raise ProviderHTTPError(429, "Featherless catalog is cooling down. Try later.", remaining)
    while True:
        page_number = checkpoint["next_page"]
        set_catalog_progress(provider, state="loading", page=page_number)
        try:
            # Space request starts, including the first request after restart.
            delay = FEATHERLESS_PAGE_INTERVAL - (time.time() - checkpoint["last_request_at"])
            if delay > 0:
                await asyncio.sleep(min(delay, FEATHERLESS_PAGE_INTERVAL))
            checkpoint["last_request_at"] = time.time()
            data = await catalog_request(provider, base + f"/models?page={page_number}&per_page=1000", "")
            if not isinstance(data.get("data"), list):
                raise RMError("Provider model page has an unexpected format.")
            pagination = data.get("pagination") or {}
            if not isinstance(pagination, dict):
                raise RMError("Provider returned invalid model pagination.")
            pages = pagination.get("total_pages", 1)
            total = pagination.get("total_items", 0)
            if (not isinstance(pages, int) or not 1 <= pages <= 1000
                    or not isinstance(total, int) or total < 0
                    or pagination.get("current_page", page_number) != page_number):
                raise RMError("Provider returned invalid model pagination.")
            if page_number > 1 and (pages != checkpoint["total_pages"] or total != checkpoint["total_items"]):
                # There is no catalog snapshot API. Restart on a changed page
                # count/total instead of presenting mixed pages as complete.
                models.clear()
                checkpoint.update(models=[], next_page=1, total_pages=0, total_items=0, retry_at=0)
                save_catalog_checkpoint(checkpoint)
                set_catalog_progress(provider, state="failed", count=0, page=1, total_pages=0, total=0, reason="Catalog changed; try again.")
                raise RMError("Featherless catalog changed during retrieval. Try again to download the updated list.")
            checkpoint.update(total_pages=pages, total_items=total)
            for model in data["data"]:
                if isinstance(model, dict) and isinstance(model.get("id"), str):
                    models[model["id"]] = compact_catalog_model(model)
            set_catalog_progress(provider, count=len(models), total=total, total_pages=pages, reason="")
            checkpoint.update(models=list(models.values()), retry_at=0)
            if page_number >= pages:
                if not models:
                    raise RMError("Provider returned an empty model catalog.")
                break
            checkpoint["next_page"] = page_number + 1
            save_catalog_checkpoint(checkpoint)
        except RMError as error:
            retry_at = time.time() + error.retry_after if isinstance(error, ProviderHTTPError) and error.status == 429 and error.retry_after else 0
            checkpoint["retry_at"] = retry_at
            save_catalog_checkpoint(checkpoint)
            if catalog_progress(provider).get("state") != "failed":
                set_catalog_progress(provider, state="paused" if retry_at else "failed", retry_at=retry_at)
            logging.warning("[RM-LLM] Featherless catalog stopped at page %s/%s; %s models retained (%s).",
                            page_number, checkpoint["total_pages"] or "?", len(models),
                            f"HTTP {error.status}" if isinstance(error, ProviderHTTPError) else "retrieval failed")
            raise
    return sorted(models.values(), key=lambda model: model["id"].casefold())


async def _fetch_catalog(provider, key="", force=False):
    resuming = provider == "Featherless" and read_catalog_checkpoint() is not None
    with LOCK:
        cached = CATALOG_CACHE.get(provider)
        if cached and not force and not resuming and time.monotonic() - cached[0] < CATALOG_TTL:
            CATALOG_STATUS[provider] = {"source": "memory cache", "warning": ""}
            set_catalog_progress(provider, state="cached", count=len(cached[1]), total=len(cached[1]), retry_at=0)
            return copy.deepcopy(cached[1])
    if not force and not resuming:
        local = read_catalog_cache(provider)
        if local:
            with LOCK:
                CATALOG_CACHE[provider] = (time.monotonic(), local)
                CATALOG_STATUS[provider] = {"source": "local cache", "warning": "Live catalog is checked only with Refresh."}
                set_catalog_progress(provider, state="cached", count=len(local), total=len(local), retry_at=0)
            return copy.deepcopy(local)
    base, _ = provider_info(provider)
    if provider == "Featherless":
        catalog = await fetch_featherless_catalog(base)
        with LOCK:
            CATALOG_CACHE[provider] = (time.monotonic(), catalog)
            CATALOG_STATUS[provider] = {"source": "live catalog", "warning": ""}
        write_catalog_cache(provider, catalog)
        try:
            catalog_cache_path().with_name("featherless_catalog_progress.json").unlink(missing_ok=True)
        except OSError:
            logging.warning("[RM-LLM] Could not clear completed Featherless catalog progress.")
        set_catalog_progress(provider, state="ready", count=len(catalog), retry_at=0)
        return copy.deepcopy(catalog)
    set_catalog_progress(provider, state="loading", count=0, page=1, total_pages=0, total=0, retry_at=0)
    url = base + "/models"
    models = {}
    seen = set()
    while url:
        parsed, origin = urlsplit(url), urlsplit(base)
        if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc) or not parsed.path.startswith(origin.path + "/models"):
            raise RMError("Provider supplied an invalid pagination URL.")
        if url in seen or len(seen) >= 1000:
            raise RMError("Provider model pagination did not finish.")
        seen.add(url)
        data = await catalog_request(provider, url, key)
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
            # Follow advertised pages sequentially.
            for page_number in range(2, total_pages + 1):
                page = await catalog_request(provider, base + f"/models?page={page_number}&per_page=1000", key)
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
    catalog = [{"id": m["id"], "name": m.get("name", m["id"]), "available_on_current_plan": m.get("available_on_current_plan")} for m in sorted(models.values(), key=lambda m: m["id"].casefold())]
    with LOCK:
        CATALOG_CACHE[provider] = (time.monotonic(), catalog)
        CATALOG_STATUS[provider] = {"source": "live catalog", "warning": ""}
    write_catalog_cache(provider, catalog)
    set_catalog_progress(provider, state="ready", count=len(catalog), total=len(catalog), retry_at=0)
    return copy.deepcopy(catalog)


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
        modalities = featherless_modalities(raw)
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
        check_local_request(request, secret=request.match_info["action"] in {"key", "ticket", "set_env"})
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
            name = set_environment_key(provider, data.get("env_name", ""), data.get("key"))
            result = {"environment_variable": name, "key_present": True, "persistent": True}
        elif action == "credential_status":
            source = data.get("credential_source") or ("Masked session key" if data.get("session") else "Environment variable")
            if source == "Masked session key":
                try:
                    session_key(provider, data.get("session", ""))
                except RMError:
                    result = {"key_present": False}
                else:
                    result = {"key_present": True}
            elif source == "Environment variable":
                result = {"key_present": bool(environment_key(provider, data.get("env_name", "")))}
            else:
                raise RMError("Select Environment variable or Masked session key.")
        elif action == "ticket":
            result = {"ticket": issue_ticket(provider, data.get("session", ""))}
        elif action == "models":
            if provider == "Featherless":
                key = ""
            else:
                key = session_key(provider, data["session"]) if data.get("session") else environment_key(provider, data.get("env_name", ""))
            result = {"models": await fetch_catalog(provider, key, force=bool(data.get("force")))}
            result.update(CATALOG_STATUS.get(provider, {}))
            result["progress"] = catalog_progress(provider)
        elif action == "catalog_status":
            # Browser polling reads local progress only; no provider request.
            result = {"progress": catalog_progress(provider)}
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
    PromptServer.instance.routes.post("/rm_llm_040/{action}")(api_request)
