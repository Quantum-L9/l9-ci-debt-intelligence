# ADR-INTEL-026: Historical mining is a bounded upstream producer of INTEL-P1
- Status: Accepted
- Phase: INTEL-P1
## Context
Historical PR and CI evidence can bootstrap the corpus, but a separate corpus,
ingestion service, or storage authority would split Intelligence truth.
## Decision
Historical mining is implemented inside the authoritative
`src/l9_debt_intelligence` package as an upstream producer.
Its only corpus path is historical reconstruction -> Intelligence-owned corpus
event projection -> the existing INTEL-P1 ingestion service.
It owns provider acquisition, safety screening, provider-neutral
normalization, temporal reconstruction, bounded attribution, episode building,
and historical projection. It does not own live resolution, repair execution,
snapshot storage, analytics, rule compilation, publication, or source
repository mutation.
## Consequences
Live CI truth outranks history. SDK canonical semantics are referenced through
public contracts and never cloned. Historical runtime code cannot write the
corpus store or snapshot store directly.
