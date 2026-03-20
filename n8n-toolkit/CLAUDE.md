# CLAUDE.md — n8n-toolkit

## What This Is

CLI toolkit for migrating and auditing n8n AI workflows to route through Pay-i. Part of the `payi-utilities` monorepo (subtree import).

## Stack

- **Language:** Python 3.8+ (stdlib only — no third-party dependencies)
- **Shell:** Bash + curl (for redirect-only scripts)
- **Testing:** `unittest` (stdlib)
- **Target:** Self-hosted n8n instances via REST API

## Key Scripts

| Script | Purpose |
|--------|---------|
| `audit-configure-payi-proxy.py` | Audit workflows, probe credentials, emit JSON/Markdown reports, optionally patch |
| `migrate-workflows-to-payi.py` | Interactive migration: redirect, replace, or both |
| `migrate-to-payi.sh` | Bulk credential redirect (OpenAI, Anthropic, Azure OpenAI) |
| `migrate-openai-to-payi.sh` | OpenAI-only credential redirect |

## Commands

```bash
# Run all unit tests
python3 -m unittest discover -s . -p "test_*.py" -v

# Audit (read-only)
python3 audit-configure-payi-proxy.py --out ./audit.json

# Markdown report from JSON
python3 audit-configure-payi-proxy.py --from-json ./audit.json --report-format md --out ./audit.md

# Interactive migration (dry-run)
python3 migrate-workflows-to-payi.py --dry-run
```

## Architecture Notes

- All scripts are single-file, zero-dependency Python. No `requirements.txt` or `pyproject.toml` needed.
- Workflow fixtures (`sample-workflow-*.json`, `test-workflow-*.json`) are test data, not production artifacts.
- `docs/` contains customer-facing documentation. `docs/DEMO_VIDEO_SCRIPT.md` and `docs/LOCAL_TESTING.md` are internal-only and gitignored.
- This directory is a subtree inside `payi-utilities`. CI, containerization, and gitleaks hooks live at the parent repo level.

## Confidentiality

This is a Pay-i project. All data classification and confidentiality rules from the root `~/src/CLAUDE.md` apply. No Pay-i proprietary data leaves this machine without explicit confirmation.
