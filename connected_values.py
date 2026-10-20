"""Display only wired scalar controls; never transport credential or media inputs."""
import math

EXCLUDED = {"key_ticket", "api_key", "api_key_env", "image", "video", "agent_request"}

def connected_values(inputs, values):
    result = {}
    for name, source in inputs.items():
        if name in EXCLUDED or not isinstance(source, list) or len(source) != 2:
            continue
        value = values.get(name)
        if type(value) not in (str, bool, int, float) or isinstance(value, float) and not math.isfinite(value):
            continue
        result[name] = {"value": value, "source": source}
    return result
