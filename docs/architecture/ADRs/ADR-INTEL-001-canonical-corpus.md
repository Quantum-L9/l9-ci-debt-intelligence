# ADR-INTEL-001: Intelligence owns the canonical fleet corpus
- Status: Accepted
- Phase: INTEL-P0
## Decision
`l9-ci-debt-intelligence` owns historical fleet corpus records and
Intelligence-specific schema extensions.
SDK evidence, findings, source locations, snapshots, validation results, and
coverage remain SDK-owned contracts. Intelligence references those contracts;
it does not duplicate them.
Historical mining is an upstream producer of corpus candidates. It does not
create a second corpus or a second ingestion authority; candidates enter only
through the existing INTEL-P1 ingestion service.
## Consequences
Producer payloads retain their public contract identity. Intelligence records
lineage, lifecycle, redaction state, limitations, and correction history
around those payloads.
Current live CI evidence outranks reconstructed historical evidence.
