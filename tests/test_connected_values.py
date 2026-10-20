import unittest
from test_providers import n
from rm_test.connected_values import connected_values

class ConnectedValues(unittest.TestCase):
    def test_only_wired_scalars_and_no_credentials(self):
        names = ["temperature", "console_output", "system_prompt", "key_ticket", "api_key_env", "image", "agent_request", "tools"]
        inputs = {name: ["12", 0] for name in names}
        inputs["user_prompt"] = "manual"
        values = dict(temperature=0.7, console_output=False, system_prompt="received", key_ticket="secret", api_key_env="KEY", image=object(), agent_request={}, tools={}, user_prompt="manual")
        self.assertEqual(connected_values(inputs, values), {
            "temperature": {"value": .7, "source": ["12", 0]},
            "console_output": {"value": False, "source": ["12", 0]},
            "system_prompt": {"value": "received", "source": ["12", 0]}})

    def test_finite_and_empty_values(self):
        self.assertEqual(connected_values({"temperature": [1,0]}, {"temperature": float("nan")}), {})
        self.assertEqual(connected_values({"user_prompt": [1,0]}, {"user_prompt": ""})["user_prompt"]["value"], "")

class ReceivedEvent(unittest.IsolatedAsyncioTestCase):
    async def test_execution_reports_received_values_without_changing_request(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock, patch
        prompt = Mock()
        prompt.get_node.return_value = {"inputs": {"user_prompt": ["2", 0], "console_output": ["3", 0], "key_ticket": ["4", 0]}}
        prompt.get_display_node_id.return_value = "13"
        server = SimpleNamespace(send_sync=Mock(), client_id="test-client")
        args = dict(provider="Featherless", model_name="example", endpoint="Auto", api_key_env="FEATHERLESS_API_KEY", credential_source="Environment variable", system_prompt="manual", user_prompt="from upstream", timeout_seconds=30, console_output=True, key_ticket="secret-ticket")
        with patch.object(n, "get_executing_context", return_value=SimpleNamespace(node_id="13")), patch.object(n.PromptServer, "instance", server, create=True), patch.object(n.ChatCompletionNode, "generate", AsyncMock(return_value={"ui": {}, "result": ("answer", "", "{}")})) as run:
            result = await n.RMLLM050().generate(parameters_json="{}", dynprompt=prompt, **args)
        packet = server.send_sync.call_args.args[1]["input_values"]
        self.assertEqual(packet["user_prompt"]["value"], "from upstream")
        self.assertIs(packet["console_output"]["value"], True)
        self.assertNotIn("key_ticket", packet)
        self.assertEqual(result["ui"]["rm_llm_inputs"], [packet])
        self.assertEqual(run.call_args.kwargs["user_prompt"], "from upstream")
