from .node import RMLLM040
from .agent import AgentProfile, AgentRequest
from .service import register_routes

register_routes()
NODE_CLASS_MAPPINGS = {"RM_LLM_040": RMLLM040, "RMLLMAgentProfile040": AgentProfile, "RMLLMAgentRequest040": AgentRequest}
NODE_DISPLAY_NAME_MAPPINGS = {"RM_LLM_040": "RM-LLM 0.4.0", "RMLLMAgentProfile040": "Agent Model Profile 0.4.0", "RMLLMAgentRequest040": "Agent Request 0.4.0"}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
