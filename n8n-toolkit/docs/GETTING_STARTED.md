# Getting Started

## 1) Prerequisites

- n8n API access
  - `N8N_BASE_URL`
  - `N8N_API_KEY`
- Pay-i access (needed for credential patch/apply)
  - `PAYI_BASE_URL`
  - `PAYI_API_KEY`
- Python 3.8+
- Bash + curl (for shell redirect scripts)

Notes:
- Python scripts are interactive by default and prompt for missing required values.
- For CI/pipelines, use flags/env-vars and `--non-interactive` where supported.

## 2) Recommended Operator Flow

1. Run audit in read-only mode.
2. Review [Limitations and Known Issues](./LIMITATIONS_AND_KNOWN_ISSUES.md).
3. Review `migration_manifest` and credential capability states.
4. Treat `unverified` credentials as manual validation items before apply mode.
5. Decide migration strategy:
   - credential redirect
   - node replacement
   - both
6. Run migration in dry-run mode first.
7. Apply in controlled batches.
8. Validate workflow execution and tracking output.

## 3) Read-Only Audit

```bash
python3 audit-configure-payi-proxy.py --out ./audit.json
```

Generate Markdown from JSON for review/compliance:

```bash
python3 audit-configure-payi-proxy.py \
  --from-json ./audit.json \
  --report-format md \
  --out ./audit.md
```

## 4) Interactive Migration Orchestrator

```bash
python3 migrate-workflows-to-payi.py
```

The script guides you through:
- connection setup,
- workflow scan,
- strategy selection (`redirect`, `replace`, `both`),
- credentials and apply flow.

Dry-run:

```bash
python3 migrate-workflows-to-payi.py --dry-run
```

## 5) Redirect-Only Scripts

All supported credentials:

```bash
./migrate-to-payi.sh
```

OpenAI only:

```bash
./migrate-openai-to-payi.sh
```

## 6) Validation Checklist

- Workflows still execute successfully
- Expected credentials are attached to migrated nodes
- Expected requests route through Pay-i proxy
- Cost/usage/tracking data appears as expected
- No broken expression references
