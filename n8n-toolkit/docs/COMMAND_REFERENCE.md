# Command Reference

## `audit-configure-payi-proxy.py`

Audit workflows and emit migration/compliance reports.

### Typical Use

```bash
python3 audit-configure-payi-proxy.py --out ./audit.json
```

### Key Options

- `--workflow ID`: analyze only one workflow
- `--from-json PATH`: load an existing JSON report instead of calling n8n API
- `--out PATH`: write report to file
- `--report-format json|md`: output format for `--out`
- `--json`: print report JSON to stdout
- `--configure-credentials`: patch credentials that are marked redirectable
- `--dry-run`: preview credential patch actions without applying
- `--yes`: skip apply confirmation prompt
- `--non-interactive`: fail if required inputs are missing (no prompts)
- `--n8n-base-url URL`, `--n8n-api-key KEY`
- `--payi-base-url URL`, `--payi-api-key KEY`
- `--verbose`: show API call logs
- `--insecure`: disable TLS verification (local/self-signed environments)

### Current Constraints

- `--configure-credentials` cannot be combined with `--from-json`.
- Auto-apply patches only credentials with `redirect_capability=likely_supported`.
- `unverified` credentials require manual validation before apply.
- Detection scope is limited to mapped native/Pay-i node types.
- Full details: [Limitations and Known Issues](./LIMITATIONS_AND_KNOWN_ISSUES.md)

## `migrate-workflows-to-payi.py`

Interactive migration orchestrator for redirect and/or node replacement.

### Typical Use

```bash
python3 migrate-workflows-to-payi.py
```

### Key Options

- `--dry-run`: preview without writing
- `--auto-yes`: skip interactive node/workflow selection where possible
- `--workflow ID`: limit migration to one workflow
- `--strategy redirect|replace|both`: pre-select migration strategy
- `--verbose`: show detailed API logs and credential verification details

### Strategy Modes

- `redirect`: patch redirectable credentials to Pay-i proxy URLs
- `replace`: replace supported nodes with Pay-i nodes
- `both`: run redirect + replacement

## `migrate-to-payi.sh`

Bulk credential redirect script.

### Behavior

- Scans credentials in n8n
- Targets `openAiApi`, `anthropicApi`, `azureOpenAiApi`
- Prompts for provider API key values before patching

## `migrate-openai-to-payi.sh`

OpenAI-only credential redirect script.
