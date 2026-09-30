"""RM-LLM v3: the v2 node with the LithosAI provider enabled in its UI."""

from .node_v2 import RMLLMV2


class RMLLMV3(RMLLMV2):
    """Keep v2's execution contract while exposing the v3 provider set."""

    DESCRIPTION = (
        "OpenRouter, Featherless, and LithosAI LLM calls with live model discovery, "
        "dynamic controls, optional media input, and server-side credentials."
    )
