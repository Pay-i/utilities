# User Documentation

This folder is for operators using the toolkit in n8n environments.

## Start Here

- [Getting Started](./GETTING_STARTED.md)
- [Command Reference](./COMMAND_REFERENCE.md)
- [Audit and Compliance Reports](./AUDIT_AND_REPORTS.md)
- [Limitations and Known Issues](./LIMITATIONS_AND_KNOWN_ISSUES.md)
- [Workflow Fixtures for Testing](./WORKFLOW_FIXTURES.md)
- [Local Testing Runbook](./LOCAL_TESTING.md)
- [Changelog For Operators](./CHANGELOG_FOR_OPERATORS.md)

## Script Overview

- `audit-configure-payi-proxy.py`
  - Workflow and credential inventory
  - Credential capability probing
  - Migration manifest output
  - JSON + Markdown report generation
  - Optional credential patching for redirectable credentials

- `migrate-workflows-to-payi.py`
  - Interactive migration runner
  - Strategy selection: credential redirect, node replacement, or both
  - Workflow backups and renamed migrated workflows

- `migrate-to-payi.sh`
  - Bulk credential redirect for OpenAI, Anthropic, Azure OpenAI

- `migrate-openai-to-payi.sh`
  - OpenAI-only credential redirect

## Intended Audience

- Platform admins running self-hosted n8n
- Integration engineers migrating workflows to Pay-i
- Security/compliance teams reviewing migration artifacts
