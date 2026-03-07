# payi-n8n-toolkit

Toolkit for migrating and auditing n8n AI workflows to route through Pay-i.

Use this repo when you need to:
- inventory where AI providers are used in n8n,
- generate migration plans and compliance artifacts,
- redirect credentials to Pay-i proxy,
- replace supported native nodes with Pay-i nodes.

For the Pay-i n8n node package itself, see [n8n-nodes-payi](https://github.com/pay-i/n8n-nodes-payi).

## Documentation

- User docs: [`docs/README.md`](./docs/README.md)
- Limitations/known issues: [`docs/LIMITATIONS_AND_KNOWN_ISSUES.md`](./docs/LIMITATIONS_AND_KNOWN_ISSUES.md)

## Main Scripts

| Script | Purpose |
|---|---|
| `audit-configure-payi-proxy.py` | Read workflows, analyze providers/actions, probe credential redirect capability, emit JSON/Markdown reports, optionally patch redirectable credentials |
| `migrate-workflows-to-payi.py` | Interactive migration flow with strategy selection (`redirect`, `replace`, `both`) |
| `migrate-to-payi.sh` | Credential redirect for OpenAI, Anthropic, Azure OpenAI |
| `migrate-openai-to-payi.sh` | Credential redirect for OpenAI only |

## Quick Start

1. Audit first:

```bash
python3 audit-configure-payi-proxy.py --out ./audit.json
```

2. Generate a human-readable report:

```bash
python3 audit-configure-payi-proxy.py \
  --from-json ./audit.json \
  --report-format md \
  --out ./audit.md
```

3. Run interactive migration:

```bash
python3 migrate-workflows-to-payi.py
```

## Notes

- Scripts are interactive by default and will prompt for missing required values.
- For CI/pipelines, use non-interactive inputs (environment variables and flags).
- Provider support depends on both this toolkit and the installed `n8n-nodes-payi` version.

## License

MIT
