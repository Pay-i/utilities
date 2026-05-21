# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.0.1] - 2026-05-21

### Added
- Databricks-shim detection: `lmChatOpenAi` nodes whose `baseURL` (or
  linked `openAiApi` credential URL) targets a Databricks workspace
  hostname are reclassified as `chat_model_databricks` and migrated to
  `n8n-nodes-payi.lmChatPayiDatabricks`.
- `--databricks-cloud` and `--databricks-credential-id` CLI flags on
  the migrator for non-interactive Databricks runs.
- `resolve_payi_databricks_credential()` helper picks (or creates) a
  `payiDatabricksApi` credential once per migration; reused across all
  shim node replacements.
- Audit script recognizes `n8n-nodes-payi.lmChatPayiDatabricks` and the
  `payiDatabricksApi` credential type so workflows already on the new
  Databricks proxy node show up correctly in audit reports.
- `KNOWN_PAYI_CREDENTIAL_TYPES` mapping in the audit script tags Pay-i
  credentials with `already_payi_credential=true`.
- Test fixtures `test-workflow-databricks-shim.json` and
  `test-workflow-payi-databricks.json` plus expanded test coverage
  (shim detection, shim builder, credential resolver, end-to-end
  migration, audit-side recognition).
- Documentation cross-linking and navigation across all user-facing docs
- `SBOM.md` software bill of materials
- `CHANGELOG.md` (this file)

### Changed
- Audit script display labels for Pay-i nodes match upstream
  `n8n-nodes-payi` v1.0.1 ("Pay-i OpenAI (Proxy)", "Pay-i Anthropic
  (Proxy)", "Pay-i Azure AI Foundry (Proxy)", "Pay-i Amazon Bedrock
  (Proxy)", "Pay-i Databricks (Proxy)").
- The community-node Databricks builder is now
  `build_payi_chat_model_databricks_community_node` to disambiguate
  from the new shim-path builder; dispatch chooses by inspecting
  `databricks_shim` on the discovered node entry.
- Root `README.md` expanded with full documentation table
- `docs/README.md` rewritten as structured documentation hub with reading order
- All doc pages now include navigation headers and "See Also" footers
- `.gitignore` updated to cover standard project artifacts, env files,
  virtualenvs, IDE artifacts, build outputs, and local working directories

## [0.3.0] - 2026-03-06

### Added
- Databricks provider support across migration and audit tooling
- Databricks credential provisioning support
- Test coverage for Databricks detection, node building, credential passthrough (157 tests total)

### Changed
- Documentation updates across getting started guide, command reference, audit reports, and workflow fixtures

## [0.2.0] - 2026-03-04

### Changed
- Documentation cleanup and structure alignment
- Simplified root `README.md`
- Added `docs/COMMAND_REFERENCE.md` and `docs/LIMITATIONS_AND_KNOWN_ISSUES.md`
- Moved non-user report artifacts out of repo root

## [0.1.0] - 2026-03-02

### Added
- Initial release of n8n migration and audit toolkit
- `audit-configure-payi-proxy.py` — workflow/provider inventory, credential probing, JSON/Markdown reports
- `migrate-workflows-to-payi.py` — interactive migration with strategy selection
- `migrate-to-payi.sh` — bulk credential redirect (OpenAI, Anthropic, Azure OpenAI)
- `migrate-openai-to-payi.sh` — OpenAI-only credential redirect
- Enterprise test fixture: `sample-workflow-enterprise-ingest.json`
- User documentation in `docs/`
