# Workflow Fixtures for Testing

The repo includes workflow fixtures for testing audit and migration behavior without touching production n8n data.

## Included Fixtures

- `sample-workflow-all-providers.json`
  - compact mixed-provider fixture
- `sample-workflow-enterprise-ingest.json`
  - larger enterprise-style fixture with native + Pay-i nodes
- `test-workflow-native-providers.json`
  - native provider-oriented test fixture
- `test-workflow-payi-all-providers.json`
  - Pay-i node fixture across providers
- `test-workflow-payi-pipeline.json`
  - pipeline/flow-oriented Pay-i fixture

## Recommended Uses

- unit/integration tests for node detection and classification
- dry-run test cases before applying migration changes
- report-rendering consistency checks (`json` vs `md`)
- regression validation when migration logic changes

## Notes

- Fixtures use placeholder IDs and credentials.
- Replace values only when doing environment-specific test runs.
