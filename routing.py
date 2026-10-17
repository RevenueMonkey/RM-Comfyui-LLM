"""Route resolution and endpoint-specific capabilities; no network or credentials."""
import copy

from .service import RMError, provider_info


def resolve_route(router, provider, hosting_provider="Auto", endpoint="Auto"):
    # Empty router is the legacy contract: provider names identify the API service.
    if not router:
        return provider, hosting_provider if provider == "OpenRouter" and hosting_provider != "Auto" else endpoint
    if router == "OpenRouter":
        return "OpenRouter", hosting_provider or "Auto"
    if router != "Direct":
        raise RMError("Select Direct or OpenRouter for router.")
    if provider == "OpenRouter":
        raise RMError("Select a direct provider, or set router to OpenRouter.")
    provider_info(provider)
    return provider, "Auto"


def endpoint_capabilities(caps, endpoint):
    if caps.get("provider") != "OpenRouter" or endpoint == "Auto":
        return caps
    # A base provider slug includes its eligible endpoint variants.
    matches = [ep for ep in caps.get("endpoints", [])
               if ep["id"] == endpoint or ep["id"].startswith(endpoint + "/")]
    if not matches:
        raise RMError("The selected hosting provider does not serve this model. Select another provider or model.")
    result = copy.deepcopy(caps)
    supported = set.intersection(*(set(ep["parameters"]) for ep in matches))
    result["parameters"] = {k: v for k, v in result["parameters"].items() if k in supported}
    selected = dict(matches[0], id=endpoint, parameters=sorted(supported))
    for field in ("context_length", "max_tokens"):
        limits = [ep[field] for ep in matches if type(ep.get(field)) is int and ep[field] > 0]
        selected[field] = min(limits) if limits else None
    result["endpoints"] = [selected]
    return result
