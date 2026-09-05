# ADR-INTEL-031: Historical mining starts with one fail-intervention-validation vertical slice
- Status: Accepted
- Phase: INTEL-P1
## Decision
The first historical-mining release proves one deterministic repository-level
failure -> intervention -> materially equivalent validation path through the
real INTEL-P1 ingestion boundary.
The MVP includes Intelligence-owned historical contracts, bounded GitHub
acquisition, checkpointing, pre-normalization safety screening,
provider-neutral normalization, a directed temporal evidence graph, failure
identity resolution, validation equivalence, confounder and flake handling,
episode construction, corpus projection, and adversarial/architecture tests.
Organization-wide scheduling, Harness replay, AST classification,
cross-repository clustering, PR Repair learning packets, automated strategy
ranking, historical rule compilation, and fleet-scale orchestration remain
deferred.
## Consequences
The vertical slice must prove deterministic provenance, byte-equivalent episode
reconstruction, idempotent P1 projection, and rejection of false repair credit
before fleet scale is admitted.
