# Contributing

## Author attribution policy

All commits in this repository should be authored by approved human maintainers.
Do not use bot/agent identities as commit authors.

## Subtree sync for `n8n-toolkit`

Initial import path:
- `n8n-toolkit/`

Update command pattern:

```bash
git subtree pull --prefix=n8n-toolkit <SOURCE_REPO> <BRANCH> --squash
```

Example (local source repo):

```bash
git subtree pull --prefix=n8n-toolkit /Users/swharr/src/pay-i-instrumentation/payi-n8n-toolkit codex/AgentExplore --squash
```

## Recommended local git identity check

```bash
git config user.name
git config user.email
```

Verify identity before commit and push.
