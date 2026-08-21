# Documentation Conventions

Use these conventions when editing project documentation.

## Documentation Information Architecture

- Keep the top-level `README.md` as a thin entrypoint:
  - project purpose
  - quick start
  - testing commands
  - links to focused guides
- Use `runbooks/RUNBOOK.md` as the central navigation index.
- Keep procedural setup in runbooks.
- Keep environment-specific technical behavior in `local-dev-environment` guides.
- Keep troubleshooting in `docs/TROUBLESHOOTING.md` using symptom -> cause -> fix format.

## Environment Terms

- Local development environment:
  - Docker + LocalStack + OpenSearch running locally.
- Port-forward environment:
  - local scripts targeting remote DEV or UAT OpenSearch through `kubectl port-forward`.
- DEV / UAT:
  - remote Cloud Platform namespaces for non-production testing.

## Environment Variable Naming

- Prefix by domain where possible:
  - `OPENSEARCH_*` for OpenSearch settings
  - `AWS_MOD_PLATFORM_*` for Mod Platform credentials
  - `AWS_CICA_*` for CICA bucket and credentials settings
  - `BEDROCK_*` for Bedrock connector/model settings
- Keep defaults in `.env_template` and `local-dev-environment/.env_template` aligned with documented defaults.
- For local development, default to a single bucket for source and page images unless a split-bucket use case is explicitly required.

## Security and Scanning Source of Truth

- Container vulnerability scanning is performed with Grype through `.github/workflows/scan-container.yml`.
- Dependency override and vulnerability process is documented in `docs/VULNERABILITY_MANAGEMENT.md`.
- Do not introduce alternate scanner language in docs unless CI implementation changes.

## Authoring Style

- Keep sections concise and task-oriented.
- Prefer short imperative commands for setup steps.
- Avoid duplicating troubleshooting blocks across multiple guides.
- Link to canonical docs instead of repeating long operational details.
- Keep command examples copy-paste ready.

## Related Documents

- Runbook index: [/runbooks/RUNBOOK.md](/runbooks/RUNBOOK.md)
- Local runbook: [/runbooks/LOCAL_DEVELOPMENT_RUNBOOK.md](/runbooks/LOCAL_DEVELOPMENT_RUNBOOK.md)
- Remote runbook: [/runbooks/REMOTE_PORT_FORWARDING_RUNBOOK.md](/runbooks/REMOTE_PORT_FORWARDING_RUNBOOK.md)
- Bedrock guide: [/local-dev-environment/BEDROCK_CONNECTOR_README.md](/local-dev-environment/BEDROCK_CONNECTOR_README.md)
- OpenSearch indexes guide: [/local-dev-environment/OPENSEARCH_INDEXES_README.md](/local-dev-environment/OPENSEARCH_INDEXES_README.md)
- Troubleshooting: [/docs/TROUBLESHOOTING.md](/docs/TROUBLESHOOTING.md)
- Vulnerability management: [/docs/VULNERABILITY_MANAGEMENT.md](/docs/VULNERABILITY_MANAGEMENT.md)