#!/usr/bin/env python3
"""
Tests for migrate-workflows-to-payi.py

Run:  python3 -m pytest test_migrate_workflows.py -v
  or: python3 test_migrate_workflows.py
"""

import copy
import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# ── Import the migration script as a module ──────────────────────────────────

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "migrate-workflows-to-payi.py")
spec = importlib.util.spec_from_file_location("migrate", SCRIPT_PATH)
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)

# ── Test Fixtures ────────────────────────────────────────────────────────────

PAYI_CRED = {"id": "cred-123", "name": "Pay-i API"}

OPENAI_CHAT_MODEL_NODE = {
    "id": "node-aaa",
    "name": "OpenAI Chat Model",
    "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
    "typeVersion": 1,
    "position": [400, 300],
    "parameters": {
        "model": "gpt-4.1-mini",
        "options": {
            "temperature": 0.5,
            "maxTokens": 2048,
            "topP": 0.9,
        },
    },
    "credentials": {
        "openAiApi": {"id": "old-cred", "name": "OpenAI"},
    },
}

OPENAI_APP_NODE = {
    "id": "node-bbb",
    "name": "OpenAI",
    "type": "@n8n/n8n-nodes-langchain.openai",
    "typeVersion": 1,
    "position": [600, 200],
    "parameters": {
        "model": "gpt-4o",
        "messages": '[{"role": "user", "content": "Summarize this"}]',
    },
    "credentials": {
        "openAiApi": {"id": "old-cred", "name": "OpenAI"},
    },
}

ANTHROPIC_CHAT_MODEL_NODE = {
    "id": "node-ccc",
    "name": "Anthropic Chat Model",
    "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "typeVersion": 1,
    "position": [400, 500],
    "parameters": {"model": "claude-sonnet-4-20250514"},
}

ANTHROPIC_CHAT_MODEL_NODE_V12 = {
    "id": "node-ccc",
    "name": "Anthropic Chat Model",
    "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "typeVersion": 1.2,
    "position": [400, 500],
    "parameters": {
        "options": {
            "maxTokensToSample": 8192,
            "temperature": 0.7,
        },
    },
    "credentials": {
        "anthropicApi": {
            "id": "cred-anthropic",
            "name": "Anthropic Account",
        },
    },
}

TRIGGER_NODE = {
    "id": "node-trigger",
    "name": "Manual Trigger",
    "type": "n8n-nodes-base.manualTrigger",
    "typeVersion": 1,
    "position": [200, 300],
    "parameters": {},
}

AGENT_NODE = {
    "id": "node-agent",
    "name": "AI Agent",
    "type": "@n8n/n8n-nodes-langchain.agent",
    "typeVersion": 1,
    "position": [600, 300],
    "parameters": {
        "text": "={{ $('OpenAI Chat Model').item.json.output }}",
        "other": "no refs here",
    },
}


def make_workflow(wf_id="wf-1", name="Test Workflow", nodes=None, connections=None):
    return {
        "id": wf_id,
        "name": name,
        "nodes": nodes or [],
        "connections": connections or {},
        "settings": {},
        "staticData": None,
        "pinData": {},
        # Read-only fields that GET returns
        "active": False,
        "createdAt": "2025-01-01T00:00:00.000Z",
        "updatedAt": "2025-01-01T00:00:00.000Z",
        "versionId": "v1",
        "tags": [],
    }


# ── Tests: find_llm_nodes ───────────────────────────────────────────────────

class TestFindLlmNodes(unittest.TestCase):
    def test_finds_openai_chat_model(self):
        wf = make_workflow(nodes=[TRIGGER_NODE, OPENAI_CHAT_MODEL_NODE])
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["provider"], "openai")
        self.assertEqual(found[0]["replacement"], "chat_model")
        self.assertTrue(found[0]["feasible"])

    def test_finds_openai_app_node(self):
        wf = make_workflow(nodes=[TRIGGER_NODE, OPENAI_APP_NODE])
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["replacement"], "proxy")
        self.assertTrue(found[0]["feasible"])

    def test_finds_anthropic_as_feasible(self):
        wf = make_workflow(nodes=[ANTHROPIC_CHAT_MODEL_NODE])
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["feasible"])
        self.assertEqual(found[0]["replacement"], "chat_model_anthropic")

    def test_ignores_non_llm_nodes(self):
        wf = make_workflow(nodes=[TRIGGER_NODE])
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 0)

    def test_multiple_workflows(self):
        wf1 = make_workflow("wf-1", "Bot A", [OPENAI_CHAT_MODEL_NODE])
        wf2 = make_workflow("wf-2", "Bot B", [OPENAI_APP_NODE, ANTHROPIC_CHAT_MODEL_NODE])
        found = migrate.find_llm_nodes([wf1, wf2])
        self.assertEqual(len(found), 3)
        feasible = [n for n in found if n["feasible"]]
        infeasible = [n for n in found if not n["feasible"]]
        self.assertEqual(len(feasible), 3)
        self.assertEqual(len(infeasible), 0)

    def test_preserves_workflow_metadata(self):
        wf = make_workflow("wf-42", "My Workflow", [OPENAI_CHAT_MODEL_NODE])
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(found[0]["workflow_id"], "wf-42")
        self.assertEqual(found[0]["workflow_name"], "My Workflow")

    def test_empty_workflows(self):
        found = migrate.find_llm_nodes([])
        self.assertEqual(len(found), 0)

    def test_workflow_with_no_nodes(self):
        wf = make_workflow(nodes=[])
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 0)

    def test_detects_all_infeasible_types(self):
        nodes = [
            {"name": "Gemini", "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini", "parameters": {}},
            {"name": "Mistral", "type": "@n8n/n8n-nodes-langchain.lmChatMistralCloud", "parameters": {}},
        ]
        wf = make_workflow(nodes=nodes)
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 2)
        self.assertTrue(all(not n["feasible"] for n in found))

    def test_azure_and_bedrock_are_feasible(self):
        nodes = [
            {"name": "Azure", "type": "@n8n/n8n-nodes-langchain.lmChatAzureOpenAi", "parameters": {}},
            {"name": "Bedrock", "type": "@n8n/n8n-nodes-langchain.lmChatAwsBedrock", "parameters": {}},
        ]
        wf = make_workflow(nodes=nodes)
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 2)
        self.assertTrue(all(n["feasible"] for n in found))
        self.assertEqual(found[0]["replacement"], "chat_model_azure")
        self.assertEqual(found[1]["replacement"], "chat_model_bedrock")


# ── Tests: build_payi_chat_model_node ────────────────────────────────────────

class TestBuildPayiChatModelNode(unittest.TestCase):
    def test_basic_fields(self):
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, PAYI_CRED, "sk-test-key", "Pay-i Chat Model"
        )
        self.assertEqual(result["type"], "n8n-nodes-payi.lmChatPayi")
        self.assertEqual(result["name"], "Pay-i Chat Model")
        self.assertEqual(result["id"], "node-aaa")
        self.assertEqual(result["position"], [400, 300])
        self.assertEqual(result["typeVersion"], 1)

    def test_model_mapped(self):
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, PAYI_CRED, "sk-test", "Pay-i Chat Model"
        )
        self.assertEqual(result["parameters"]["model"], "gpt-4.1-mini")

    def test_options_preserved(self):
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, PAYI_CRED, "sk-test", "Pay-i Chat Model"
        )
        opts = result["parameters"]["options"]
        self.assertEqual(opts["temperature"], 0.5)
        self.assertEqual(opts["maxTokens"], 2048)
        self.assertEqual(opts["topP"], 0.9)

    def test_unsupported_options_excluded(self):
        node = copy.deepcopy(OPENAI_CHAT_MODEL_NODE)
        node["parameters"]["options"]["unknownOption"] = "foo"
        result = migrate.build_payi_chat_model_node(node, PAYI_CRED, "sk-test", "Pay-i Chat Model")
        self.assertNotIn("unknownOption", result["parameters"]["options"])

    def test_no_plaintext_provider_key(self):
        """providerApiKey should NOT be in parameters — credentials are passed through."""
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, PAYI_CRED, "sk-my-key", "Pay-i Chat Model"
        )
        self.assertNotIn("providerApiKey", result["parameters"])

    def test_native_credential_passthrough(self):
        """The original node's openAiApi credential should be passed to the Pay-i node."""
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, PAYI_CRED, "sk-test", "Pay-i Chat Model"
        )
        self.assertIn("openAiApi", result["credentials"])
        self.assertEqual(result["credentials"]["openAiApi"]["id"], "old-cred")
        self.assertEqual(result["credentials"]["openAiApi"]["name"], "OpenAI")

    def test_credentials_reference(self):
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, PAYI_CRED, "sk-test", "Pay-i Chat Model"
        )
        cred_ref = result["credentials"]["payiApi"]
        self.assertEqual(cred_ref["id"], "cred-123")
        self.assertEqual(cred_ref["name"], "Pay-i API")

    def test_tracking_defaults(self):
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, PAYI_CRED, "sk-test", "Pay-i Chat Model"
        )
        params = result["parameters"]
        self.assertEqual(params["useCaseName"], "={{ $workflow.name.replaceAll(' ', '-') }}")
        self.assertEqual(params["useCaseId"], "={{ 'openai/' + $parameter.model + '/' + $execution.id }}")
        self.assertEqual(params["useCaseStep"], "={{ $node.name }}")

    def test_default_model_when_missing(self):
        node = {"id": "x", "parameters": {}, "position": [0, 0]}
        result = migrate.build_payi_chat_model_node(node, PAYI_CRED, "sk-test", "Pay-i Chat Model")
        self.assertEqual(result["parameters"]["model"], "gpt-4o")

    def test_empty_options_when_none_in_source(self):
        node = {"id": "x", "parameters": {"model": "gpt-4o"}, "position": [0, 0]}
        result = migrate.build_payi_chat_model_node(node, PAYI_CRED, "sk-test", "Pay-i Chat Model")
        self.assertEqual(result["parameters"]["options"], {})

    def test_credential_id_stringified(self):
        cred = {"id": 42, "name": "Pay-i API"}
        result = migrate.build_payi_chat_model_node(
            OPENAI_CHAT_MODEL_NODE, cred, "sk-test", "Pay-i Chat Model"
        )
        self.assertEqual(result["credentials"]["payiApi"]["id"], "42")

    def test_model_from_resource_locator_object(self):
        """n8n 2.x stores model as resourceLocator: {mode, value}."""
        node = {
            "id": "x",
            "parameters": {
                "model": {"mode": "list", "value": "gpt-4.1-mini"},
                "options": {},
            },
            "position": [0, 0],
        }
        result = migrate.build_payi_chat_model_node(node, PAYI_CRED, "sk-test", "Pay-i Chat Model")
        self.assertEqual(result["parameters"]["model"], "gpt-4.1-mini")


# ── Tests: build_payi_proxy_node ─────────────────────────────────────────────

class TestBuildPayiProxyNode(unittest.TestCase):
    def test_basic_fields(self):
        result = migrate.build_payi_proxy_node(
            OPENAI_APP_NODE, PAYI_CRED, "sk-test", "Pay-i Proxy"
        )
        self.assertEqual(result["type"], "n8n-nodes-payi.payi")
        self.assertEqual(result["name"], "Pay-i Proxy")
        self.assertEqual(result["id"], "node-bbb")
        self.assertEqual(result["position"], [600, 200])

    def test_model_mapped(self):
        result = migrate.build_payi_proxy_node(
            OPENAI_APP_NODE, PAYI_CRED, "sk-test", "Pay-i Proxy"
        )
        self.assertEqual(result["parameters"]["model"], "gpt-4o")
        self.assertEqual(result["parameters"]["provider"], "openai")

    def test_messages_json_string_preserved(self):
        result = migrate.build_payi_proxy_node(
            OPENAI_APP_NODE, PAYI_CRED, "sk-test", "Pay-i Proxy"
        )
        msgs = json.loads(result["parameters"]["messages"])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "Summarize this")

    def test_messages_from_plain_prompt_string(self):
        node = copy.deepcopy(OPENAI_APP_NODE)
        node["parameters"] = {"model": "gpt-4o", "prompt": "Hello world"}
        result = migrate.build_payi_proxy_node(node, PAYI_CRED, "sk-test", "Pay-i Proxy")
        msgs = json.loads(result["parameters"]["messages"])
        self.assertEqual(msgs[0]["content"], "Hello world")

    def test_messages_from_list(self):
        node = copy.deepcopy(OPENAI_APP_NODE)
        node["parameters"]["messages"] = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
        ]
        result = migrate.build_payi_proxy_node(node, PAYI_CRED, "sk-test", "Pay-i Proxy")
        msgs = json.loads(result["parameters"]["messages"])
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")

    def test_messages_from_dict_values_format(self):
        node = copy.deepcopy(OPENAI_APP_NODE)
        node["parameters"]["messages"] = {
            "values": [
                {"role": "user", "content": "What is 2+2?"},
            ]
        }
        result = migrate.build_payi_proxy_node(node, PAYI_CRED, "sk-test", "Pay-i Proxy")
        msgs = json.loads(result["parameters"]["messages"])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["content"], "What is 2+2?")

    def test_messages_empty_dict_values(self):
        node = copy.deepcopy(OPENAI_APP_NODE)
        node["parameters"]["messages"] = {"values": []}
        result = migrate.build_payi_proxy_node(node, PAYI_CRED, "sk-test", "Pay-i Proxy")
        msgs = json.loads(result["parameters"]["messages"])
        self.assertEqual(msgs[0]["content"], "Hello!")

    def test_messages_fallback_default(self):
        node = {"id": "x", "parameters": {"model": "gpt-4o"}, "position": [0, 0]}
        result = migrate.build_payi_proxy_node(node, PAYI_CRED, "sk-test", "Pay-i Proxy")
        msgs = json.loads(result["parameters"]["messages"])
        self.assertEqual(msgs[0]["content"], "Hello!")

    def test_output_defaults(self):
        result = migrate.build_payi_proxy_node(
            OPENAI_APP_NODE, PAYI_CRED, "sk-test", "Pay-i Proxy"
        )
        self.assertTrue(result["parameters"]["includeCostData"])
        self.assertFalse(result["parameters"]["returnFullResponse"])
        self.assertFalse(result["parameters"]["debugLogging"])

    def test_tracking_defaults(self):
        result = migrate.build_payi_proxy_node(
            OPENAI_APP_NODE, PAYI_CRED, "sk-test", "Pay-i Proxy"
        )
        self.assertEqual(result["parameters"]["useCaseName"], "={{ $workflow.name.replaceAll(' ', '-') }}")
        self.assertEqual(result["parameters"]["useCaseId"], "={{ 'openai/' + $parameter.model + '/' + $execution.id }}")
        self.assertEqual(result["parameters"]["useCaseStep"], "={{ $node.name }}")

    def test_model_from_resource_locator_object(self):
        """n8n 2.x stores model as resourceLocator: {mode, value}."""
        node = {
            "id": "x",
            "parameters": {
                "model": {"mode": "list", "value": "gpt-4o"},
                "messages": '[{"role": "user", "content": "Hi"}]',
            },
            "position": [0, 0],
        }
        result = migrate.build_payi_proxy_node(node, PAYI_CRED, "sk-test", "Pay-i Proxy")
        self.assertEqual(result["parameters"]["model"], "gpt-4o")


# ── Tests: build_payi_chat_model_anthropic_node ──────────────────────────────

class TestBuildPayiChatModelAnthropicNode(unittest.TestCase):
    def test_basic_fields(self):
        result = migrate.build_payi_chat_model_anthropic_node(
            ANTHROPIC_CHAT_MODEL_NODE_V12, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model"
        )
        self.assertEqual(result["id"], "node-ccc")
        self.assertEqual(result["name"], "Pay-i Anthropic Chat Model")
        self.assertEqual(result["type"], "n8n-nodes-payi.lmChatPayiAnthropic")
        self.assertEqual(result["typeVersion"], 1)
        self.assertEqual(result["position"], [400, 500])

    def test_model_extraction(self):
        """Default model when none specified should be empty string."""
        node = {"id": "x", "parameters": {}, "position": [0, 0]}
        result = migrate.build_payi_chat_model_anthropic_node(node, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model")
        self.assertEqual(result["parameters"]["model"], "")

    def test_model_from_resource_locator(self):
        """Handle resourceLocator dict format for model."""
        node = {
            "id": "x",
            "parameters": {
                "model": {"mode": "list", "value": "claude-sonnet-4-20250514"},
                "options": {},
            },
            "position": [0, 0],
        }
        result = migrate.build_payi_chat_model_anthropic_node(node, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model")
        self.assertEqual(result["parameters"]["model"], "claude-sonnet-4-20250514")

    def test_options_mapping(self):
        """maxTokensToSample, temperature, topK, topP are mapped correctly."""
        node = {
            "id": "x",
            "parameters": {
                "model": "claude-sonnet-4-20250514",
                "options": {
                    "maxTokensToSample": 4096,
                    "temperature": 0.8,
                    "topK": 40,
                    "topP": 0.95,
                },
            },
            "position": [0, 0],
        }
        result = migrate.build_payi_chat_model_anthropic_node(node, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model")
        opts = result["parameters"]["options"]
        self.assertEqual(opts["maxTokensToSample"], 4096)
        self.assertEqual(opts["temperature"], 0.8)
        self.assertEqual(opts["topK"], 40)
        self.assertEqual(opts["topP"], 0.95)

    def test_thinking_mode_options(self):
        """When source has thinking and thinkingBudget, these are preserved."""
        node = {
            "id": "x",
            "parameters": {
                "model": "claude-sonnet-4-20250514",
                "options": {
                    "thinking": True,
                    "thinkingBudget": 10000,
                },
            },
            "position": [0, 0],
        }
        result = migrate.build_payi_chat_model_anthropic_node(node, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model")
        opts = result["parameters"]["options"]
        self.assertTrue(opts["thinking"])
        self.assertEqual(opts["thinkingBudget"], 10000)

    def test_empty_options(self):
        """When source has no options, result has empty options dict."""
        node = {"id": "x", "parameters": {"model": "claude-sonnet-4-20250514"}, "position": [0, 0]}
        result = migrate.build_payi_chat_model_anthropic_node(node, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model")
        self.assertEqual(result["parameters"]["options"], {})

    def test_credential_reference(self):
        """payiApi credential is set correctly."""
        result = migrate.build_payi_chat_model_anthropic_node(
            ANTHROPIC_CHAT_MODEL_NODE_V12, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model"
        )
        cred_ref = result["credentials"]["payiApi"]
        self.assertEqual(cred_ref["id"], "cred-123")
        self.assertEqual(cred_ref["name"], "Pay-i API")

    def test_tracking_defaults(self):
        """useCaseName and useCaseId expressions are set."""
        result = migrate.build_payi_chat_model_anthropic_node(
            ANTHROPIC_CHAT_MODEL_NODE_V12, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model"
        )
        params = result["parameters"]
        self.assertEqual(params["useCaseName"], "={{ $workflow.name.replaceAll(' ', '-') }}")
        self.assertEqual(params["useCaseId"], "={{ 'anthropic/' + $parameter.model + '/' + $execution.id }}")
        self.assertEqual(params["useCaseStep"], "={{ $node.name }}")

    def test_no_plaintext_provider_key(self):
        """providerApiKey should NOT be in parameters — credentials are passed through."""
        result = migrate.build_payi_chat_model_anthropic_node(
            ANTHROPIC_CHAT_MODEL_NODE_V12, PAYI_CRED, "sk-ant-my-key", "Pay-i Anthropic Chat Model"
        )
        self.assertNotIn("providerApiKey", result["parameters"])

    def test_credential_id_stringified(self):
        cred = {"id": 99, "name": "Pay-i API"}
        result = migrate.build_payi_chat_model_anthropic_node(
            ANTHROPIC_CHAT_MODEL_NODE_V12, cred, "sk-ant-test", "Pay-i Anthropic Chat Model"
        )
        self.assertEqual(result["credentials"]["payiApi"]["id"], "99")

    def test_model_string_preserved(self):
        """Model specified as a plain string is preserved."""
        result = migrate.build_payi_chat_model_anthropic_node(
            ANTHROPIC_CHAT_MODEL_NODE, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model"
        )
        self.assertEqual(result["parameters"]["model"], "claude-sonnet-4-20250514")

    def test_unknown_options_excluded(self):
        """Options not in the Anthropic allowlist are excluded."""
        node = {
            "id": "x",
            "parameters": {
                "model": "claude-sonnet-4-20250514",
                "options": {
                    "temperature": 0.5,
                    "unknownOption": "foo",
                    "frequencyPenalty": 0.1,
                },
            },
            "position": [0, 0],
        }
        result = migrate.build_payi_chat_model_anthropic_node(node, PAYI_CRED, "sk-ant-test", "Pay-i Anthropic Chat Model")
        opts = result["parameters"]["options"]
        self.assertIn("temperature", opts)
        self.assertNotIn("unknownOption", opts)
        self.assertNotIn("frequencyPenalty", opts)


# ── Tests: unique_node_name ──────────────────────────────────────────────────

class TestUniqueNodeName(unittest.TestCase):
    def test_no_collision(self):
        self.assertEqual(
            migrate.unique_node_name("Pay-i Chat Model", {"Trigger", "Agent"}),
            "Pay-i Chat Model",
        )

    def test_collision_adds_suffix(self):
        self.assertEqual(
            migrate.unique_node_name("Pay-i Chat Model", {"Pay-i Chat Model", "Agent"}),
            "Pay-i Chat Model 1",
        )

    def test_multiple_collisions(self):
        existing = {"Pay-i Chat Model", "Pay-i Chat Model 1", "Pay-i Chat Model 2"}
        self.assertEqual(
            migrate.unique_node_name("Pay-i Chat Model", existing),
            "Pay-i Chat Model 3",
        )

    def test_empty_set(self):
        self.assertEqual(migrate.unique_node_name("Foo", set()), "Foo")


# ── Tests: rewire_connections ────────────────────────────────────────────────

class TestRewireConnections(unittest.TestCase):
    def test_renames_source_key(self):
        connections = {
            "OpenAI Chat Model": {
                "ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]
            },
        }
        result = migrate.rewire_connections(connections, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertIn("Pay-i Chat Model", result)
        self.assertNotIn("OpenAI Chat Model", result)

    def test_renames_target_reference(self):
        connections = {
            "Trigger": {
                "main": [[{"node": "OpenAI Chat Model", "type": "main", "index": 0}]]
            },
        }
        result = migrate.rewire_connections(connections, "OpenAI Chat Model", "Pay-i Chat Model")
        target = result["Trigger"]["main"][0][0]
        self.assertEqual(target["node"], "Pay-i Chat Model")

    def test_renames_both_source_and_target(self):
        connections = {
            "OpenAI Chat Model": {
                "ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]
            },
            "Trigger": {
                "main": [[{"node": "OpenAI Chat Model", "type": "main", "index": 0}]]
            },
        }
        result = migrate.rewire_connections(connections, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertIn("Pay-i Chat Model", result)
        self.assertNotIn("OpenAI Chat Model", result)
        self.assertEqual(result["Trigger"]["main"][0][0]["node"], "Pay-i Chat Model")

    def test_no_change_when_names_equal(self):
        connections = {"Foo": {"main": [[{"node": "Bar", "type": "main", "index": 0}]]}}
        result = migrate.rewire_connections(connections, "Foo", "Foo")
        self.assertIs(result, connections)  # same object, no copy

    def test_other_nodes_untouched(self):
        connections = {
            "Trigger": {
                "main": [[
                    {"node": "OpenAI", "type": "main", "index": 0},
                    {"node": "Logger", "type": "main", "index": 1},
                ]]
            },
        }
        result = migrate.rewire_connections(connections, "OpenAI", "Pay-i Proxy")
        slot = result["Trigger"]["main"][0]
        self.assertEqual(slot[0]["node"], "Pay-i Proxy")
        self.assertEqual(slot[1]["node"], "Logger")  # untouched

    def test_empty_connections(self):
        result = migrate.rewire_connections({}, "Old", "New")
        self.assertEqual(result, {})

    def test_multiple_connection_types(self):
        connections = {
            "OpenAI Chat Model": {
                "ai_languageModel": [[{"node": "Agent", "type": "ai_languageModel", "index": 0}]],
                "main": [[{"node": "Output", "type": "main", "index": 0}]],
            },
        }
        result = migrate.rewire_connections(connections, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertIn("ai_languageModel", result["Pay-i Chat Model"])
        self.assertIn("main", result["Pay-i Chat Model"])

    def test_multiple_slots(self):
        connections = {
            "Router": {
                "main": [
                    [{"node": "OpenAI", "type": "main", "index": 0}],
                    [{"node": "Logger", "type": "main", "index": 0}],
                ]
            },
        }
        result = migrate.rewire_connections(connections, "OpenAI", "Pay-i Proxy")
        self.assertEqual(result["Router"]["main"][0][0]["node"], "Pay-i Proxy")
        self.assertEqual(result["Router"]["main"][1][0]["node"], "Logger")


# ── Tests: fix_expression_references ─────────────────────────────────────────

class TestFixExpressionReferences(unittest.TestCase):
    def test_replaces_single_quote_reference(self):
        nodes = [{"parameters": {"text": "={{ $('OpenAI Chat Model').item.json.output }}"}}]
        count = migrate.fix_expression_references(nodes, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertEqual(count, 1)
        self.assertIn("Pay-i Chat Model", nodes[0]["parameters"]["text"])
        self.assertNotIn("OpenAI Chat Model", nodes[0]["parameters"]["text"])

    def test_replaces_double_quote_reference(self):
        nodes = [{"parameters": {"text": '={{ $("OpenAI Chat Model").item.json }}'}}]
        count = migrate.fix_expression_references(nodes, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertEqual(count, 1)
        self.assertIn("Pay-i Chat Model", nodes[0]["parameters"]["text"])

    def test_no_change_when_no_references(self):
        nodes = [{"parameters": {"text": "hello world"}}]
        count = migrate.fix_expression_references(nodes, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertEqual(count, 0)
        self.assertEqual(nodes[0]["parameters"]["text"], "hello world")

    def test_no_change_when_names_equal(self):
        nodes = [{"parameters": {"text": "={{ $('Foo').item }}"}}]
        count = migrate.fix_expression_references(nodes, "Foo", "Foo")
        self.assertEqual(count, 0)

    def test_nested_dict_parameters(self):
        nodes = [{"parameters": {"outer": {"inner": "={{ $('Old').item }}"}}}]
        count = migrate.fix_expression_references(nodes, "Old", "New")
        self.assertEqual(count, 1)
        self.assertEqual(nodes[0]["parameters"]["outer"]["inner"], "={{ $('New').item }}")

    def test_list_parameters(self):
        nodes = [{"parameters": {"items": ["={{ $('Old').item }}", "no ref"]}}]
        count = migrate.fix_expression_references(nodes, "Old", "New")
        self.assertEqual(count, 1)
        self.assertEqual(nodes[0]["parameters"]["items"][0], "={{ $('New').item }}")
        self.assertEqual(nodes[0]["parameters"]["items"][1], "no ref")

    def test_multiple_references_in_one_string(self):
        nodes = [{"parameters": {"text": "={{ $('Old').a }} + {{ $('Old').b }}"}}]
        count = migrate.fix_expression_references(nodes, "Old", "New")
        # count is 1 because replace_in_value counts per string, not per match
        self.assertEqual(count, 1)
        self.assertNotIn("Old", nodes[0]["parameters"]["text"])

    def test_multiple_nodes_with_references(self):
        nodes = [
            {"parameters": {"text": "={{ $('Old').item }}"}},
            {"parameters": {"other": "={{ $('Old').data }}"}},
            {"parameters": {"clean": "no ref"}},
        ]
        count = migrate.fix_expression_references(nodes, "Old", "New")
        self.assertEqual(count, 2)

    def test_skips_nodes_without_parameters(self):
        nodes = [{"name": "Trigger"}]  # no 'parameters' key
        count = migrate.fix_expression_references(nodes, "Old", "New")
        self.assertEqual(count, 0)

    def test_non_string_values_unchanged(self):
        nodes = [{"parameters": {"count": 42, "flag": True, "nothing": None}}]
        count = migrate.fix_expression_references(nodes, "Old", "New")
        self.assertEqual(count, 0)
        self.assertEqual(nodes[0]["parameters"]["count"], 42)


# ── Tests: filter_workflow_for_update ────────────────────────────────────────

class TestFilterWorkflowForUpdate(unittest.TestCase):
    def test_strips_read_only_fields(self):
        wf = make_workflow()
        filtered = migrate.filter_workflow_for_update(wf)
        for field in ("id", "active", "createdAt", "updatedAt", "versionId", "tags"):
            self.assertNotIn(field, filtered)

    def test_keeps_required_fields(self):
        wf = make_workflow(nodes=[TRIGGER_NODE])
        filtered = migrate.filter_workflow_for_update(wf)
        self.assertIn("name", filtered)
        self.assertIn("nodes", filtered)
        self.assertIn("connections", filtered)
        self.assertIn("settings", filtered)

    def test_strips_non_allowed_top_level_fields(self):
        wf = make_workflow()
        wf["customField"] = "drop me"
        wf["triggerCount"] = 5
        wf["meta"] = {"some": "data"}
        filtered = migrate.filter_workflow_for_update(wf)
        for field in ("customField", "triggerCount", "meta", "staticData", "pinData"):
            self.assertNotIn(field, filtered)

    def test_sanitizes_settings_keys(self):
        wf = make_workflow()
        wf["settings"] = {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "unknownSetting": "drop me",
        }
        filtered = migrate.filter_workflow_for_update(wf)
        self.assertIn("executionOrder", filtered["settings"])
        self.assertIn("saveManualExecutions", filtered["settings"])
        self.assertNotIn("unknownSetting", filtered["settings"])

    def test_strips_unknown_fields(self):
        wf = make_workflow()
        wf["customField"] = "drop me"
        wf["triggerCount"] = 5
        wf["meta"] = {"some": "data"}
        filtered = migrate.filter_workflow_for_update(wf)
        self.assertNotIn("customField", filtered)
        self.assertNotIn("triggerCount", filtered)
        self.assertNotIn("meta", filtered)


# ── Tests: _redact_dict ─────────────────────────────────────────────────────

class TestRedactDict(unittest.TestCase):
    def test_redacts_apikey(self):
        result = migrate._redact_dict({"apiKey": "sk-secret123"})
        self.assertEqual(result["apiKey"], "****")

    def test_redacts_password(self):
        result = migrate._redact_dict({"password": "p@ss"})
        self.assertEqual(result["password"], "****")

    def test_preserves_safe_values(self):
        result = migrate._redact_dict({"name": "My Cred", "baseUrl": "https://example.com"})
        self.assertEqual(result["name"], "My Cred")
        self.assertEqual(result["baseUrl"], "https://example.com")

    def test_nested_dict_redaction(self):
        result = migrate._redact_dict({"data": {"apiKey": "secret", "url": "https://x.com"}})
        self.assertEqual(result["data"]["apiKey"], "****")
        self.assertEqual(result["data"]["url"], "https://x.com")


# ── Tests: ensure_payi_credential ────────────────────────────────────────────

class TestEnsurePayiCredential(unittest.TestCase):
    def test_finds_existing_credential(self):
        client = MagicMock()
        client.get.return_value = {
            "data": [
                {"id": "c-1", "name": "OpenAI", "type": "openAiApi"},
                {"id": "c-2", "name": "Pay-i API", "type": "payiApi"},
            ]
        }
        result = migrate.ensure_payi_credential(client, "pk-test", "https://api.pay-i.com")
        self.assertEqual(result["id"], "c-2")
        self.assertEqual(result["name"], "Pay-i API")
        client.post.assert_not_called()

    def test_creates_credential_when_missing(self):
        client = MagicMock()
        client.get.return_value = {
            "data": [
                {"id": "c-1", "name": "OpenAI", "type": "openAiApi"},
            ]
        }
        client.post.return_value = {"id": "c-new", "name": "Pay-i API", "type": "payiApi"}
        result = migrate.ensure_payi_credential(client, "pk-test", "https://api.pay-i.com")
        self.assertEqual(result["id"], "c-new")
        client.post.assert_called_once()
        call_body = client.post.call_args[0][1]
        self.assertEqual(call_body["type"], "payiApi")
        self.assertEqual(call_body["data"]["apiKey"], "pk-test")
        self.assertEqual(call_body["data"]["baseUrl"], "https://api.pay-i.com")

    def test_handles_empty_credentials_list(self):
        client = MagicMock()
        client.get.return_value = {"data": []}
        client.post.return_value = {"id": "c-new"}
        result = migrate.ensure_payi_credential(client, "pk-test", "https://api.pay-i.com")
        self.assertEqual(result["id"], "c-new")
        client.post.assert_called_once()


# ── Tests: collect_provider_keys ─────────────────────────────────────────────

class TestCollectProviderKeys(unittest.TestCase):
    def test_reads_from_env(self):
        nodes = [{"feasible": True, "provider": "openai"}]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-from-env"}):
            keys = migrate.collect_provider_keys(nodes)
        self.assertEqual(keys["openai"], "sk-from-env")

    def test_prompts_when_no_env(self):
        nodes = [{"feasible": True, "provider": "openai"}]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with patch.object(migrate.getpass, "getpass", return_value="sk-interactive"):
                keys = migrate.collect_provider_keys(nodes)
        self.assertEqual(keys["openai"], "sk-interactive")

    def test_skips_empty_key(self):
        nodes = [{"feasible": True, "provider": "openai"}]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with patch.object(migrate.getpass, "getpass", return_value=""):
                keys = migrate.collect_provider_keys(nodes)
        self.assertNotIn("openai", keys)

    def test_ignores_infeasible_nodes(self):
        nodes = [
            {"feasible": False, "provider": "google"},
            {"feasible": True, "provider": "openai"},
        ]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            keys = migrate.collect_provider_keys(nodes)
        self.assertIn("openai", keys)
        self.assertNotIn("google", keys)

    def test_deduplicates_providers(self):
        nodes = [
            {"feasible": True, "provider": "openai"},
            {"feasible": True, "provider": "openai"},
        ]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            keys = migrate.collect_provider_keys(nodes)
        self.assertEqual(len(keys), 1)


# ── Tests: End-to-End (main with mocked API) ────────────────────────────────

class TestMainDryRun(unittest.TestCase):
    """Test the main() function in dry-run mode with mocked API calls."""

    def _make_env(self):
        return {
            "N8N_BASE_URL": "http://localhost:5678",
            "N8N_API_KEY": "test-key",
            "PAYI_BASE_URL": "https://api.pay-i.com",
            "PAYI_API_KEY": "pk-test",
        }

    def test_dry_run_detects_and_reports(self):
        workflow = make_workflow(
            "wf-1", "Test Bot",
            nodes=[TRIGGER_NODE, OPENAI_CHAT_MODEL_NODE, AGENT_NODE],
            connections={
                "OpenAI Chat Model": {
                    "ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]
                },
            },
        )

        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--dry-run", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request") as mock_req:
                    mock_req.side_effect = lambda method, path, body=None, quiet=False: {
                        ("/api/v1/workflows", "GET"): {"data": [workflow]},
                        (f"/api/v1/workflows/wf-1", "GET"): workflow,
                    }.get((path, method), {})

                    rc = migrate.main()

        self.assertEqual(rc, 0)

    def test_missing_env_returns_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("sys.argv", ["migrate"]):
                rc = migrate.main()
        self.assertEqual(rc, 1)

    def test_no_workflows_returns_zero(self):
        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--dry-run", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request") as mock_req:
                    mock_req.return_value = {"data": []}
                    rc = migrate.main()
        self.assertEqual(rc, 0)

    def test_no_llm_nodes_returns_zero(self):
        workflow = make_workflow("wf-1", "Clean Bot", nodes=[TRIGGER_NODE])
        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--dry-run", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request") as mock_req:
                    mock_req.return_value = {"data": [workflow]}
                    rc = migrate.main()
        self.assertEqual(rc, 0)

    def test_only_infeasible_nodes_returns_zero(self):
        azure_node = {
            "id": "node-azure",
            "name": "Azure OpenAI Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
            "typeVersion": 1,
            "position": [400, 500],
            "parameters": {"model": "gpt-4o"},
        }
        workflow = make_workflow("wf-1", "Azure Bot", nodes=[azure_node])
        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--dry-run", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request") as mock_req:
                    mock_req.return_value = {"data": [workflow]}
                    rc = migrate.main()
        self.assertEqual(rc, 0)


class TestMainFullMigration(unittest.TestCase):
    """Test the main() function in full mode with mocked API and auto-yes."""

    def _make_env(self):
        return {
            "N8N_BASE_URL": "http://localhost:5678",
            "N8N_API_KEY": "test-key",
            "PAYI_BASE_URL": "https://api.pay-i.com",
            "PAYI_API_KEY": "pk-test",
            "OPENAI_API_KEY": "sk-from-env",
        }

    def test_full_migration_chat_model(self):
        """End-to-end: OpenAI Chat Model -> Pay-i Chat Model with auto-yes."""
        workflow = make_workflow(
            "wf-1", "Test Bot",
            nodes=[TRIGGER_NODE, copy.deepcopy(OPENAI_CHAT_MODEL_NODE), copy.deepcopy(AGENT_NODE)],
            connections={
                "OpenAI Chat Model": {
                    "ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]
                },
            },
        )

        put_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-1":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                put_calls.append({"path": path, "body": body})
                return {}
            return {}

        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        # Verify a PUT was issued
        self.assertEqual(len(put_calls), 1)
        put_body = put_calls[0]["body"]

        # Verify the node was replaced
        node_types = [n["type"] for n in put_body["nodes"]]
        self.assertIn("n8n-nodes-payi.lmChatPayi", node_types)
        self.assertNotIn("@n8n/n8n-nodes-langchain.lmChatOpenAi", node_types)

        # Verify connections were rewired
        self.assertIn("Pay-i Chat Model", put_body["connections"])
        self.assertNotIn("OpenAI Chat Model", put_body["connections"])

        # Verify read-only fields stripped
        self.assertNotIn("id", put_body)
        self.assertNotIn("active", put_body)
        self.assertNotIn("createdAt", put_body)

    def test_full_migration_proxy_node(self):
        """End-to-end: OpenAI app node -> Pay-i Proxy with auto-yes."""
        workflow = make_workflow(
            "wf-2", "Data Pipeline",
            nodes=[TRIGGER_NODE, copy.deepcopy(OPENAI_APP_NODE)],
            connections={
                "Manual Trigger": {
                    "main": [[{"node": "OpenAI", "type": "main", "index": 0}]]
                },
            },
        )

        put_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-2":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                put_calls.append({"path": path, "body": body})
                return {}
            return {}

        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        self.assertEqual(len(put_calls), 1)
        put_body = put_calls[0]["body"]

        node_types = [n["type"] for n in put_body["nodes"]]
        self.assertIn("n8n-nodes-payi.payi", node_types)
        self.assertNotIn("@n8n/n8n-nodes-langchain.openai", node_types)

        # Verify connection target was renamed
        trigger_conns = put_body["connections"]["Manual Trigger"]["main"][0]
        self.assertEqual(trigger_conns[0]["node"], "Pay-i Proxy")

    def test_full_migration_anthropic_chat_model(self):
        """End-to-end: Anthropic Chat Model -> Pay-i Anthropic Chat Model with auto-yes."""
        anthropic_node = copy.deepcopy(ANTHROPIC_CHAT_MODEL_NODE_V12)
        agent = copy.deepcopy(AGENT_NODE)
        agent["parameters"]["text"] = "={{ $('Anthropic Chat Model').item.json.output }}"
        workflow = make_workflow(
            "wf-3", "Anthropic Bot",
            nodes=[TRIGGER_NODE, anthropic_node, agent],
            connections={
                "Anthropic Chat Model": {
                    "ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]
                },
            },
        )

        put_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-3":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                put_calls.append({"path": path, "body": body})
                return {}
            return {}

        env = {**self._make_env(), "ANTHROPIC_API_KEY": "sk-ant-test"}
        with patch.dict(os.environ, env, clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        # Verify a PUT was issued
        self.assertEqual(len(put_calls), 1)
        put_body = put_calls[0]["body"]

        # Verify the node was replaced with Anthropic Pay-i type
        node_types = [n["type"] for n in put_body["nodes"]]
        self.assertIn("n8n-nodes-payi.lmChatPayiAnthropic", node_types)
        self.assertNotIn("@n8n/n8n-nodes-langchain.lmChatAnthropic", node_types)

        # Verify connections were rewired
        self.assertIn("Pay-i Anthropic Chat Model", put_body["connections"])
        self.assertNotIn("Anthropic Chat Model", put_body["connections"])

        # Verify expression references were updated
        agent_node = next(n for n in put_body["nodes"] if n["name"] == "AI Agent")
        self.assertIn("Pay-i Anthropic Chat Model", agent_node["parameters"]["text"])
        # The old bare name should not appear — check by ensuring the only occurrence
        # of "Anthropic Chat Model" is prefixed with "Pay-i "
        self.assertNotIn("$('Anthropic Chat Model')", agent_node["parameters"]["text"])

        # Verify read-only fields stripped
        self.assertNotIn("id", put_body)
        self.assertNotIn("active", put_body)

    def test_expression_references_fixed_in_full_migration(self):
        """Verify $('OpenAI Chat Model') references are updated."""
        agent = copy.deepcopy(AGENT_NODE)
        workflow = make_workflow(
            "wf-1", "Ref Test",
            nodes=[TRIGGER_NODE, copy.deepcopy(OPENAI_CHAT_MODEL_NODE), agent],
            connections={
                "OpenAI Chat Model": {
                    "ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]
                },
            },
        )

        put_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-1":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                put_calls.append({"path": path, "body": body})
                return {}
            return {}

        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        put_body = put_calls[0]["body"]

        # Find the agent node and check its expression was updated
        agent_node = next(n for n in put_body["nodes"] if n["name"] == "AI Agent")
        self.assertIn("Pay-i Chat Model", agent_node["parameters"]["text"])
        self.assertNotIn("OpenAI Chat Model", agent_node["parameters"]["text"])

    def test_creates_credential_when_missing(self):
        """Verify credential creation when no payiApi exists."""
        workflow = make_workflow(
            "wf-1", "Test",
            nodes=[TRIGGER_NODE, copy.deepcopy(OPENAI_CHAT_MODEL_NODE)],
            connections={},
        )
        post_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-1":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": []}  # No credentials
            if method == "POST" and path == "/api/v1/credentials":
                post_calls.append(body)
                return {"id": "c-new", "name": "Pay-i API"}
            if method == "PUT":
                return {}
            return {}

        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        self.assertEqual(len(post_calls), 1)
        self.assertEqual(post_calls[0]["type"], "payiApi")

    def test_workflow_filter_flag(self):
        """Verify --workflow ID only fetches that one workflow."""
        workflow = make_workflow(
            "wf-99", "Target",
            nodes=[TRIGGER_NODE, copy.deepcopy(OPENAI_CHAT_MODEL_NODE)],
            connections={},
        )

        get_paths = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET":
                get_paths.append(path)
            if method == "GET" and path == "/api/v1/workflows/wf-99":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                return {}
            return {}

        with patch.dict(os.environ, self._make_env(), clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes", "--workflow", "wf-99"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        # Should NOT have called /api/v1/workflows (list all)
        self.assertNotIn("/api/v1/workflows", get_paths)
        self.assertIn("/api/v1/workflows/wf-99", get_paths)


# ── Tests: N8nApiClient ─────────────────────────────────────────────────────

class TestN8nApiClient(unittest.TestCase):
    def test_strips_trailing_slash(self):
        client = migrate.N8nApiClient("http://localhost:5678/", "key")
        self.assertEqual(client.base_url, "http://localhost:5678")

    def test_sets_headers(self):
        client = migrate.N8nApiClient("http://localhost:5678", "my-api-key")
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"ok": true}'
            mock_resp.status = 200
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            client.get("/api/v1/test")

            req = mock_open.call_args[0][0]
            self.assertEqual(req.get_header("X-n8n-api-key"), "my-api-key")
            self.assertEqual(req.get_header("Content-type"), "application/json")
            self.assertEqual(req.get_header("Accept"), "application/json")


# ── Tests: Edge Cases ────────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):
    def test_name_collision_during_migration(self):
        """If 'Pay-i Chat Model' already exists, suffix should be added."""
        existing_payi_node = {
            "id": "node-existing",
            "name": "Pay-i Chat Model",
            "type": "n8n-nodes-payi.lmChatPayi",
            "typeVersion": 1,
            "position": [200, 200],
            "parameters": {},
        }
        workflow = make_workflow(
            "wf-1", "Collision Test",
            nodes=[TRIGGER_NODE, existing_payi_node, copy.deepcopy(OPENAI_CHAT_MODEL_NODE)],
            connections={},
        )

        put_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-1":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                put_calls.append(body)
                return {}
            return {}

        env = {
            "N8N_BASE_URL": "http://localhost:5678",
            "N8N_API_KEY": "test-key",
            "PAYI_BASE_URL": "https://api.pay-i.com",
            "PAYI_API_KEY": "pk-test",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        self.assertEqual(len(put_calls), 1)
        names = [n["name"] for n in put_calls[0]["nodes"]]
        self.assertIn("Pay-i Chat Model", names)       # existing
        self.assertIn("Pay-i Chat Model 1", names)     # new with suffix

    def test_multiple_openai_nodes_same_workflow(self):
        """Two OpenAI chat models in one workflow get distinct names."""
        node2 = copy.deepcopy(OPENAI_CHAT_MODEL_NODE)
        node2["id"] = "node-ddd"
        node2["name"] = "OpenAI Chat Model 1"
        node2["parameters"]["model"] = "gpt-4.1"

        workflow = make_workflow(
            "wf-1", "Multi-Node Test",
            nodes=[TRIGGER_NODE, copy.deepcopy(OPENAI_CHAT_MODEL_NODE), node2],
            connections={},
        )

        put_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-1":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                put_calls.append(body)
                return {}
            return {}

        env = {
            "N8N_BASE_URL": "http://localhost:5678",
            "N8N_API_KEY": "test-key",
            "PAYI_BASE_URL": "https://api.pay-i.com",
            "PAYI_API_KEY": "pk-test",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        self.assertEqual(len(put_calls), 1)
        names = [n["name"] for n in put_calls[0]["nodes"]]
        # Both should be migrated with unique names
        payi_names = [n for n in names if n.startswith("Pay-i Chat Model")]
        self.assertEqual(len(payi_names), 2)
        self.assertEqual(len(set(payi_names)), 2)  # all unique


# ── Tests: prompt_select_nodes ────────────────────────────────────────────────

class TestPromptSelectNodes(unittest.TestCase):
    """Tests for the interactive node selection menu."""

    def _make_found(self):
        """Create a sample found-nodes list with mix of feasible and infeasible."""
        return [
            {
                "workflow_id": "wf-1", "workflow_name": "Bot A",
                "node": {"name": "OpenAI Chat Model"}, "node_type": "x",
                "provider": "openai", "replacement": "chat_model",
                "feasible": True, "label": "OpenAI Chat Model (LangChain)",
            },
            {
                "workflow_id": "wf-1", "workflow_name": "Bot A",
                "node": {"name": "Azure OpenAI Chat Model"}, "node_type": "x",
                "provider": "azureOpenai", "replacement": None,
                "feasible": False, "label": "Azure OpenAI Chat Model (LangChain)",
                "skip_reason": "Pay-i Chat Model currently supports OpenAI-compatible providers only",
            },
            {
                "workflow_id": "wf-2", "workflow_name": "Pipeline",
                "node": {"name": "OpenAI"}, "node_type": "x",
                "provider": "openai", "replacement": "proxy",
                "feasible": True, "label": "OpenAI (App Node)",
            },
        ]

    def test_all_selects_all_feasible(self):
        found = self._make_found()
        with patch("builtins.input", return_value="all"):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(n["feasible"] for n in selected))

    def test_empty_input_selects_all_feasible(self):
        found = self._make_found()
        with patch("builtins.input", return_value=""):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 2)

    def test_none_selects_nothing(self):
        found = self._make_found()
        with patch("builtins.input", return_value="none"):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 0)

    def test_specific_numbers(self):
        found = self._make_found()
        with patch("builtins.input", return_value="1,3"):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 2)
        names = [n["node"]["name"] for n in selected]
        self.assertIn("OpenAI Chat Model", names)
        self.assertIn("OpenAI", names)

    def test_single_number(self):
        found = self._make_found()
        with patch("builtins.input", return_value="3"):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["node"]["name"], "OpenAI")

    def test_infeasible_number_skipped(self):
        found = self._make_found()
        with patch("builtins.input", return_value="2"):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 0)

    def test_out_of_range_skipped(self):
        found = self._make_found()
        with patch("builtins.input", return_value="99"):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 0)

    def test_non_numeric_input_skipped(self):
        found = self._make_found()
        with patch("builtins.input", return_value="abc"):
            selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 0)

    def test_mixed_valid_and_invalid(self):
        found = self._make_found()
        with patch("builtins.input", return_value="1, 2, 99, abc"):
            selected = migrate.prompt_select_nodes(found)
        # Only #1 is valid and feasible; #2 is infeasible, #99 is out of range, abc is non-numeric
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["node"]["name"], "OpenAI Chat Model")

    def test_no_feasible_returns_empty(self):
        found = [
            {
                "workflow_id": "wf-1", "workflow_name": "Bot",
                "node": {"name": "Azure OpenAI"}, "node_type": "x",
                "provider": "azureOpenai", "replacement": None,
                "feasible": False, "label": "Azure OpenAI",
                "skip_reason": "not supported",
            },
        ]
        # Should not call input() when there are no migratable nodes
        selected = migrate.prompt_select_nodes(found)
        self.assertEqual(len(selected), 0)


# ── Tests: Sample Workflow Fixture ────────────────────────────────────────────

SAMPLE_WF_PATH = os.path.join(os.path.dirname(__file__), "sample-workflow-all-providers.json")


class TestSampleWorkflowFixture(unittest.TestCase):
    """Tests using the sample-workflow-all-providers.json fixture."""

    @classmethod
    def setUpClass(cls):
        with open(SAMPLE_WF_PATH) as f:
            cls.workflow = json.load(f)
        # Add id field like the API would return
        cls.workflow["id"] = "wf-sample"

    def test_detects_all_provider_nodes(self):
        found = migrate.find_llm_nodes([self.workflow])
        self.assertEqual(len(found), 5)  # 5 LLM nodes total

    def test_feasibility_classification(self):
        found = migrate.find_llm_nodes([self.workflow])
        feasible = [n for n in found if n["feasible"]]
        infeasible = [n for n in found if not n["feasible"]]
        # OpenAI Chat Model + OpenAI App Node + Anthropic Chat Model + Azure + Bedrock = 5 feasible
        self.assertEqual(len(feasible), 5)
        # All are now feasible
        self.assertEqual(len(infeasible), 0)

    def test_feasible_providers(self):
        found = migrate.find_llm_nodes([self.workflow])
        feasible = [n for n in found if n["feasible"]]
        providers = {n["provider"] for n in feasible}
        self.assertEqual(providers, {"openai", "anthropic", "azureOpenai", "bedrock"})

    def test_infeasible_providers(self):
        found = migrate.find_llm_nodes([self.workflow])
        infeasible = [n for n in found if not n["feasible"]]
        providers = {n["provider"] for n in infeasible}
        self.assertEqual(providers, set())

    def test_replacement_types(self):
        found = migrate.find_llm_nodes([self.workflow])
        feasible = sorted([n for n in found if n["feasible"]], key=lambda n: n["node"]["name"])
        # OpenAI App Node -> proxy
        app_node = next(n for n in feasible if n["node"]["name"] == "OpenAI")
        self.assertEqual(app_node["replacement"], "proxy")
        # OpenAI Chat Model -> chat_model
        chat_node = next(n for n in feasible if n["node"]["name"] == "OpenAI Chat Model")
        self.assertEqual(chat_node["replacement"], "chat_model")
        # Anthropic Chat Model -> chat_model_anthropic
        anthropic_node = next(n for n in feasible if n["node"]["name"] == "Anthropic Chat Model")
        self.assertEqual(anthropic_node["replacement"], "chat_model_anthropic")

    def test_chat_model_migration_preserves_model(self):
        """Build a Pay-i Chat Model from the sample's OpenAI Chat Model node."""
        found = migrate.find_llm_nodes([self.workflow])
        chat_info = next(n for n in found if n["node"]["name"] == "OpenAI Chat Model")
        result = migrate.build_payi_chat_model_node(
            chat_info["node"], PAYI_CRED, "sk-test", "Pay-i Chat Model"
        )
        self.assertEqual(result["parameters"]["model"], "gpt-4.1-mini")
        self.assertEqual(result["parameters"]["options"]["temperature"], 0.7)
        self.assertEqual(result["parameters"]["options"]["maxTokens"], 1024)
        self.assertEqual(result["parameters"]["options"]["topP"], 0.95)

    def test_proxy_migration_preserves_messages(self):
        """Build a Pay-i Proxy from the sample's OpenAI app node."""
        found = migrate.find_llm_nodes([self.workflow])
        app_info = next(n for n in found if n["node"]["name"] == "OpenAI")
        result = migrate.build_payi_proxy_node(
            app_info["node"], PAYI_CRED, "sk-test", "Pay-i Proxy"
        )
        msgs = json.loads(result["parameters"]["messages"])
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")

    def test_connection_rewiring_after_chat_model_rename(self):
        """Rewire connections when OpenAI Chat Model -> Pay-i Chat Model."""
        connections = copy.deepcopy(self.workflow["connections"])
        result = migrate.rewire_connections(connections, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertIn("Pay-i Chat Model", result)
        self.assertNotIn("OpenAI Chat Model", result)
        # Target should still point to AI Agent
        target = result["Pay-i Chat Model"]["ai_languageModel"][0][0]
        self.assertEqual(target["node"], "AI Agent")

    def test_connection_rewiring_after_proxy_rename(self):
        """Rewire connections when OpenAI -> Pay-i Proxy."""
        connections = copy.deepcopy(self.workflow["connections"])
        result = migrate.rewire_connections(connections, "OpenAI", "Pay-i Proxy")
        # "Manual Trigger" should now point to "Pay-i Proxy"
        trigger_target = result["Manual Trigger"]["main"][0][0]
        self.assertEqual(trigger_target["node"], "Pay-i Proxy")
        # Source key should be renamed
        self.assertIn("Pay-i Proxy", result)
        self.assertNotIn("OpenAI", result)

    def test_expression_references_in_agent_node(self):
        """Agent node has $('OpenAI Chat Model') and $('Anthropic Chat Model') references."""
        nodes = copy.deepcopy(self.workflow["nodes"])
        count = migrate.fix_expression_references(nodes, "OpenAI Chat Model", "Pay-i Chat Model")
        self.assertGreaterEqual(count, 1)
        agent = next(n for n in nodes if n["name"] == "AI Agent")
        self.assertIn("Pay-i Chat Model", agent["parameters"]["text"])
        # Anthropic ref should be untouched
        self.assertIn("Anthropic Chat Model", agent["parameters"]["fallback"])

    def test_full_dry_run_with_sample_workflow(self):
        """Full dry-run against the sample workflow fixture."""
        workflow = copy.deepcopy(self.workflow)
        env = {
            "N8N_BASE_URL": "http://localhost:5678",
            "N8N_API_KEY": "test-key",
            "PAYI_BASE_URL": "https://api.pay-i.com",
            "PAYI_API_KEY": "pk-test",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("sys.argv", ["migrate", "--dry-run", "--auto-yes"]):
                with patch.object(migrate.N8nApiClient, "_request") as mock_req:
                    mock_req.side_effect = lambda method, path, body=None, quiet=False: {
                        ("/api/v1/workflows", "GET"): {"data": [workflow]},
                        ("/api/v1/workflows/wf-sample", "GET"): workflow,
                    }.get((path, method), {})
                    rc = migrate.main()
        self.assertEqual(rc, 0)

    def test_full_migration_with_sample_workflow(self):
        """Full migration of sample workflow — verifies all feasible node types replaced."""
        workflow = copy.deepcopy(self.workflow)
        put_calls = []

        def mock_request(method, path, body=None, quiet=False):
            if method == "GET" and path == "/api/v1/workflows":
                return {"data": [workflow]}
            if method == "GET" and path == "/api/v1/workflows/wf-sample":
                return copy.deepcopy(workflow)
            if method == "GET" and path == "/api/v1/credentials":
                return {"data": [{"id": "c-1", "name": "Pay-i API", "type": "payiApi"}]}
            if method == "PUT":
                put_calls.append({"path": path, "body": body})
                return {}
            return {}

        env = {
            "N8N_BASE_URL": "http://localhost:5678",
            "N8N_API_KEY": "test-key",
            "PAYI_BASE_URL": "https://api.pay-i.com",
            "PAYI_API_KEY": "pk-test",
            "OPENAI_API_KEY": "sk-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "AZURE_OPENAI_API_KEY": "az-test",
            "AWS_ACCESS_KEY_ID": "AKIA-test",
            "AWS_SECRET_ACCESS_KEY": "secret-test",
            "AWS_REGION": "us-east-1",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("sys.argv", ["migrate", "--auto-yes", "--strategy", "replace"]):
                with patch.object(migrate.N8nApiClient, "_request", side_effect=mock_request):
                    rc = migrate.main()

        self.assertEqual(rc, 0)
        self.assertEqual(len(put_calls), 1)
        put_body = put_calls[0]["body"]
        node_types = {n["type"] for n in put_body["nodes"]}

        # All five Pay-i node types should be present
        self.assertIn("n8n-nodes-payi.lmChatPayi", node_types)
        self.assertIn("n8n-nodes-payi.payi", node_types)
        self.assertIn("n8n-nodes-payi.lmChatPayiAnthropic", node_types)
        self.assertIn("n8n-nodes-payi.lmChatPayiAzure", node_types)
        self.assertIn("n8n-nodes-payi.lmChatPayiBedrock", node_types)

        # All original native nodes should be gone
        self.assertNotIn("@n8n/n8n-nodes-langchain.lmChatOpenAi", node_types)
        self.assertNotIn("@n8n/n8n-nodes-langchain.openai", node_types)
        self.assertNotIn("@n8n/n8n-nodes-langchain.lmChatAnthropic", node_types)
        self.assertNotIn("@n8n/n8n-nodes-langchain.lmChatAzureOpenAi", node_types)
        self.assertNotIn("@n8n/n8n-nodes-langchain.lmChatAwsBedrock", node_types)

        # Connections should be rewired
        self.assertNotIn("OpenAI Chat Model", put_body["connections"])
        self.assertNotIn("OpenAI", put_body["connections"])
        self.assertIn("Pay-i Chat Model", put_body["connections"])
        self.assertIn("Pay-i Proxy", put_body["connections"])


# ── Tests: build_payi_chat_model_azure_node ──────────────────────────────────

AZURE_CHAT_MODEL_NODE = {
    "id": "azure-1",
    "name": "Azure OpenAI Chat Model",
    "type": "@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
    "typeVersion": 1,
    "position": [400, 200],
    "parameters": {
        "model": "gpt-4o",
        "apiVersion": "2024-06-01",
        "options": {"temperature": 0.5, "maxTokens": 2048},
    },
}


class TestBuildPayiChatModelAzureNode(unittest.TestCase):
    def test_basic_fields(self):
        result = migrate.build_payi_chat_model_azure_node(
            AZURE_CHAT_MODEL_NODE, PAYI_CRED, "az-key-test", "Pay-i Azure OpenAI Chat Model"
        )
        self.assertEqual(result["type"], "n8n-nodes-payi.lmChatPayiAzure")
        self.assertEqual(result["name"], "Pay-i Azure OpenAI Chat Model")
        self.assertEqual(result["parameters"]["deploymentName"], "gpt-4o")
        self.assertEqual(result["parameters"]["apiVersion"], "2024-06-01")
        self.assertNotIn("providerApiKey", result["parameters"])

    def test_options_preserved(self):
        result = migrate.build_payi_chat_model_azure_node(
            AZURE_CHAT_MODEL_NODE, PAYI_CRED, "az-key", "Test"
        )
        opts = result["parameters"]["options"]
        self.assertEqual(opts["temperature"], 0.5)
        self.assertEqual(opts["maxTokens"], 2048)

    def test_tracking_defaults(self):
        result = migrate.build_payi_chat_model_azure_node(
            AZURE_CHAT_MODEL_NODE, PAYI_CRED, "az-key", "Test"
        )
        self.assertEqual(result["parameters"]["useCaseName"], "={{ $workflow.name.replaceAll(' ', '-') }}")
        self.assertEqual(result["parameters"]["useCaseId"], "={{ 'azure/' + $parameter.deploymentName + '/' + $execution.id }}")
        self.assertEqual(result["parameters"]["useCaseStep"], "={{ $node.name }}")

    def test_no_plaintext_provider_key(self):
        """providerApiKey should NOT be in parameters — credentials are passed through."""
        result = migrate.build_payi_chat_model_azure_node(
            AZURE_CHAT_MODEL_NODE, PAYI_CRED, "az-dict-key", "Test"
        )
        self.assertNotIn("providerApiKey", result["parameters"])

    def test_resource_locator_model(self):
        node = copy.deepcopy(AZURE_CHAT_MODEL_NODE)
        node["parameters"]["model"] = {"mode": "list", "value": "gpt-4-turbo"}
        result = migrate.build_payi_chat_model_azure_node(node, PAYI_CRED, "k", "Test")
        self.assertEqual(result["parameters"]["deploymentName"], "gpt-4-turbo")

    def test_timeout_and_max_retries_preserved(self):
        """timeout and maxRetries should be extracted from native options."""
        node = copy.deepcopy(AZURE_CHAT_MODEL_NODE)
        node["parameters"]["options"]["timeout"] = 30000
        node["parameters"]["options"]["maxRetries"] = 3
        result = migrate.build_payi_chat_model_azure_node(node, PAYI_CRED, "k", "Test")
        opts = result["parameters"]["options"]
        self.assertEqual(opts["timeout"], 30000)
        self.assertEqual(opts["maxRetries"], 3)


# ── Tests: build_payi_chat_model_bedrock_node ────────────────────────────────

BEDROCK_CHAT_MODEL_NODE = {
    "id": "bedrock-1",
    "name": "AWS Bedrock Chat Model",
    "type": "@n8n/n8n-nodes-langchain.lmChatAwsBedrock",
    "typeVersion": 1,
    "position": [500, 200],
    "parameters": {
        "model": "anthropic.claude-3-sonnet-20240229-v1:0",
        "options": {"temperature": 0.7, "maxTokens": 4096},
    },
}


class TestBuildPayiChatModelBedrockNode(unittest.TestCase):
    def test_basic_fields(self):
        result = migrate.build_payi_chat_model_bedrock_node(
            BEDROCK_CHAT_MODEL_NODE, PAYI_CRED, "", "Pay-i Bedrock Chat Model"
        )
        self.assertEqual(result["type"], "n8n-nodes-payi.lmChatPayiBedrock")
        self.assertEqual(result["parameters"]["model"], "anthropic.claude-3-sonnet-20240229-v1:0")
        self.assertEqual(result["parameters"]["region"], "us-east-1")
        # No plaintext AWS credentials in parameters — they come from the aws credential
        self.assertNotIn("awsAccessKeyId", result["parameters"])
        self.assertNotIn("awsSecretAccessKey", result["parameters"])

    def test_options_preserved(self):
        result = migrate.build_payi_chat_model_bedrock_node(
            BEDROCK_CHAT_MODEL_NODE, PAYI_CRED, "", "Test"
        )
        self.assertEqual(result["parameters"]["options"]["temperature"], 0.7)
        self.assertEqual(result["parameters"]["options"]["maxTokens"], 4096)

    def test_native_aws_credential_passthrough(self):
        """AWS credential from original node should be passed through."""
        node = copy.deepcopy(BEDROCK_CHAT_MODEL_NODE)
        node["credentials"] = {"aws": {"id": "aws-cred-1", "name": "AWS account"}}
        result = migrate.build_payi_chat_model_bedrock_node(
            node, PAYI_CRED, "", "Test"
        )
        self.assertIn("aws", result["credentials"])
        self.assertEqual(result["credentials"]["aws"]["id"], "aws-cred-1")


# ── Tests: build_payi_proxy_anthropic_node ───────────────────────────────────

ANTHROPIC_APP_NODE = {
    "id": "anth-app-1",
    "name": "Anthropic",
    "type": "@n8n/n8n-nodes-langchain.anthropic",
    "typeVersion": 1,
    "position": [300, 400],
    "parameters": {
        "model": {"mode": "list", "value": "claude-sonnet-4-20250514"},
        "text": "Analyze this document for key themes.",
    },
}


class TestBuildPayiProxyAnthropicNode(unittest.TestCase):
    def test_basic_fields(self):
        result = migrate.build_payi_proxy_anthropic_node(
            ANTHROPIC_APP_NODE, PAYI_CRED, "sk-ant-test", "Pay-i Proxy (Anthropic)"
        )
        self.assertEqual(result["type"], "n8n-nodes-payi.payi")
        self.assertEqual(result["parameters"]["provider"], "anthropic")
        self.assertEqual(result["parameters"]["model"], "claude-sonnet-4-20250514")
        # providerApiKey is still used in proxy nodes (they don't use dual credentials yet)
        self.assertEqual(result["parameters"]["providerApiKey"], "sk-ant-test")

    def test_messages_from_text(self):
        result = migrate.build_payi_proxy_anthropic_node(
            ANTHROPIC_APP_NODE, PAYI_CRED, "k", "Test"
        )
        import json
        messages = json.loads(result["parameters"]["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("Analyze this document", messages[0]["content"])

    def test_tracking_defaults(self):
        result = migrate.build_payi_proxy_anthropic_node(
            ANTHROPIC_APP_NODE, PAYI_CRED, "k", "Test"
        )
        self.assertEqual(result["parameters"]["useCaseName"], "={{ $workflow.name.replaceAll(' ', '-') }}")
        self.assertEqual(result["parameters"]["useCaseId"], "={{ 'anthropic/' + $parameter.model + '/' + $execution.id }}")
        self.assertEqual(result["parameters"]["useCaseStep"], "={{ $node.name }}")


# ── Tests: credential redirect ───────────────────────────────────────────────

class TestCredentialRedirect(unittest.TestCase):
    def test_openai_redirect_patch(self):
        patch = migrate.build_credential_patch("openAiApi", "https://api.pay-i.com", "pk-test")
        self.assertEqual(patch["data"]["url"], "https://api.pay-i.com/api/v1/proxy/openai/v1")
        # All providers now include Pay-i key as custom header
        self.assertEqual(patch["data"]["headerName"], "xProxy-api-key")
        self.assertEqual(patch["data"]["headerValue"], "pk-test")

    def test_openai_redirect_merges_existing_data(self):
        existing = {"apiKey": "sk-existing-key", "url": "", "headerName": "", "headerValue": ""}
        patch = migrate.build_credential_patch("openAiApi", "https://api.pay-i.com", "pk-test",
                                               existing_data=existing)
        self.assertEqual(patch["data"]["url"], "https://api.pay-i.com/api/v1/proxy/openai/v1")
        self.assertEqual(patch["data"]["apiKey"], "sk-existing-key")
        self.assertEqual(patch["data"]["headerName"], "xProxy-api-key")
        self.assertEqual(patch["data"]["headerValue"], "pk-test")

    def test_anthropic_redirect_patch(self):
        patch = migrate.build_credential_patch("anthropicApi", "https://api.pay-i.com", "pk-test")
        self.assertEqual(patch["data"]["url"], "https://api.pay-i.com/api/v1/proxy/anthropic")
        self.assertEqual(patch["data"]["headerName"], "xProxy-api-key")
        self.assertEqual(patch["data"]["headerValue"], "pk-test")

    def test_anthropic_redirect_merges_existing_data(self):
        existing = {"apiKey": "sk-anth-key", "url": ""}
        patch = migrate.build_credential_patch("anthropicApi", "https://api.pay-i.com", "pk-test",
                                               existing_data=existing)
        self.assertEqual(patch["data"]["url"], "https://api.pay-i.com/api/v1/proxy/anthropic")
        self.assertEqual(patch["data"]["apiKey"], "sk-anth-key")
        self.assertEqual(patch["data"]["headerName"], "xProxy-api-key")

    def test_azure_redirect_patch(self):
        patch = migrate.build_credential_patch("azureOpenAiApi", "https://api.pay-i.com", "pk-test")
        self.assertEqual(patch["data"]["endpoint"], "https://api.pay-i.com/api/v1/proxy/azure.openai")
        self.assertEqual(patch["data"]["headerName"], "xProxy-api-key")
        self.assertEqual(patch["data"]["headerValue"], "pk-test")

    def test_azure_redirect_merges_existing_data(self):
        existing = {"apiKey": "az-key", "resourceName": "my-resource", "apiVersion": "2024-08-01-preview", "endpoint": ""}
        patch = migrate.build_credential_patch("azureOpenAiApi", "https://api.pay-i.com", "pk-test",
                                               existing_data=existing)
        self.assertEqual(patch["data"]["endpoint"], "https://api.pay-i.com/api/v1/proxy/azure.openai")
        self.assertEqual(patch["data"]["apiKey"], "az-key")
        self.assertEqual(patch["data"]["resourceName"], "my-resource")
        self.assertEqual(patch["data"]["apiVersion"], "2024-08-01-preview")

    def test_unsupported_type_returns_empty(self):
        patch = migrate.build_credential_patch("unknownApi", "https://api.pay-i.com", "pk-test")
        self.assertEqual(patch, {})

    def test_trailing_slash_stripped(self):
        patch = migrate.build_credential_patch("openAiApi", "https://api.pay-i.com/", "pk-test")
        self.assertEqual(patch["data"]["url"], "https://api.pay-i.com/api/v1/proxy/openai/v1")


# ── Tests: new node type detection ───────────────────────────────────────────

class TestNewNodeTypeDetection(unittest.TestCase):
    def test_detects_anthropic_app_node(self):
        nodes = [{"name": "Anth", "type": "@n8n/n8n-nodes-langchain.anthropic", "parameters": {}}]
        wf = make_workflow(nodes=nodes)
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["feasible"])
        self.assertEqual(found[0]["replacement"], "proxy_anthropic")

    def test_detects_openai_completion_model(self):
        nodes = [{"name": "GPT", "type": "@n8n/n8n-nodes-langchain.lmOpenAi", "parameters": {}}]
        wf = make_workflow(nodes=nodes)
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["feasible"])
        self.assertEqual(found[0]["replacement"], "chat_model")

    def test_detects_all_new_infeasible_types(self):
        new_types = [
            "@n8n/n8n-nodes-langchain.lmChatGroq",
            "@n8n/n8n-nodes-langchain.lmChatDeepSeek",
            "@n8n/n8n-nodes-langchain.lmChatCohere",
            "@n8n/n8n-nodes-langchain.lmChatXAiGrok",
            "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
            "@n8n/n8n-nodes-langchain.lmChatOllama",
            "@n8n/n8n-nodes-langchain.lmChatVercelAiGateway",
            "@n8n/n8n-nodes-langchain.lmChatGoogleVertex",
            "@n8n/n8n-nodes-langchain.googleGemini",
            "@n8n/n8n-nodes-langchain.embeddingsOpenAi",
            "@n8n/n8n-nodes-langchain.embeddingsCohere",
            "@n8n/n8n-nodes-langchain.embeddingsOllama",
        ]
        nodes = [{"name": f"Node{i}", "type": t, "parameters": {}} for i, t in enumerate(new_types)]
        wf = make_workflow(nodes=nodes)
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), len(new_types))
        # All these are infeasible
        for n in found:
            self.assertFalse(n["feasible"], f"{n['label']} should be infeasible")

    def test_detects_embeddings_nodes(self):
        nodes = [
            {"name": "OAIEmbed", "type": "@n8n/n8n-nodes-langchain.embeddingsOpenAi", "parameters": {}},
            {"name": "AzureEmbed", "type": "@n8n/n8n-nodes-langchain.embeddingsAzureOpenAi", "parameters": {}},
            {"name": "BedrockEmbed", "type": "@n8n/n8n-nodes-langchain.embeddingsAwsBedrock", "parameters": {}},
        ]
        wf = make_workflow(nodes=nodes)
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 3)
        # All embeddings are currently infeasible
        for n in found:
            self.assertFalse(n["feasible"])


# ── Tests: Databricks ────────────────────────────────────────────────────────

DATABRICKS_NODE = {
    "id": "node-dbx",
    "name": "Databricks",
    "type": "n8n-nodes-databricks.databricks",
    "typeVersion": 1,
    "position": [500, 400],
    "parameters": {
        "endpoint": "my-llm-endpoint",
        "options": {
            "temperature": 0.8,
            "maxTokens": 4096,
            "topP": 0.95,
        },
    },
    "credentials": {
        "databricks": {"id": "dbx-cred-1", "name": "Databricks Workspace"},
    },
}

DATABRICKS_CHAT_MODEL_NODE = {
    "id": "node-dbx-chat",
    "name": "Databricks Chat Model",
    "type": "n8n-nodes-databricks.lmChatDatabricks",
    "typeVersion": 1,
    "position": [550, 400],
    "parameters": {
        "model": "databricks-gpt-5-4",
        "options": {
            "temperature": 0.7,
        },
    },
    "credentials": {
        "databricks": {"id": "dbx-cred-3", "name": "Databricks Chat"},
    },
}

DATABRICKS_AI_AGENT_NODE = {
    "id": "node-dbx-agent",
    "name": "Databricks AI Agent",
    "type": "n8n-nodes-databricks.databricksAiAgent",
    "typeVersion": 1,
    "position": [600, 400],
    "parameters": {
        "model": "databricks-meta-llama-3-3-70b-instruct",
        "options": {},
    },
    "credentials": {
        "databricks": {"id": "dbx-cred-2", "name": "Databricks Agent"},
    },
}


class TestDatabricksDetection(unittest.TestCase):
    def test_databricks_nodes_are_feasible(self):
        nodes = [
            {"name": "Databricks", "type": "n8n-nodes-databricks.databricks", "parameters": {}},
            {"name": "Databricks Chat Model", "type": "n8n-nodes-databricks.lmChatDatabricks", "parameters": {}},
            {"name": "Databricks Agent", "type": "n8n-nodes-databricks.databricksAiAgent", "parameters": {}},
        ]
        wf = make_workflow(nodes=nodes)
        found = migrate.find_llm_nodes([wf])
        self.assertEqual(len(found), 3)
        self.assertTrue(all(n["feasible"] for n in found))
        self.assertTrue(all(n["replacement"] == "chat_model_databricks" for n in found))


class TestBuildPayiChatModelDatabricksNode(unittest.TestCase):
    def test_basic_fields(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-test-token", "Pay-i Databricks Chat Model"
        )
        self.assertEqual(result["type"], "n8n-nodes-payi.lmChatPayiDatabricks")
        self.assertEqual(result["name"], "Pay-i Databricks Chat Model")
        self.assertEqual(result["id"], "node-dbx")
        self.assertEqual(result["position"], [500, 400])
        self.assertEqual(result["typeVersion"], 1)

    def test_endpoint_extracted(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        self.assertEqual(result["parameters"]["endpointName"], "my-llm-endpoint")

    def test_endpoint_from_model_field(self):
        """When the community node uses 'model' instead of 'endpoint'."""
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_AI_AGENT_NODE, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        self.assertEqual(result["parameters"]["endpointName"], "databricks-meta-llama-3-3-70b-instruct")

    def test_options_preserved(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        opts = result["parameters"]["options"]
        self.assertEqual(opts["temperature"], 0.8)
        self.assertEqual(opts["maxTokens"], 4096)
        self.assertEqual(opts["topP"], 0.95)

    def test_unsupported_options_excluded(self):
        node = copy.deepcopy(DATABRICKS_NODE)
        node["parameters"]["options"]["unknownOption"] = "bar"
        result = migrate.build_payi_chat_model_databricks_node(
            node, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        self.assertNotIn("unknownOption", result["parameters"]["options"])

    def test_credential_passthrough(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        self.assertIn("databricks", result["credentials"])
        self.assertEqual(result["credentials"]["databricks"]["id"], "dbx-cred-1")
        self.assertEqual(result["credentials"]["databricks"]["name"], "Databricks Workspace")

    def test_payi_credential_reference(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        cred_ref = result["credentials"]["payiApi"]
        self.assertEqual(cred_ref["id"], "cred-123")
        self.assertEqual(cred_ref["name"], "Pay-i API")

    def test_no_plaintext_provider_key(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-my-token", "Pay-i Databricks Chat Model"
        )
        self.assertNotIn("providerApiKey", result["parameters"])
        self.assertNotIn("accessToken", result["parameters"])

    def test_cloud_provider_defaults_to_aws(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        self.assertEqual(result["parameters"]["cloudProvider"], "aws")

    def test_tracking_defaults(self):
        result = migrate.build_payi_chat_model_databricks_node(
            DATABRICKS_NODE, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        params = result["parameters"]
        self.assertIn("useCaseName", params)
        self.assertIn("useCaseId", params)
        self.assertIn("useCaseStep", params)
        self.assertIn("databricks/", params["useCaseId"])

    def test_resource_locator_model(self):
        """Handle n8n 2.x resourceLocator format for endpoint field."""
        node = copy.deepcopy(DATABRICKS_NODE)
        node["parameters"]["endpoint"] = {"__rl": True, "value": "my-fancy-endpoint", "mode": "string"}
        result = migrate.build_payi_chat_model_databricks_node(
            node, PAYI_CRED, "dapi-test", "Pay-i Databricks Chat Model"
        )
        self.assertEqual(result["parameters"]["endpointName"], "my-fancy-endpoint")


if __name__ == "__main__":
    unittest.main()
