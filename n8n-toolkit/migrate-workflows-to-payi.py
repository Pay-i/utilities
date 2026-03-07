#!/usr/bin/env python3
"""
migrate-workflows-to-payi.py

Scans n8n workflows for native LLM nodes (OpenAI, Anthropic, etc.)
and replaces them with Pay-i Proxy or Pay-i Chat Model nodes.

Requires: Python 3.8+, no pip dependencies (stdlib only).

Environment variables:
  N8N_BASE_URL   - Your n8n instance (e.g. http://localhost:5678)
  N8N_API_KEY    - n8n API key (Settings > API > Create API Key)
  PAYI_BASE_URL  - Pay-i instance (e.g. https://api.yourcompany.pay-i.com)
  PAYI_API_KEY   - Your Pay-i API key

  Provider API keys are NOT needed for Chat Model migration — the existing
  credentials on each node are automatically passed through to the Pay-i node.

Usage:
  python3 migrate-workflows-to-payi.py [OPTIONS]

Options:
  --dry-run       Show what would change without modifying anything
  --auto-yes      Skip per-node confirmation (still prompts for API keys)
  --workflow ID   Migrate only the specified workflow
  --verbose       Show detailed API request/response logging
"""

import argparse
import copy
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request

# ── ANSI Colors ──────────────────────────────────────────────────────────────

_USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    return _c("1", text)


def dim(text: str) -> str:
    return _c("2", text)


def green(text: str) -> str:
    return _c("32", text)


def yellow(text: str) -> str:
    return _c("33", text)


def red(text: str) -> str:
    return _c("31", text)


def cyan(text: str) -> str:
    return _c("36", text)


# ── Constants ────────────────────────────────────────────────────────────────

# Node type → {provider, replacement_type, feasible, skip_reason}
NATIVE_LLM_NODES = {
    # ── OpenAI ──────────────────────────────────────────────────────────────
    "@n8n/n8n-nodes-langchain.lmChatOpenAi": {
        "provider": "openai",
        "replacement": "chat_model",
        "feasible": True,
        "label": "OpenAI Chat Model (LangChain)",
    },
    "@n8n/n8n-nodes-langchain.openai": {
        "provider": "openai",
        "replacement": "proxy",
        "feasible": True,
        "label": "OpenAI (App Node — 16 actions)",
    },
    "@n8n/n8n-nodes-langchain.lmOpenAi": {
        "provider": "openai",
        "replacement": "chat_model",
        "feasible": True,
        "label": "OpenAI Completion Model",
    },
    "@n8n/n8n-nodes-langchain.embeddingsOpenAi": {
        "provider": "openai",
        "replacement": None,
        "feasible": False,
        "label": "OpenAI Embeddings",
        "skip_reason": "Embeddings migration not yet implemented",
    },
    # ── Anthropic ───────────────────────────────────────────────────────────
    "@n8n/n8n-nodes-langchain.lmChatAnthropic": {
        "provider": "anthropic",
        "replacement": "chat_model_anthropic",
        "feasible": True,
        "label": "Anthropic Chat Model (LangChain)",
    },
    "@n8n/n8n-nodes-langchain.anthropic": {
        "provider": "anthropic",
        "replacement": "proxy_anthropic",
        "feasible": True,
        "label": "Anthropic (App Node — 10 actions)",
    },
    # ── Azure OpenAI ────────────────────────────────────────────────────────
    "@n8n/n8n-nodes-langchain.lmChatAzureOpenAi": {
        "provider": "azureOpenai",
        "replacement": "chat_model_azure",
        "feasible": True,
        "label": "Azure OpenAI Chat Model (LangChain)",
    },
    "@n8n/n8n-nodes-langchain.embeddingsAzureOpenAi": {
        "provider": "azureOpenai",
        "replacement": None,
        "feasible": False,
        "label": "Azure OpenAI Embeddings",
        "skip_reason": "Embeddings migration not yet implemented",
    },
    # ── AWS Bedrock ─────────────────────────────────────────────────────────
    "@n8n/n8n-nodes-langchain.lmChatAwsBedrock": {
        "provider": "bedrock",
        "replacement": "chat_model_bedrock",
        "feasible": True,
        "label": "AWS Bedrock Chat Model (LangChain)",
    },
    "@n8n/n8n-nodes-langchain.embeddingsAwsBedrock": {
        "provider": "bedrock",
        "replacement": None,
        "feasible": False,
        "label": "AWS Bedrock Embeddings",
        "skip_reason": "Embeddings migration not yet implemented",
    },
    # ── Google ──────────────────────────────────────────────────────────────
    "@n8n/n8n-nodes-langchain.lmChatGoogleGemini": {
        "provider": "google",
        "replacement": None,
        "feasible": False,
        "label": "Google Gemini Chat Model",
        "skip_reason": "Google proxy route not yet available in Pay-i",
    },
    "@n8n/n8n-nodes-langchain.lmChatGoogleVertex": {
        "provider": "google",
        "replacement": None,
        "feasible": False,
        "label": "Google Vertex Chat Model",
        "skip_reason": "Google proxy route not yet available in Pay-i",
    },
    "@n8n/n8n-nodes-langchain.googleGemini": {
        "provider": "google",
        "replacement": None,
        "feasible": False,
        "label": "Google Gemini (App Node)",
        "skip_reason": "Google proxy route not yet available in Pay-i",
    },
    "@n8n/n8n-nodes-langchain.embeddingsGoogleGemini": {
        "provider": "google",
        "replacement": None,
        "feasible": False,
        "label": "Google Gemini Embeddings",
        "skip_reason": "Google proxy route not yet available in Pay-i",
    },
    "@n8n/n8n-nodes-langchain.embeddingsGoogleVertex": {
        "provider": "google",
        "replacement": None,
        "feasible": False,
        "label": "Google Vertex Embeddings",
        "skip_reason": "Google proxy route not yet available in Pay-i",
    },
    # ── Other providers (detected but not yet migratable) ───────────────────
    "@n8n/n8n-nodes-langchain.lmChatMistralCloud": {
        "provider": "mistral",
        "replacement": None,
        "feasible": False,
        "label": "Mistral Chat Model",
        "skip_reason": "Mistral is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.embeddingsMistralCloud": {
        "provider": "mistral",
        "replacement": None,
        "feasible": False,
        "label": "Mistral Embeddings",
        "skip_reason": "Mistral is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.lmChatGroq": {
        "provider": "groq",
        "replacement": None,
        "feasible": False,
        "label": "Groq Chat Model",
        "skip_reason": "Groq is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.lmChatDeepSeek": {
        "provider": "deepseek",
        "replacement": None,
        "feasible": False,
        "label": "DeepSeek Chat Model",
        "skip_reason": "DeepSeek is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.lmChatCohere": {
        "provider": "cohere",
        "replacement": None,
        "feasible": False,
        "label": "Cohere Chat Model",
        "skip_reason": "Cohere is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.embeddingsCohere": {
        "provider": "cohere",
        "replacement": None,
        "feasible": False,
        "label": "Cohere Embeddings",
        "skip_reason": "Cohere is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.lmChatXAiGrok": {
        "provider": "xai",
        "replacement": None,
        "feasible": False,
        "label": "xAI Grok Chat Model",
        "skip_reason": "xAI is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.lmChatOpenRouter": {
        "provider": "openrouter",
        "replacement": None,
        "feasible": False,
        "label": "OpenRouter Chat Model",
        "skip_reason": "OpenRouter is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.lmChatOllama": {
        "provider": "ollama",
        "replacement": None,
        "feasible": False,
        "label": "Ollama Chat Model",
        "skip_reason": "Ollama is a local provider — no proxy needed",
    },
    "@n8n/n8n-nodes-langchain.lmOllama": {
        "provider": "ollama",
        "replacement": None,
        "feasible": False,
        "label": "Ollama Completion Model",
        "skip_reason": "Ollama is a local provider — no proxy needed",
    },
    "@n8n/n8n-nodes-langchain.embeddingsOllama": {
        "provider": "ollama",
        "replacement": None,
        "feasible": False,
        "label": "Ollama Embeddings",
        "skip_reason": "Ollama is a local provider — no proxy needed",
    },
    "@n8n/n8n-nodes-langchain.lmChatVercelAiGateway": {
        "provider": "vercel",
        "replacement": None,
        "feasible": False,
        "label": "Vercel AI Gateway Chat Model",
        "skip_reason": "Vercel AI Gateway is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.lmOpenHuggingFaceInference": {
        "provider": "huggingface",
        "replacement": None,
        "feasible": False,
        "label": "HuggingFace Inference Model",
        "skip_reason": "HuggingFace is not a supported Pay-i provider",
    },
    "@n8n/n8n-nodes-langchain.embeddingsHuggingFaceInference": {
        "provider": "huggingface",
        "replacement": None,
        "feasible": False,
        "label": "HuggingFace Embeddings",
        "skip_reason": "HuggingFace is not a supported Pay-i provider",
    },
    # ── Databricks / AgentBricks ─────────────────────────────────────────────
    # Community node: n8n-nodes-databricks
    "n8n-nodes-databricks.databricks": {
        "provider": "databricks",
        "replacement": "chat_model_databricks",
        "feasible": True,
        "label": "Databricks (Community Node)",
    },
    "n8n-nodes-databricks.lmChatDatabricks": {
        "provider": "databricks",
        "replacement": "chat_model_databricks",
        "feasible": True,
        "label": "Databricks Chat Model (Community Node)",
    },
    "n8n-nodes-databricks.databricksAiAgent": {
        "provider": "databricks",
        "replacement": "chat_model_databricks",
        "feasible": True,
        "label": "Databricks AI Agent (Community Node)",
    },
}

# Provider → env var name for API key
PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azureOpenai": "AZURE_OPENAI_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "databricks": "DATABRICKS_TOKEN",
}

# Provider credential config — used by the interactive setup flow.
# Each provider has a list of fields the user needs to supply.
PROVIDER_CREDENTIAL_CONFIG = {
    "openai": {
        "label": "OpenAI",
        "fields": [
            {"key": "apiKey", "prompt": "OpenAI API Key", "env": "OPENAI_API_KEY", "secret": True},
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "fields": [
            {"key": "apiKey", "prompt": "Anthropic API Key", "env": "ANTHROPIC_API_KEY", "secret": True},
        ],
    },
    "azureOpenai": {
        "label": "Azure OpenAI",
        "fields": [
            {"key": "apiKey", "prompt": "Azure OpenAI API Key", "env": "AZURE_OPENAI_API_KEY", "secret": True},
        ],
    },
    "bedrock": {
        "label": "AWS Bedrock",
        "fields": [
            {"key": "awsAccessKeyId", "prompt": "AWS Access Key ID", "env": "AWS_ACCESS_KEY_ID", "secret": True},
            {"key": "awsSecretAccessKey", "prompt": "AWS Secret Access Key", "env": "AWS_SECRET_ACCESS_KEY", "secret": True},
            {"key": "awsRegion", "prompt": "AWS Region", "env": "AWS_REGION", "default": "us-east-1", "secret": False},
        ],
    },
    "databricks": {
        "label": "Databricks",
        "fields": [
            {"key": "token", "prompt": "Databricks Personal Access Token", "env": "DATABRICKS_TOKEN", "secret": True},
            {"key": "host", "prompt": "Databricks Workspace URL", "env": "DATABRICKS_WORKSPACE_URL", "secret": False},
        ],
    },
}

# Fields accepted by PUT /api/v1/workflows/{id}.
# Using an allowlist is safer than a denylist — n8n adds new read-only fields
# across versions and the PUT endpoint rejects anything it doesn't recognize.
WORKFLOW_PUT_ALLOWED_FIELDS = {
    "name", "nodes", "connections", "settings",
}


# ── API Client ───────────────────────────────────────────────────────────────

class N8nApiClient:
    def __init__(self, base_url: str, api_key: str, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.verbose = verbose

    def _request(self, method: str, path: str, body: dict = None, quiet: bool = False) -> dict:
        url = f"{self.base_url}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-N8N-API-KEY", self.api_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        if self.verbose:
            print(f"  {dim('[API]')} {method} {url}")
            if body:
                redacted = _redact_dict(body)
                print(f"  {dim('[API]')} Body: {json.dumps(redacted, indent=2)[:500]}")

        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read().decode("utf-8")
                if self.verbose:
                    preview = resp_body[:500]
                    if len(resp_body) > 500:
                        preview += "...(truncated)"
                    print(f"  {dim('[API]')} {resp.status} OK — {preview}")
                return json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if not quiet:
                print(f"  {red('ERROR')}: {method} {path} -> HTTP {e.code}")
                print(f"  {err_body[:500]}")
            raise SystemExit(1)

    def get(self, path: str, quiet: bool = False) -> dict:
        return self._request("GET", path, quiet=quiet)

    def post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body)

    def put(self, path: str, body: dict) -> dict:
        return self._request("PUT", path, body)

    def patch(self, path: str, body: dict) -> dict:
        return self._request("PATCH", path, body)


def _redact_dict(d: dict) -> dict:
    """Shallow copy with sensitive-looking values masked."""
    sensitive = {"apikey", "api_key", "providerApiKey", "secret", "password", "token", "headervalue"}
    out = {}
    for k, v in d.items():
        if k.lower().replace("-", "").replace("_", "") in {s.lower().replace("_", "") for s in sensitive}:
            out[k] = "****"
        elif isinstance(v, dict):
            out[k] = _redact_dict(v)
        else:
            out[k] = v
    return out


# ── Interactive Prompts ───────────────────────────────────────────────────────

def _is_interactive() -> bool:
    """Return True if stdin is a terminal (not piped)."""
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def prompt_value(label: str, env_var: str = None, default: str = None, secret: bool = False) -> str:
    """Prompt the user for a value, with optional env-var default."""
    env_val = os.environ.get(env_var, "").strip() if env_var else ""
    if env_val:
        masked = env_val[:4] + "****" if secret and len(env_val) > 4 else env_val
        print(f"  {green('Found')} {env_var} in environment ({masked})")
        return env_val

    hint = f" [{default}]" if default else ""
    if secret:
        val = getpass.getpass(f"  {label}{hint}: ").strip()
    else:
        val = input(f"  {label}{hint}: ").strip()

    return val if val else (default or "")


def setup_connection_details(args) -> dict:
    """Interactively gather connection details, using env vars as defaults."""
    print(bold("  Connection Setup"))
    print()

    n8n_base = prompt_value("n8n Instance URL", "N8N_BASE_URL", "http://localhost:5678")
    if not n8n_base:
        print(f"  {red('ERROR')}: n8n URL is required")
        raise SystemExit(1)

    n8n_key = prompt_value("n8n API Key", "N8N_API_KEY", secret=True)
    if not n8n_key:
        print(f"  {red('ERROR')}: n8n API key is required")
        raise SystemExit(1)

    print()
    payi_base = prompt_value("Pay-i Base URL", "PAYI_BASE_URL", "https://api.pay-i.com")
    if not payi_base:
        print(f"  {red('ERROR')}: Pay-i URL is required")
        raise SystemExit(1)

    payi_key = prompt_value("Pay-i API Key", "PAYI_API_KEY", secret=True)
    if not payi_key:
        print(f"  {red('ERROR')}: Pay-i API key is required")
        raise SystemExit(1)

    return {
        "n8n_base": n8n_base.rstrip("/"),
        "n8n_key": n8n_key,
        "payi_base": payi_base.rstrip("/"),
        "payi_key": payi_key,
    }


def collect_provider_credentials(found_nodes: list) -> dict:
    """Interactively collect credentials for each detected provider.

    Returns {provider: cred_value} where cred_value is either a string (API key)
    or a dict (for providers needing multiple fields like Bedrock).
    """
    needed = set()
    for n in found_nodes:
        if n["feasible"]:
            needed.add(n["provider"])

    if not needed:
        return {}

    print(bold("  Provider API Keys"))
    print()

    creds = {}
    for provider in sorted(needed):
        config = PROVIDER_CREDENTIAL_CONFIG.get(provider)
        if not config:
            continue

        fields = config["fields"]
        if len(fields) == 1:
            # Simple single-key provider
            f = fields[0]
            val = prompt_value(f["prompt"], f.get("env"), f.get("default"), f.get("secret", True))
            if val:
                creds[provider] = val
            else:
                print(f"  {yellow('WARNING')}: No key for {config['label']} — those nodes will be skipped")
        else:
            # Multi-field provider (e.g. Bedrock)
            print(f"  {bold(config['label'])} credentials:")
            provider_creds = {}
            missing = False
            for f in fields:
                val = prompt_value(f"  {f['prompt']}", f.get("env"), f.get("default"), f.get("secret", True))
                if val:
                    provider_creds[f["key"]] = val
                elif not f.get("default"):
                    missing = True
            if missing:
                print(f"  {yellow('WARNING')}: Incomplete credentials for {config['label']} — those nodes will be skipped")
            else:
                creds[provider] = provider_creds

    return creds


# ── Node Detection ───────────────────────────────────────────────────────────

def find_llm_nodes(workflows: list) -> list:
    """Scan workflows and return a list of found LLM node descriptors."""
    results = []
    for wf in workflows:
        wf_id = wf.get("id", "?")
        wf_name = wf.get("name", "Untitled")
        for node in wf.get("nodes", []):
            node_type = node.get("type", "")
            if node_type in NATIVE_LLM_NODES:
                info = NATIVE_LLM_NODES[node_type]
                results.append({
                    "workflow_id": wf_id,
                    "workflow_name": wf_name,
                    "node": node,
                    "node_type": node_type,
                    **info,
                })
    return results


# Databricks URL patterns matched in HTTP Request node parameters
_DATABRICKS_URL_PATTERNS = [
    ".databricks.com/serving-endpoints/",
    ".databricks.com/api/2.0/serving-endpoints/",
    ".databricks.com/api/v1/",
    ".databricksapps.com/",
]


def find_databricks_nodes(workflows: list) -> list:
    """Detect Databricks/AgentBricks nodes not already in NATIVE_LLM_NODES.

    Two detection patterns:
      1. Any node whose type contains 'databricks' (case-insensitive) that
         isn't already in NATIVE_LLM_NODES (those are caught by find_llm_nodes).
      2. HTTP Request nodes whose URL parameters target Databricks endpoints.

    Returns a list of descriptors with workflow context and detection reason.
    """
    results = []
    for wf in workflows:
        wf_id = wf.get("id", "?")
        wf_name = wf.get("name", "Untitled")
        for node in wf.get("nodes", []):
            node_type = node.get("type", "")
            node_name = node.get("name", "?")
            pos = node.get("position", [0, 0])

            # Pattern 1: Community node with 'databricks' in type
            if "databricks" in node_type.lower() and node_type not in NATIVE_LLM_NODES:
                results.append({
                    "workflow_id": wf_id,
                    "workflow_name": wf_name,
                    "node_name": node_name,
                    "node_type": node_type,
                    "position": pos,
                    "reason": "Databricks community node",
                })
                continue

            # Pattern 2: HTTP Request nodes calling Databricks URLs
            if node_type in (
                "n8n-nodes-base.httpRequest",
                "@n8n/n8n-nodes-langchain.httpRequest",
            ):
                params = node.get("parameters", {})
                url = params.get("url", "")
                # Also check if URL is in an expression
                if isinstance(url, dict):
                    url = str(url.get("value", ""))
                url_lower = url.lower()
                for pattern in _DATABRICKS_URL_PATTERNS:
                    if pattern in url_lower:
                        results.append({
                            "workflow_id": wf_id,
                            "workflow_name": wf_name,
                            "node_name": node_name,
                            "node_type": node_type,
                            "position": pos,
                            "reason": f"HTTP Request to Databricks ({pattern.strip('/')})",
                        })
                        break

    return results


# ── Credential Management ────────────────────────────────────────────────────

def ensure_payi_credential(client: N8nApiClient, payi_api_key: str, payi_base_url: str) -> dict:
    """Find or create a payiApi credential in n8n. Returns {id, name}."""
    print(f"  Checking for Pay-i credential in n8n...")

    creds_resp = client.get("/api/v1/credentials")
    creds = creds_resp.get("data", creds_resp) if isinstance(creds_resp, dict) else creds_resp
    if isinstance(creds, dict) and "data" not in creds:
        # Some n8n versions return a list directly
        creds = [creds_resp] if creds_resp.get("type") else []

    for c in creds:
        if c.get("type") == "payiApi":
            print(f'  {green("Found")} Pay-i credential: "{c["name"]}" (ID: {c["id"]})')
            return {"id": c["id"], "name": c["name"]}

    print(f"  No Pay-i credential found — creating one...")
    new_cred = client.post("/api/v1/credentials", {
        "name": "Pay-i API",
        "type": "payiApi",
        "data": {
            "apiKey": payi_api_key,
            "baseUrl": payi_base_url,
        },
    })
    cred_id = new_cred.get("id", "?")
    print(f'  {green("Created")} Pay-i credential: "Pay-i API" (ID: {cred_id})')
    return {"id": cred_id, "name": "Pay-i API"}


# ── Provider API Key Collection ──────────────────────────────────────────────

def collect_provider_keys(found_nodes: list) -> dict:
    """Legacy wrapper — delegates to collect_provider_credentials."""
    return collect_provider_credentials(found_nodes)


# ── Node Builders ────────────────────────────────────────────────────────────

def _extract_native_credential(original: dict, cred_type: str) -> dict:
    """Extract an existing credential reference from the original node.

    Returns a dict like {"id": "xxx", "name": "OpenAI account"} or {} if not found.
    """
    creds = original.get("credentials", {}) or {}
    for key, val in creds.items():
        if key == cred_type and isinstance(val, dict) and val.get("id"):
            return val
    return {}


# Maps replacement type → native credential key that the Pay-i node should inherit.
NATIVE_CREDENTIAL_KEY = {
    "chat_model": "openAiApi",
    "chat_model_anthropic": "anthropicApi",
    "chat_model_azure": "azureOpenAiApi",
    "chat_model_bedrock": "aws",
    "chat_model_databricks": "databricks",
    "proxy": "openAiApi",
    "proxy_anthropic": "anthropicApi",
}


def build_payi_chat_model_node(
    original: dict,
    payi_cred: dict,
    provider_key: str,
    new_name: str,
) -> dict:
    """Build a Pay-i Chat Model node from a native OpenAI LangChain chat model."""
    params = original.get("parameters", {})

    # Extract model — newer n8n versions (2.x) store this as a resourceLocator
    # object {"mode": "list", "value": "gpt-4o"} instead of a plain string.
    model = params.get("model", "gpt-4o")
    if isinstance(model, dict):
        model = model.get("value", "gpt-4o")

    # Extract options from native node
    native_options = params.get("options", {})
    options = {}
    for key in ("temperature", "maxTokens", "topP", "frequencyPenalty", "presencePenalty", "timeout", "maxRetries"):
        if key in native_options:
            options[key] = native_options[key]

    # Pass through the existing OpenAI credential — no need to re-enter API keys
    native_cred = _extract_native_credential(original, "openAiApi")

    credentials = {
        "payiApi": {
            "id": str(payi_cred["id"]),
            "name": payi_cred["name"],
        },
    }
    if native_cred:
        credentials["openAiApi"] = native_cred

    new_node = {
        "id": original.get("id", ""),
        "name": new_name,
        "type": "n8n-nodes-payi.lmChatPayi",
        "typeVersion": 1,
        "position": original.get("position", [0, 0]),
        "parameters": {
            "model": model,
            "options": options,
            # Tracking defaults
            "useCaseName": "={{ $workflow.name.replaceAll(' ', '-') }}",
            "useCaseId": "={{ 'openai/' + $parameter.model + '/' + $execution.id }}",
            "useCaseStep": "={{ $node.name }}",
        },
        "credentials": credentials,
    }
    return new_node


def build_payi_chat_model_anthropic_node(
    original: dict,
    payi_cred: dict,
    provider_key: str,
    new_name: str,
) -> dict:
    """Build a Pay-i Anthropic Chat Model node from a native Anthropic LangChain chat model."""
    params = original.get("parameters", {})

    # Native n8n Anthropic node uses "modelName" in some versions, "model" in others
    model = params.get("model", params.get("modelName", ""))
    if isinstance(model, dict):
        model = model.get("value", "")

    native_options = params.get("options", {})
    options = {}
    for key in ("maxTokensToSample", "temperature", "topK", "topP", "thinking", "thinkingBudget"):
        if key in native_options:
            options[key] = native_options[key]

    # Pass through the existing Anthropic credential
    native_cred = _extract_native_credential(original, "anthropicApi")

    credentials = {
        "payiApi": {
            "id": str(payi_cred["id"]),
            "name": payi_cred["name"],
        },
    }
    if native_cred:
        credentials["anthropicApi"] = native_cred

    new_node = {
        "id": original.get("id", ""),
        "name": new_name,
        "type": "n8n-nodes-payi.lmChatPayiAnthropic",
        "typeVersion": 1,
        "position": original.get("position", [0, 0]),
        "parameters": {
            "model": model,
            "options": options,
            "useCaseName": "={{ $workflow.name.replaceAll(' ', '-') }}",
            "useCaseId": "={{ 'anthropic/' + $parameter.model + '/' + $execution.id }}",
            "useCaseStep": "={{ $node.name }}",
        },
        "credentials": credentials,
    }
    return new_node


def build_payi_chat_model_azure_node(
    original: dict,
    payi_cred: dict,
    provider_key: str,
    new_name: str,
) -> dict:
    """Build a Pay-i Azure OpenAI Chat Model node from a native Azure OpenAI LangChain chat model."""
    params = original.get("parameters", {})

    # Azure uses deployment name instead of model
    deployment = params.get("model", "")
    if isinstance(deployment, dict):
        deployment = deployment.get("value", "")

    api_version = params.get("apiVersion", "2024-08-01-preview")

    # Extract options
    native_options = params.get("options", {})
    options = {}
    for key in ("temperature", "maxTokens", "topP", "frequencyPenalty", "presencePenalty", "timeout", "maxRetries"):
        if key in native_options:
            options[key] = native_options[key]

    # Pass through the existing Azure OpenAI credential
    native_cred = _extract_native_credential(original, "azureOpenAiApi")

    credentials = {
        "payiApi": {
            "id": str(payi_cred["id"]),
            "name": payi_cred["name"],
        },
    }
    if native_cred:
        credentials["azureOpenAiApi"] = native_cred

    new_node = {
        "id": original.get("id", ""),
        "name": new_name,
        "type": "n8n-nodes-payi.lmChatPayiAzure",
        "typeVersion": 1,
        "position": original.get("position", [0, 0]),
        "parameters": {
            "deploymentName": deployment,
            "apiVersion": api_version,
            "options": options,
            "useCaseName": "={{ $workflow.name.replaceAll(' ', '-') }}",
            "useCaseId": "={{ 'azure/' + $parameter.deploymentName + '/' + $execution.id }}",
            "useCaseStep": "={{ $node.name }}",
        },
        "credentials": credentials,
    }
    return new_node


def build_payi_chat_model_bedrock_node(
    original: dict,
    payi_cred: dict,
    provider_key: str,
    new_name: str,
) -> dict:
    """Build a Pay-i Bedrock Chat Model node from a native AWS Bedrock LangChain chat model."""
    params = original.get("parameters", {})

    model = params.get("model", "")
    if isinstance(model, dict):
        model = model.get("value", "")

    region = params.get("region", "us-east-1")

    native_options = params.get("options", {})
    options = {}
    for key in ("temperature", "maxTokens", "topP"):
        if key in native_options:
            options[key] = native_options[key]

    # Pass through the existing AWS credential
    native_cred = _extract_native_credential(original, "aws")

    credentials = {
        "payiApi": {
            "id": str(payi_cred["id"]),
            "name": payi_cred["name"],
        },
    }
    if native_cred:
        credentials["aws"] = native_cred

    new_node = {
        "id": original.get("id", ""),
        "name": new_name,
        "type": "n8n-nodes-payi.lmChatPayiBedrock",
        "typeVersion": 1,
        "position": original.get("position", [0, 0]),
        "parameters": {
            "model": model,
            "region": region,
            "options": options,
            "useCaseName": "={{ $workflow.name.replaceAll(' ', '-') }}",
            "useCaseId": "={{ 'bedrock/' + $parameter.model + '/' + $execution.id }}",
            "useCaseStep": "={{ $node.name }}",
        },
        "credentials": credentials,
    }
    return new_node


def build_payi_chat_model_databricks_node(
    original: dict,
    payi_cred: dict,
    provider_key: str,
    new_name: str,
) -> dict:
    """Build a Pay-i Databricks Chat Model node from a Databricks community node."""
    params = original.get("parameters", {})

    # Extract endpoint name — community node may use "endpoint", "model", or "endpointName"
    endpoint = params.get("endpoint", params.get("endpointName", params.get("model", "")))
    if isinstance(endpoint, dict):
        endpoint = endpoint.get("value", "")

    # Default cloud provider — we can't reliably detect this from the node params
    # so default to "aws" (most common); user can adjust after migration.
    cloud_provider = "aws"

    native_options = params.get("options", {})
    options = {}
    for key in ("temperature", "maxTokens", "topP", "frequencyPenalty", "presencePenalty"):
        if key in native_options:
            options[key] = native_options[key]

    # Pass through the existing Databricks credential
    native_cred = _extract_native_credential(original, "databricks")

    credentials = {
        "payiApi": {
            "id": str(payi_cred["id"]),
            "name": payi_cred["name"],
        },
    }
    if native_cred:
        credentials["databricks"] = native_cred

    new_node = {
        "id": original.get("id", ""),
        "name": new_name,
        "type": "n8n-nodes-payi.lmChatPayiDatabricks",
        "typeVersion": 1,
        "position": original.get("position", [0, 0]),
        "parameters": {
            "endpointName": endpoint,
            "cloudProvider": cloud_provider,
            "options": options,
            "useCaseName": "={{ $workflow.name.replaceAll(' ', '-') }}",
            "useCaseId": "={{ 'databricks/' + $parameter.endpointName + '/' + $execution.id }}",
            "useCaseStep": "={{ $node.name }}",
        },
        "credentials": credentials,
    }
    return new_node


def build_payi_proxy_anthropic_node(
    original: dict,
    payi_cred: dict,
    provider_key: str,
    new_name: str,
) -> dict:
    """Build a Pay-i Proxy node from a native Anthropic app node."""
    params = original.get("parameters", {})

    model = params.get("model", "claude-sonnet-4-20250514")
    if isinstance(model, dict):
        model = model.get("value", "claude-sonnet-4-20250514")

    # Try to extract the user message content
    text = params.get("text", params.get("prompt", ""))
    if not text:
        text = "Hello!"
    messages = json.dumps([{"role": "user", "content": text}])

    new_node = {
        "id": original.get("id", ""),
        "name": new_name,
        "type": "n8n-nodes-payi.payi",
        "typeVersion": 1,
        "position": original.get("position", [0, 0]),
        "parameters": {
            "provider": "anthropic",
            "providerApiKey": provider_key,
            "model": model,
            "messages": messages,
            # Tracking defaults
            "useCaseName": "={{ $workflow.name.replaceAll(' ', '-') }}",
            "useCaseId": "={{ 'anthropic/' + $parameter.model + '/' + $execution.id }}",
            "useCaseStep": "={{ $node.name }}",
            "includeCostData": True,
            "returnFullResponse": False,
            "debugLogging": False,
        },
        "credentials": {
            "payiApi": {
                "id": str(payi_cred["id"]),
                "name": payi_cred["name"],
            },
        },
    }
    return new_node


# ── Credential Redirect ──────────────────────────────────────────────────────

# Credential types that support URL redirect (base URL swap to Pay-i proxy).
# This is the simplest migration: change the URL field, route ALL actions through Pay-i.
CREDENTIAL_REDIRECT_CONFIG = {
    "openAiApi": {
        "provider": "openai",
        "url_field": "url",
        "proxy_path": "/api/v1/proxy/openai/v1",
        "header_field": "xProxy-api-key",  # Pay-i key sent as custom header alongside Bearer token
    },
    "anthropicApi": {
        "provider": "anthropic",
        "url_field": "url",
        "proxy_path": "/api/v1/proxy/anthropic",
        "header_field": "xProxy-api-key",  # Pay-i key sent as custom header
    },
    "azureOpenAiApi": {
        "provider": "azureOpenai",
        "url_field": "endpoint",
        "proxy_path": "/api/v1/proxy/azure.openai",
        "header_field": "xProxy-api-key",  # Pay-i key sent as custom header
    },
}


def _fetch_credential_data(client, cred_id: str) -> dict:
    """Fetch existing (decrypted) credential data from n8n.

    Uses the ``?includeData=true`` query parameter supported by n8n v1.x+.
    Returns the ``data`` dict if available, or an empty dict on failure.
    """
    try:
        resp = client.get(f"/api/v1/credentials/{cred_id}?includeData=true", quiet=True)
        return resp.get("data", {}) or {}
    except SystemExit:
        return {}


def build_credential_patch(cred_type: str, payi_base_url: str, payi_api_key: str,
                           existing_data: dict = None) -> dict:
    """Build the PATCH body to redirect a credential to Pay-i proxy.

    When *existing_data* is provided (fetched from n8n), the redirect fields are
    merged into the full credential data so n8n's PATCH validation passes.
    Without existing_data, only the redirect fields are returned (may fail on n8n
    versions that require all fields in a PATCH).
    """
    config = CREDENTIAL_REDIRECT_CONFIG.get(cred_type)
    if not config:
        return {}

    base = payi_base_url.rstrip("/")
    proxy_url = f"{base}{config['proxy_path']}"

    # Start from existing data if available, otherwise from scratch
    data = dict(existing_data) if existing_data else {}

    # Apply redirect changes
    data[config["url_field"]] = proxy_url
    if config.get("header_field"):
        data["headerName"] = config["header_field"]
        data["headerValue"] = payi_api_key

    return {"data": data}


def find_redirectable_credentials(client, workflows: list) -> list:
    """Find all credentials used by AI nodes that can be redirected."""
    # Collect credential IDs from detected AI nodes
    cred_ids = set()
    for wf in workflows:
        for node in wf.get("nodes", []):
            node_type = node.get("type", "")
            if node_type in NATIVE_LLM_NODES:
                for cred_key, cred_info in (node.get("credentials", {}) or {}).items():
                    if isinstance(cred_info, dict) and cred_info.get("id"):
                        cred_ids.add((str(cred_info["id"]), cred_key))

    # Fetch credential metadata to get their types
    if not cred_ids:
        return []

    creds_resp = client.get("/api/v1/credentials")
    all_creds = creds_resp.get("data", creds_resp) if isinstance(creds_resp, dict) else creds_resp
    if isinstance(all_creds, dict):
        all_creds = [all_creds]

    by_id = {str(c.get("id")): c for c in all_creds if c.get("id") is not None}

    redirectable = []
    seen = set()
    for cred_id, cred_key in cred_ids:
        if cred_id in seen:
            continue
        seen.add(cred_id)
        cred = by_id.get(cred_id, {})
        cred_type = cred.get("type", "")
        if cred_type in CREDENTIAL_REDIRECT_CONFIG:
            redirectable.append({
                "id": cred_id,
                "name": cred.get("name", "?"),
                "type": cred_type,
                "provider": CREDENTIAL_REDIRECT_CONFIG[cred_type]["provider"],
            })

    return redirectable


def build_payi_proxy_node(
    original: dict,
    payi_cred: dict,
    provider_key: str,
    new_name: str,
) -> dict:
    """Build a Pay-i Proxy node from a native OpenAI app node."""
    params = original.get("parameters", {})

    # The native OpenAI node uses 'model' — newer n8n versions (2.x) store
    # this as a resourceLocator object {"mode": "list", "value": "gpt-4o"}.
    model = params.get("model", "gpt-4o")
    if isinstance(model, dict):
        model = model.get("value", "gpt-4o")

    # Try to extract messages — the native node uses structured fields or prompt
    messages = params.get("messages", params.get("prompt", ""))
    if isinstance(messages, str) and messages.startswith("["):
        pass  # already a JSON array string, keep as-is
    elif isinstance(messages, str) and messages:
        # Convert simple prompt string to messages array
        messages = json.dumps([{"role": "user", "content": messages}])
    elif isinstance(messages, list):
        messages = json.dumps(messages)
    elif isinstance(messages, dict):
        # Some nodes use {values: [{...}]} format
        values = messages.get("values", [])
        converted = []
        for v in values:
            role = v.get("role", "user")
            content = v.get("content", "")
            converted.append({"role": role, "content": content})
        messages = json.dumps(converted) if converted else '[{"role": "user", "content": "Hello!"}]'

    if not messages:
        messages = '[{"role": "user", "content": "Hello!"}]'

    new_node = {
        "id": original.get("id", ""),
        "name": new_name,
        "type": "n8n-nodes-payi.payi",
        "typeVersion": 1,
        "position": original.get("position", [0, 0]),
        "parameters": {
            "provider": "openai",
            "providerApiKey": provider_key,
            "model": model,
            "messages": messages,
            # Tracking defaults
            "useCaseName": "={{ $workflow.name.replaceAll(' ', '-') }}",
            "useCaseId": "={{ 'openai/' + $parameter.model + '/' + $execution.id }}",
            "useCaseStep": "={{ $node.name }}",
            # Output defaults
            "includeCostData": True,
            "returnFullResponse": False,
            "debugLogging": False,
        },
        "credentials": {
            "payiApi": {
                "id": str(payi_cred["id"]),
                "name": payi_cred["name"],
            },
        },
    }
    return new_node


# ── Connection Rewiring ──────────────────────────────────────────────────────

def unique_node_name(desired: str, existing_names: set) -> str:
    """Return a unique node name, appending a numeric suffix if needed."""
    if desired not in existing_names:
        return desired
    i = 1
    while f"{desired} {i}" in existing_names:
        i += 1
    return f"{desired} {i}"


def rewire_connections(connections: dict, old_name: str, new_name: str) -> dict:
    """Rename a node in the connections map (both as key and as target)."""
    if old_name == new_name:
        return connections

    new_connections = {}
    for source_name, source_conns in connections.items():
        key = new_name if source_name == old_name else source_name
        new_source_conns = {}
        for conn_type, conn_list in source_conns.items():
            new_conn_list = []
            for slot_connections in conn_list:
                new_slot = []
                for conn in slot_connections:
                    c = dict(conn)
                    if c.get("node") == old_name:
                        c["node"] = new_name
                    new_slot.append(c)
                new_conn_list.append(new_slot)
            new_source_conns[conn_type] = new_conn_list
        new_connections[key] = new_source_conns
    return new_connections


# ── Expression Reference Scanning ────────────────────────────────────────────

def fix_expression_references(nodes: list, old_name: str, new_name: str, dry_run: bool = False) -> int:
    """Find and replace $('Old Name') references in node parameters. Returns count of fixes."""
    if old_name == new_name:
        return 0

    # Match $('name') or $("name") patterns
    pattern_single = re.compile(re.escape(f"$('{old_name}')"))
    pattern_double = re.compile(re.escape(f'$("{old_name}")'))

    count = 0

    def replace_in_value(value):
        nonlocal count
        if isinstance(value, str):
            new_val = pattern_single.sub(f"$('{new_name}')", value)
            new_val = pattern_double.sub(f'$("{new_name}")', new_val)
            if new_val != value:
                count += 1
            return new_val
        elif isinstance(value, dict):
            return {k: replace_in_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [replace_in_value(item) for item in value]
        return value

    for node in nodes:
        if "parameters" in node:
            node["parameters"] = replace_in_value(node["parameters"])

    return count


# ── Workflow Update ──────────────────────────────────────────────────────────

SETTINGS_ALLOWED_KEYS = {
    "saveExecutionProgress", "saveManualExecutions",
    "saveDataErrorExecution", "saveDataSuccessExecution",
    "executionTimeout", "errorWorkflow", "timezone", "executionOrder",
}


def filter_workflow_for_update(workflow: dict) -> dict:
    """Keep only fields the PUT endpoint accepts."""
    result = {k: v for k, v in workflow.items() if k in WORKFLOW_PUT_ALLOWED_FIELDS}
    # Sanitize settings to only known-good keys
    if "settings" in result and isinstance(result["settings"], dict):
        result["settings"] = {
            k: v for k, v in result["settings"].items()
            if k in SETTINGS_ALLOWED_KEYS
        }
    return result


# ── Interactive Selection ────────────────────────────────────────────────────

REPLACEMENT_LABELS = {
    "chat_model": "Pay-i Chat Model",
    "chat_model_anthropic": "Pay-i Anthropic Chat Model",
    "chat_model_azure": "Pay-i Azure OpenAI Chat Model",
    "chat_model_bedrock": "Pay-i Bedrock Chat Model",
    "chat_model_databricks": "Pay-i Databricks Chat Model",
    "proxy": "Pay-i Proxy",
    "proxy_anthropic": "Pay-i Proxy (Anthropic)",
}


def print_discovery_summary(found: list):
    """Print a nice summary table of detected AI nodes."""
    # Aggregate by provider + category
    summary = {}
    for n in found:
        provider = n["provider"]
        label = n["label"]
        key = (provider, label)
        if key not in summary:
            summary[key] = {"count": 0, "feasible": n["feasible"], "skip_reason": n.get("skip_reason", "")}
        summary[key]["count"] += 1

    print(bold("  Detected AI Nodes"))
    print()
    print(f"  {'Provider':<16} {'Node Type':<36} {'Count':>5}  {'Status'}")
    print(f"  {'─' * 16} {'─' * 36} {'─' * 5}  {'─' * 20}")

    total = 0
    migratable = 0
    for (provider, label), info in sorted(summary.items()):
        total += info["count"]
        if info["feasible"]:
            migratable += info["count"]
            status = green("Migratable")
        else:
            status = yellow("Skip") + dim(f" ({info['skip_reason'][:30]})")
        provider_label = PROVIDER_CREDENTIAL_CONFIG.get(provider, {}).get("label", provider.title())
        print(f"  {provider_label:<16} {label:<36} {info['count']:>5}  {status}")

    print(f"  {'─' * 16} {'─' * 36} {'─' * 5}  {'─' * 20}")
    print(f"  {'Total':<16} {'':<36} {total:>5}  {green(str(migratable))} migratable, {yellow(str(total - migratable))} skipped")
    print()


def prompt_select_workflows(workflows: list) -> list:
    """Let the user pick which workflows to migrate when multiple are found."""
    print(bold("  Select Workflows"))
    print()

    # Show numbered list with AI node counts per workflow
    for i, wf in enumerate(workflows, 1):
        wf_name = wf.get("name", "Untitled")
        wf_id = wf.get("id", "?")
        node_count = len(wf.get("nodes", []))
        ai_count = sum(1 for n in wf.get("nodes", []) if n.get("type", "") in NATIVE_LLM_NODES)
        ai_tag = f" ({green(str(ai_count) + ' AI node' + ('s' if ai_count != 1 else ''))})" if ai_count else dim(" (no AI nodes)")
        print(f"  {bold(f'[{i}]')} {wf_name} {dim(f'(ID: {wf_id})')}{ai_tag}")

    print()
    print(f"  {bold('[A]')} All workflows")
    print()
    answer = input(f"  Which workflow(s)? [comma-separated numbers or A]: ").strip().lower()

    if not answer or answer == "a":
        return workflows

    try:
        indices = [int(x.strip()) for x in answer.split(",")]
        selected = [workflows[i - 1] for i in indices if 1 <= i <= len(workflows)]
        if selected:
            names = ", ".join(w.get("name", "?") for w in selected)
            print(f"  Selected: {green(names)}")
        return selected
    except (ValueError, IndexError):
        print(f"  {yellow('Invalid selection')} — using all workflows")
        return workflows


def prompt_migration_strategy(found: list, redirectable_creds: list) -> str:
    """Ask the user which migration approach to use."""
    has_migratable = any(n["feasible"] for n in found)
    has_redirectable = len(redirectable_creds) > 0

    print(bold("  Migration Strategy"))
    print()

    if has_redirectable:
        print(f"  {bold('[1]')} Credential Redirect {green('(recommended)')}")
        print(f"      Change API endpoint URLs to route ALL actions through Pay-i proxy.")
        print(f"      Fastest approach — covers every endpoint for each credential.")
        cred_names = ", ".join(f"{c['name']} ({c['type']})" for c in redirectable_creds)
        print(f"      Credentials: {dim(cred_names)}")
        print()

    if has_migratable:
        print(f"  {bold('[2]')} Node Replacement {dim('(full tracking)')}")
        print(f"      Replace Chat Model nodes with Pay-i equivalents.")
        print(f"      Adds full tracking headers (use case, user ID, limits).")
        print()

    if has_redirectable and has_migratable:
        print(f"  {bold('[3]')} Both (redirect + replace)")
        print(f"      Credential redirect for all endpoints + node replacement")
        print(f"      for full tracking on Chat Model nodes.")
        print()

    print(f"  {bold('[D]')} Dry run (preview changes without applying)")
    print(f"  {bold('[Q]')} Cancel")
    print()

    default = "1" if has_redirectable else "2"
    answer = input(f"  Strategy [{default}]: ").strip().lower()
    if not answer:
        answer = default

    return answer


def prompt_select_nodes(found: list) -> list:
    """Display a numbered list and let the user pick which nodes to migrate.

    Returns the subset of *feasible* nodes the user selected.
    """
    print(bold("  Select Nodes for Replacement"))
    print()

    migratable_indices = []

    for i, n in enumerate(found):
        num = i + 1
        wf = n["workflow_name"]
        node_name = n["node"]["name"]
        label = n["label"]

        if n["feasible"]:
            tag = green("MIGRATABLE")
            migratable_indices.append(i)
            replacement = REPLACEMENT_LABELS.get(n["replacement"], "Pay-i Node")
            detail = dim(f"-> {replacement}")
        else:
            tag = yellow("SKIP")
            detail = dim(n.get("skip_reason", "not supported"))

        print(f"  {bold(str(num)):>4}  [{tag}]  {wf} / {bold(node_name)}")
        print(f"        {label}  {detail}")
        print()

    if not migratable_indices:
        return []

    migratable_nums = [str(i + 1) for i in migratable_indices]
    hint = ",".join(migratable_nums)

    print(f"  Migratable: {', '.join(migratable_nums)}")
    print()
    answer = input(f"  Migrate which nodes? [{hint} / {bold('all')} / none]: ").strip().lower()

    if not answer or answer == "all":
        return [found[i] for i in migratable_indices]
    elif answer == "none":
        return []
    else:
        selected = []
        for part in answer.replace(" ", "").split(","):
            try:
                idx = int(part) - 1
                if 0 <= idx < len(found) and found[idx]["feasible"]:
                    selected.append(found[idx])
                elif 0 <= idx < len(found):
                    print(f"  {yellow('Note')}: #{part} ({found[idx]['label']}) is not migratable, skipping")
                else:
                    print(f"  {yellow('Note')}: #{part} is not a valid number, skipping")
            except ValueError:
                print(f"  {yellow('Note')}: '{part}' is not a number, skipping")
        return selected


# ── Display Helpers ──────────────────────────────────────────────────────────

def print_banner():
    print()
    print(bold("=" * 62))
    print(bold("  Pay-i Workflow Migration"))
    print(bold("=" * 62))
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def execute_credential_redirect(client, redirectable_creds: list, payi_base: str, payi_key: str, dry_run: bool = False) -> int:
    """Redirect credentials to Pay-i proxy URLs. Returns count of redirected.

    n8n's PATCH endpoint requires ALL credential fields (including apiKey).
    We first fetch the existing credential data via ``?includeData=true``,
    merge our redirect changes, then PATCH with the complete data.
    """
    redirected = 0
    for cred in redirectable_creds:
        config = CREDENTIAL_REDIRECT_CONFIG.get(cred["type"])
        if not config:
            continue

        base = payi_base.rstrip("/")
        proxy_url = f"{base}{config['proxy_path']}"

        if dry_run:
            print(f'    {cyan("DRY RUN")} "{cred["name"]}" ({cred["type"]}) -> {proxy_url}')
            redirected += 1
            continue

        # Fetch existing credential data (including secrets) so the PATCH
        # includes all required fields — n8n rejects partial updates.
        existing_data = _fetch_credential_data(client, cred["id"])
        if not existing_data:
            print(f'    {yellow("SKIP")} "{cred["name"]}" — could not read credential data from n8n')
            print(f'           (Ensure n8n API supports includeData, or update credentials manually)')
            continue

        patch = build_credential_patch(cred["type"], payi_base, payi_key,
                                       existing_data=existing_data)
        if not patch:
            continue

        try:
            client.patch(f"/api/v1/credentials/{cred['id']}", patch)
            print(f'    {green("OK")} "{cred["name"]}" ({cred["type"]}) -> {proxy_url}')
            redirected += 1
        except SystemExit:
            print(f'    {red("FAIL")} "{cred["name"]}" — could not patch credential')

    return redirected


def execute_node_replacement(client, selected: list, workflows: list, payi_cred: dict,
                             provider_creds: dict, dry_run: bool = False, workflow_filter: str = None,
                             verbose: bool = False) -> tuple:
    """Replace nodes in workflows. Returns (migrated_count, skipped_count)."""
    migrated = 0
    skipped = 0

    by_wf_id = {}
    for n in selected:
        wf_id = n["workflow_id"]
        if wf_id not in by_wf_id:
            by_wf_id[wf_id] = {"workflow_name": n["workflow_name"], "nodes": []}
        by_wf_id[wf_id]["nodes"].append(n)

    for wf_id, wf_info in by_wf_id.items():
        print(f'  {bold(wf_info["workflow_name"])} {dim("(ID: " + str(wf_id) + ")")}')

        if dry_run:
            if workflow_filter:
                workflow = copy.deepcopy(workflows[0])
            else:
                workflow = copy.deepcopy(client.get(f"/api/v1/workflows/{wf_id}"))
        else:
            workflow = client.get(f"/api/v1/workflows/{wf_id}")

        # Save a pristine deep copy BEFORE any modifications for the backup
        original_workflow_snapshot = copy.deepcopy(workflow)

        nodes = workflow.get("nodes", [])
        connections = workflow.get("connections", {})
        existing_names = {n["name"] for n in nodes}
        modified = False

        for node_info in wf_info["nodes"]:
            node = node_info["node"]
            old_name = node["name"]
            provider = node_info["provider"]

            # For chat_model_* replacements, credentials are inherited from the
            # original node — no separate provider key needed.
            # For proxy_* replacements, the provider key is still needed as a parameter.
            cred_val = provider_creds.get(provider, "") if provider_creds else ""

            replacement_type = node_info["replacement"]
            replacement_label = REPLACEMENT_LABELS.get(replacement_type, "Pay-i Node")
            desired_name = replacement_label
            new_name = unique_node_name(desired_name, existing_names - {old_name})

            # Dispatch to the right builder
            builder_map = {
                "chat_model": build_payi_chat_model_node,
                "chat_model_anthropic": build_payi_chat_model_anthropic_node,
                "chat_model_azure": build_payi_chat_model_azure_node,
                "chat_model_bedrock": build_payi_chat_model_bedrock_node,
                "chat_model_databricks": build_payi_chat_model_databricks_node,
                "proxy": build_payi_proxy_node,
                "proxy_anthropic": build_payi_proxy_anthropic_node,
            }
            builder = builder_map.get(replacement_type)
            if not builder:
                print(f'    {yellow("SKIP")} "{old_name}" — no builder for {replacement_type}')
                skipped += 1
                continue

            new_node = builder(node, payi_cred, cred_val, new_name)

            # Log credential passthrough details in verbose mode
            if verbose:
                orig_creds = node.get("credentials", {})
                new_creds = new_node.get("credentials", {})
                print(f'       {dim("[CREDS]")} Original node credentials: {json.dumps(orig_creds)}')
                print(f'       {dim("[CREDS]")} New node credentials:      {json.dumps(new_creds)}')

            for i, n in enumerate(nodes):
                if n.get("name") == old_name and n.get("type") == node_info["node_type"]:
                    nodes[i] = new_node
                    break

            existing_names.discard(old_name)
            existing_names.add(new_name)
            connections = rewire_connections(connections, old_name, new_name)
            ref_fixes = fix_expression_references(nodes, old_name, new_name, dry_run=dry_run)

            if dry_run:
                print(f'    {cyan("DRY RUN")} "{old_name}" -> "{new_name}"')
            else:
                print(f'    {green("OK")} "{old_name}" -> "{new_name}"')

            if ref_fixes:
                print(f'       Updated {ref_fixes} expression reference(s)')

            migrated += 1
            modified = True

        if modified and not dry_run:
            # Save a backup copy using the PRISTINE snapshot (before any modifications)
            try:
                backup_body = filter_workflow_for_update(original_workflow_snapshot)
                original_name = original_workflow_snapshot.get("name", "Untitled")
                backup_body["name"] = f"{original_name} (Pre-Migration Backup)"
                backup_resp = client.post("/api/v1/workflows", backup_body)
                backup_id = backup_resp.get("id", "?")
                print(f'    {dim(f"Backup saved as ID {backup_id}")}'  )
            except Exception as e:
                print(f'    {yellow("WARNING")}: Could not create backup: {e}')

            # Update the original workflow with migrated nodes and new name
            workflow["nodes"] = nodes
            workflow["connections"] = connections
            workflow["name"] = f"{original_workflow_snapshot.get('name', 'Untitled')} (Pay-i)"
            update_body = filter_workflow_for_update(workflow)
            put_resp = client.put(f"/api/v1/workflows/{wf_id}", update_body)
            print(f'    {green("Saved")} as "{workflow["name"]}"')

            # Verify credentials survived the PUT (n8n may strip them for
            # unrecognised node types or missing credential associations)
            saved_nodes = put_resp.get("nodes", [])
            cred_warnings = []
            for sn in saved_nodes:
                if sn.get("type", "").startswith("n8n-nodes-payi."):
                    saved_creds = sn.get("credentials", {})
                    if not saved_creds:
                        cred_warnings.append(sn.get("name", "?"))
                    elif verbose:
                        print(f'       {dim("[VERIFY]")} {sn["name"]} credentials saved: {json.dumps(saved_creds)}')
            if cred_warnings:
                print(f'    {yellow("WARNING")}: Credentials NOT saved for: {", ".join(cred_warnings)}')
                print(f'           Open each node in n8n and select the credentials manually.')
                print(f'           (This can happen if n8n hasn\'t loaded the Pay-i community node; try restarting n8n.)')

        print()

    return migrated, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Migrate n8n workflows from native LLM nodes to Pay-i nodes",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying anything")
    parser.add_argument("--auto-yes", action="store_true",
                        help="Skip interactive selection — migrate all feasible nodes")
    parser.add_argument("--workflow", metavar="ID",
                        help="Migrate only the specified workflow ID")
    parser.add_argument("--verbose", action="store_true",
                        help="Show detailed API request/response logging")
    parser.add_argument("--strategy", choices=["redirect", "replace", "both"],
                        help="Migration strategy (skip interactive prompt)")
    args = parser.parse_args()

    print_banner()

    # ── Step 1: Connection Setup ─────────────────────────────────────────
    print(bold("  Step 1: Connection Setup"))
    print()

    # Check if all env vars are present (CI/non-interactive mode)
    env_vars_present = all(os.environ.get(v) for v in ["N8N_BASE_URL", "N8N_API_KEY", "PAYI_BASE_URL", "PAYI_API_KEY"])

    if env_vars_present:
        n8n_base = os.environ["N8N_BASE_URL"].rstrip("/")
        n8n_key = os.environ["N8N_API_KEY"]
        payi_base = os.environ["PAYI_BASE_URL"].rstrip("/")
        payi_key = os.environ["PAYI_API_KEY"]
        print(f"  {green('Using environment variables')}")
    elif _is_interactive():
        details = setup_connection_details(args)
        n8n_base = details["n8n_base"]
        n8n_key = details["n8n_key"]
        payi_base = details["payi_base"]
        payi_key = details["payi_key"]
    else:
        print(f"{red('ERROR')}: Missing environment variables (non-interactive mode).")
        print("  Set: N8N_BASE_URL, N8N_API_KEY, PAYI_BASE_URL, PAYI_API_KEY")
        return 1

    print()
    print(f"  n8n instance:  {cyan(n8n_base)}")
    print(f"  Pay-i base:    {cyan(payi_base)}")
    if args.dry_run:
        print(f"  Mode:          {yellow('DRY RUN')} (no changes will be made)")
    print()

    client = N8nApiClient(n8n_base, n8n_key, verbose=args.verbose)

    # ── Step 2: Scan Workflows ───────────────────────────────────────────
    print(bold("  Step 2: Scanning workflows"))
    print()

    if args.workflow:
        wf_data = client.get(f"/api/v1/workflows/{args.workflow}")
        workflows = [wf_data]
    else:
        wf_resp = client.get("/api/v1/workflows")
        workflows = wf_resp.get("data", wf_resp) if isinstance(wf_resp, dict) else wf_resp
        if isinstance(workflows, dict):
            workflows = [workflows]

    if not workflows:
        print("  No workflows found.")
        return 0

    # For list endpoints that return partial data, fetch full workflows
    full_workflows = []
    for wf in workflows:
        if isinstance(wf.get("nodes"), list) and isinstance(wf.get("connections"), dict):
            full_workflows.append(wf)
        else:
            wf_id = wf.get("id")
            if wf_id:
                full_workflows.append(client.get(f"/api/v1/workflows/{wf_id}"))
    workflows = full_workflows

    # ── Workflow selection (interactive) ─────────────────────────────
    if not args.workflow and len(workflows) > 1 and _is_interactive() and not args.auto_yes:
        workflows = prompt_select_workflows(workflows)
        if not workflows:
            print("  No workflows selected. Exiting.")
            return 0
        print()

    found = find_llm_nodes(workflows)
    redirectable_creds = find_redirectable_credentials(client, workflows)
    databricks_nodes = find_databricks_nodes(workflows)

    if not found and not redirectable_creds and not databricks_nodes:
        print("  No AI nodes or redirectable credentials found. Nothing to migrate.")
        return 0

    print(f"  Scanned {len(workflows)} workflow(s), found {len(found)} AI node(s)")
    if redirectable_creds:
        print(f"  Found {len(redirectable_creds)} redirectable credential(s)")
    if databricks_nodes:
        print(f"  Found {yellow(str(len(databricks_nodes)))} Databricks/AgentBricks node(s)")
    print()

    # ── Databricks/AgentBricks Warnings ──────────────────────────────────
    # Known Databricks types in NATIVE_LLM_NODES are auto-migrated above.
    # This section warns about additional Databricks nodes (unknown community
    # node types, HTTP Request nodes calling Databricks URLs) that can't be
    # auto-migrated but should be reviewed.
    if databricks_nodes:
        print(yellow(bold("  ⚠ Additional Databricks / AgentBricks Detected")))
        print()
        for dbx in databricks_nodes:
            print(f"    • {bold(dbx['node_name'])} ({dim(dbx['node_type'])})")
            print(f"      Workflow: {dbx['workflow_name']} (ID: {dbx['workflow_id']})")
            print(f"      Reason:   {dbx['reason']}")
        print()
        print(f"  {yellow('Note:')} These {len(databricks_nodes)} node(s) use non-standard Databricks")
        print(f"  types and require manual replacement with Pay-i Databricks (Proxy).")
        print()

    if found:
        print_discovery_summary(found)

    # ── Step 3: Choose Strategy ──────────────────────────────────────────
    print(bold("  Step 3: Choose migration strategy"))
    print()

    if args.strategy:
        strategy = {"redirect": "1", "replace": "2", "both": "3"}[args.strategy]
    elif args.auto_yes:
        strategy = "3" if redirectable_creds else "2"
        print(f"  Auto-selected: {'both' if strategy == '3' else 'node replacement'}")
        print()
    else:
        strategy = prompt_migration_strategy(found, redirectable_creds)

    dry_run = args.dry_run or strategy.lower() == "d"
    if strategy.lower() == "q":
        print("  Cancelled.")
        return 0

    do_redirect = strategy in ("1", "3")
    do_replace = strategy in ("2", "3")

    # ── Step 4: Collect Credentials ──────────────────────────────────────
    print(bold("  Step 4: Credentials"))
    print()

    payi_cred = {"id": "dry-run", "name": "Pay-i API (dry run)"}
    provider_creds = {}

    if not dry_run and do_replace:
        payi_cred = ensure_payi_credential(client, payi_key, payi_base)
        print()

    if do_replace:
        selected = [n for n in found if n["feasible"]]
        if not args.auto_yes and _is_interactive():
            selected = prompt_select_nodes(found)
            print()

        if not dry_run and selected:
            # Chat model nodes use credential passthrough (the existing provider
            # credential is copied to the Pay-i node) — no API key needed.
            # Proxy nodes still need provider API keys as node parameters.
            proxy_nodes = [n for n in selected if n.get("replacement", "").startswith("proxy")]
            if proxy_nodes:
                provider_creds = collect_provider_credentials(proxy_nodes)
                print()
            else:
                print(f"  {green('Provider credentials inherited')} from existing nodes (no re-entry needed)")
                print()
    else:
        selected = []

    # ── Step 5: Execute Migration ────────────────────────────────────────
    print(bold("  Step 5: Migrating"))
    print()

    creds_redirected = 0
    nodes_migrated = 0
    nodes_skipped = 0

    # Credential redirect
    if do_redirect and redirectable_creds:
        print(bold("  Credential Redirects:"))
        print()
        creds_redirected = execute_credential_redirect(client, redirectable_creds, payi_base, payi_key, dry_run=dry_run)
        print()

    # Node replacement
    if do_replace and selected:
        print(bold("  Node Replacements:"))
        print()
        nodes_migrated, nodes_skipped = execute_node_replacement(
            client, selected, workflows, payi_cred, provider_creds,
            dry_run=dry_run, workflow_filter=args.workflow, verbose=args.verbose,
        )

    infeasible_count = len([n for n in found if not n["feasible"]])
    total_skipped = nodes_skipped + infeasible_count

    # ── Summary ──────────────────────────────────────────────────────────
    print(bold("=" * 62))
    tag = yellow("DRY RUN") if dry_run else green("COMPLETE")
    print(f"  Migration {tag}")
    print()
    if creds_redirected:
        print(f"  Credentials redirected: {green(str(creds_redirected)) if not dry_run else cyan(str(creds_redirected))}")
    if nodes_migrated:
        print(f"  Nodes replaced:        {green(str(nodes_migrated)) if not dry_run else cyan(str(nodes_migrated))}")
    if total_skipped:
        print(f"  Nodes skipped:         {yellow(str(total_skipped))}")
    if not creds_redirected and not nodes_migrated:
        print(f"  {yellow('No changes made.')}")
    print(bold("=" * 62))
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
