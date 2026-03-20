# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Documentation cross-linking and navigation across all user-facing docs
- `CLAUDE.md` project guidance file
- `SBOM.md` software bill of materials
- `CHANGELOG.md` (this file)

### Changed
- Root `README.md` expanded with full documentation table
- `docs/README.md` rewritten as structured documentation hub with reading order
- All doc pages now include navigation headers and "See Also" footers
- `.gitignore` updated to cover standard project artifacts

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
