from .node_v2 import RMLLMV2
from .node_v3 import RMLLMV3
from .agent import AgentProfile, AgentRequest
from .service import register_routes

register_routes()
NODE_CLASS_MAPPINGS = {"RM_LLM_V2": RMLLMV2, "RM_LLM_V3": RMLLMV3, "RMLLMAgentProfile": AgentProfile, "RMLLMAgentRequest": AgentRequest}
NODE_DISPLAY_NAME_MAPPINGS = {"RM_LLM_V2": "RM-LLM v2 (legacy)", "RM_LLM_V3": "RM-LLM 0.3.0", "RMLLMAgentProfile": "Agent Model Profile", "RMLLMAgentRequest": "Agent Request"}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
