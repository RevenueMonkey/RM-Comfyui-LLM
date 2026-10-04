from .node import RMLLM050
from .agent import AgentProfile, AgentRequest
from .service import register_routes

register_routes()
NODE_CLASS_MAPPINGS = {"RM_LLM_050": RMLLM050, "RMLLMAgentProfile050": AgentProfile, "RMLLMAgentRequest050": AgentRequest}
NODE_DISPLAY_NAME_MAPPINGS = {"RM_LLM_050": "RM-LLM 0.5.0", "RMLLMAgentProfile050": "Agent Model Profile 0.5.0", "RMLLMAgentRequest050": "Agent Request 0.5.0"}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
