# Changelog For Operators

This changelog is for platform operators running migrations and audits in n8n environments.
It focuses on operational impact, required actions, and rollout risk.

## 2026-03-04

### Changed
- Documentation cleanup and structure alignment:
  - Simplified root `README.md`
  - Added `docs/COMMAND_REFERENCE.md`
  - Added `docs/LIMITATIONS_AND_KNOWN_ISSUES.md` with customer-safe wording
  - Updated user docs to match current script behavior and flags
  - Expanded fixture documentation
- Moved non-user report artifacts out of repo root into `internal-plans/reports/`

### Operational Impact
- Faster onboarding for operators using the toolkit for the first time
- Lower risk of using outdated command examples
- Clearer separation between customer-facing docs and internal planning docs

### Required Operator Action
- None required.
- Recommended: update any internal runbooks to point to:
  - `docs/GETTING_STARTED.md`
  - `docs/COMMAND_REFERENCE.md`
  - `docs/LIMITATIONS_AND_KNOWN_ISSUES.md`

## 2026-03-02

### Added
- New audit tool: `audit-configure-payi-proxy.py`
  - Workflow/provider inventory
  - Credential redirect capability probing
  - Per-node migration manifest with recommended path and confidence
- Enterprise test fixture: `sample-workflow-enterprise-ingest.json`
- Markdown report generation for audits (`--report-format md`)
- JSON-to-Markdown rendering (`--from-json`) for compliance artifact generation

### Changed
- Documentation consolidated into `docs/` (user/customer-facing)

### Operational Impact
- You can now produce two artifacts per audit run:
  - Programmatic JSON report
  - Human/compliance Markdown report
- Migration recommendation quality is improved with credential capability awareness.

### Required Operator Action
- None required for existing scripts.
- Recommended:
  1. Add `audit-configure-payi-proxy.py` to pre-migration checks.
  2. Store both `.json` and `.md` audit artifacts for each migration batch.

### Known Limitations
- Some n8n instances do not expose credential detail fields over API, resulting in `unverified` capability status.
- `unverified` credentials should be validated before automated redirect writes.
