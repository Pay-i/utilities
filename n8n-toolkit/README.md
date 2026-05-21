# n8n-toolkit

Audit and migrate [n8n](https://n8n.io) AI workflows to route their LLM
calls through [Pay-i](https://pay-i.com) for cost tracking and budget
enforcement.

Companion to [n8n-nodes-payi](https://github.com/pay-i/n8n-nodes-payi),
the community node package that exposes Pay-i to n8n workflows.

## What it does

- Inventory where AI providers (OpenAI, Anthropic, Azure OpenAI, AWS
  Bedrock, Databricks) are used across your n8n workflows
- Generate JSON and Markdown migration plans
- Detect Databricks workspaces accessed through OpenAI-compatible
  shims and route them correctly to the Pay-i Databricks node
- Redirect supported credentials to Pay-i proxy URLs
- Replace native LLM nodes with Pay-i equivalents, with credential
  passthrough so you don't re-enter API keys

## Documentation

Full documentation lives in [`docs/`](./docs/README.md). Start there.

| Guide | Description |
|-------|-------------|
| [Getting Started](./docs/GETTING_STARTED.md) | Prerequisites, setup, and recommended operator flow |
| [Command Reference](./docs/COMMAND_REFERENCE.md) | All scripts, flags, and CI/pipeline usage |
| [Audit and Compliance Reports](./docs/AUDIT_AND_REPORTS.md) | JSON/Markdown report generation and artifact pairing |
| [Workflow Fixtures](./docs/WORKFLOW_FIXTURES.md) | Test fixtures included in this repo |
| [Limitations and Known Issues](./docs/LIMITATIONS_AND_KNOWN_ISSUES.md) | Current constraints and provider-specific caveats |
| [Changelog for Operators](./docs/CHANGELOG_FOR_OPERATORS.md) | Operational changelog with required actions per release |
| [Changelog](./CHANGELOG.md) | Project changelog (Keep a Changelog format) |
| [Software Bill of Materials](./SBOM.md) | Dependencies and runtime services |
| [Agentic Tool Instructions](./AGENTIC-TOOL-INSTRUCTIONS.md) | Project context for AI coding agents |

## Main scripts

| Script | Purpose |
|---|---|
| `audit-configure-payi-proxy.py` | Read workflows, analyze providers and actions, probe credential redirect capability, emit JSON/Markdown reports, optionally patch redirectable credentials |
| `migrate-workflows-to-payi.py` | Interactive migration with strategy selection (`redirect`, `replace`, `both`) |
| `migrate-to-payi.sh` | Credential redirect for OpenAI, Anthropic, Azure OpenAI |
| `migrate-openai-to-payi.sh` | Credential redirect for OpenAI only |

## Quick start

The toolkit uses only the Python standard library — no `pip install`
step required.

```bash
# Set environment variables (or use a .env file — see .env.example)
export N8N_BASE_URL=http://localhost:5678
export N8N_API_KEY=your-n8n-api-key
export PAYI_BASE_URL=https://api.pay-i.com
export PAYI_API_KEY=your-payi-api-key

# Audit (read-only)
python3 audit-configure-payi-proxy.py --out audit.json

# Render the audit as Markdown
python3 audit-configure-payi-proxy.py \
  --from-json audit.json --report-format md --out audit.md

# Migrate (always dry-run first)
python3 migrate-workflows-to-payi.py --dry-run

# Apply the migration once dry-run looks correct
python3 migrate-workflows-to-payi.py
```

See [`.env.example`](./.env.example) for the full list of supported
environment variables.

## Databricks workflows

The toolkit detects Databricks workspaces accessed via the OpenAI
compatibility shim (`lmChatOpenAi` nodes whose `options.baseURL`
points at `*.azuredatabricks.net` or `*.cloud.databricks.com`) and
migrates them to the Pay-i Databricks node with the correct
`cloudProvider` setting.

For ambiguous `*.cloud.databricks.com` hostnames the migrator defaults
to `aws` and prompts you to confirm or override. In non-interactive
mode, use `--databricks-cloud {aws,google,databricks}`.

If you already have a `payiDatabricksApi` credential in n8n, the
migrator reuses it. If not, it prompts to create one (or reads
`PAYI_DBX_PAT` and `PAYI_DBX_WORKSPACE_URL` for non-interactive
provisioning).

## Notes

- Scripts are interactive by default and prompt for missing required
  values.
- For CI and pipelines, set environment variables and use
  `--auto-yes`. See `.env.example`.
- Provider support depends on both this toolkit and the installed
  `n8n-nodes-payi` version.

## Container

A minimal `Dockerfile` is provided for running the CLIs in a
sandboxed environment. Run from inside the `n8n-toolkit/` directory:

```bash
docker build -t n8n-toolkit .
mkdir -p reports
docker run --rm \
  -e N8N_BASE_URL -e N8N_API_KEY \
  -e PAYI_BASE_URL -e PAYI_API_KEY \
  -v "$(pwd)/reports:/reports" \
  n8n-toolkit \
  audit-configure-payi-proxy.py --out /reports/audit.json
```

The audit JSON lands in `./reports/audit.json` on the host.

## Development

```bash
# From the n8n-toolkit/ directory
python3 -m pytest test_migrate_workflows.py -q
```

CI runs on Python 3.10 and 3.12 — see the GitHub Actions workflow at
the root of the monorepo.

## License

MIT. See [`LICENSE`](./LICENSE).
</content>
</invoke>