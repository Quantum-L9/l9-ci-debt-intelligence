# Historical Miner Build Brief

## Executive verdict
Historical-mining architecture was reconciled against the current Intelligence repository and implemented as an upstream producer of the existing INTEL-P1 ingress boundary. The candidate is intentionally not fleet-scale. Final repository landing remains subject to the governed PR validation gate.

## Exact initial SHA
`dca5498b11d073a756dd707b212b6c4895ea6d51`

## Donor files used
- `MinerADRs(1).md`, hydration v1 donor and decision history.
- `MinerBuild(1).md`, authoritative hydration v2, which supersedes v1 where semantics differ.

## V1 to V2 supersession disposition
V1's separate immutable source-ledger wording was narrowed to v2's non-authoritative, content-digest-bound acquisition observations and rebuildable acquisition state. V2 trust ordering, pre-normalization safety, quarantine, validation equivalence, bounded attribution, flakiness, corrections/retractions, independence gates, and closed-loop lineage control the implementation.

## Repository architecture before
Intelligence already owned the canonical corpus envelope, deterministic ingestion, quarantine, corrections/retractions, and producer compatibility. SDK semantics were federated. No historical-mining subsystem existed. The existing P1 `IngestionService` was therefore reused rather than cloned.

## Hydrated ADRs and mapping
- HIST-001 -> ADR-INTEL-026 plus extension of ADR-INTEL-001.
- HIST-002/HIST-010 -> ADR-INTEL-027 plus ADR-INTEL-008.
- HIST-003/HIST-008/HIST-009/HIST-011 -> ADR-INTEL-028 plus ADR-INTEL-006.
- HIST-004 -> ADR-INTEL-029 plus ADR-INTEL-023.
- HIST-005 -> ADR-INTEL-030.
- HIST-006 -> ADR-INTEL-026 plus existing P1 authority.
- HIST-007 -> ADR-INTEL-027.
- HIST-012 -> ADR-INTEL-031.
- V2 sample/independence law -> extension of ADR-INTEL-025.
- V2 correction/retraction law -> extension of ADR-INTEL-005.

## Implementation filetree
`src/l9_debt_intelligence/historical/` contains acquisition/checkpointing, GitHub provider isolation, safety/quarantine, provider-neutral normalization, temporal reconstruction, validation equivalence, attribution, flakiness, episode contracts, derived storage, P1 projection, and bootstrap orchestration. Three Intelligence-owned historical schemas live under `schemas/intelligence/`. Adversarial fixture inventory and architecture boundary tests live under `tests/`.

## Contracts added or reused
Added `l9.historical-acquisition-observation/v1`, `l9.historical-normalized-observation/v1`, and `l9.historical-resolution-episode/v1`. Reused `l9.corpus-event/v1`, `l9.integration-contract/v1`, Intelligence repository pseudonymization, canonical hashing, redaction inspection, ingestion result, and the existing P1 ingestion service.

## P1 integration
Historical episodes are projected to the Intelligence-owned corpus envelope and submitted to `IngestionService.ingest`. Historical runtime code has no canonical corpus-store dependency.

## GitHub provider
The adapter owns token use, bounded pagination/retries, pull/commit/run/attempt/job/check acquisition, optional logs, explicit missing-log/attempt limitations, and rate-limit failure. It owns no semantic identity, attribution, admission, or repair strategy.

## Security and quarantine
Provider material is scanned before normalization using Intelligence's existing sensitive-value/path detector. Sensitive observations preserve digest and limitation metadata only. Raw job-log text is never emitted by normalized observations or corpus projection.

## Temporal reconstruction
The subsystem constructs a directed evidence graph and orders revision transitions by Git parent relationships, workflow/run relationships, and attempt number. Ambiguous paths are not guessed.

## Identity model
Provider object, semantic failure, occurrence, execution, delivery, and episode identity remain separate. Historical surrogates are explicitly `historical:` and noncanonical. Episode identity excludes arrival time, local sequence, machine, and checkpoint state.

## Validation equivalence
Successful repair credit requires stable workflow/job/step semantics and rejects removed jobs, validation weakening, workflow changes, and unaccounted environment changes.

## Attribution and confidence
Grades A/B/C/D/U are policy-bearing; numeric completeness is diagnostic only. Same-revision reruns cannot receive repair credit. Multiple interventions and material confounders cap evidence at C. Missing or non-equivalent validation stays U.

## Flakiness
Same-SHA fail/pass is suspected flake; alternating same-SHA outcomes can become verified flake. Flake prevention learning remains separate from repair learning.

## Idempotency
Acquisition, normalized, episode, and corpus identities are deterministic. Duplicate acquisition converges and repeated P1 delivery uses the existing duplicate-record behavior.

## Closed-loop lineage
Optional lineage accepts active defense pack/rules, Resolver strategy source, LSP intervention, and PR Repair intervention. Replay/duplicate/cherry-pick independence remains deferred to fleet analysis but is architecture law.

## Golden and adversarial validation
A reconstructed local harness using the current P1 public seam executed `pytest -q tests/historical tests/architecture/test_historical_boundary.py`: 21 tests plus 6 subtests passed. This proves the local implementation logic, not the remote repository candidate. Remote authoritative CI remains required.

## Deferred scope
Organization scheduler, Harness replay execution, AST change classification, cross-repository clustering, PR Repair learning packets, strategy ranking, historical rule compilation, and fleet-scale orchestration.

## Unresolved UNKNOWNs
Remote lint/mypy/central Core results are UNKNOWN until the governed PR executes. Provider behavior against a real historical repository is not claimed from the local fixture harness.

## Repository landing state
Feature branch created from the exact initial SHA. Candidate publication and merge are governed by the repository's required PR checks and squash-only merge policy.

## Final status
`BLOCKED_BY_VALIDATION` until remote required checks pass; after green checks the intended terminal state is `HISTORICAL_MINER_BUILT_ADRS_HYDRATED_VALIDATED_AND_LANDED`.
