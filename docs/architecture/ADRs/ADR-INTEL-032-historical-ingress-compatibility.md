# ADR-INTEL-032: Historical ingress compatibility is executable against P1

- Status: Accepted
- Date: 2026-09-05

## Decision

Historical mining owns reconstruction semantics. INTEL-P1 owns corpus semantics. The only allowed bridge is a versioned native historical producer contract validated by an Intelligence-owned consumer adapter and exercised against the real P1 ingestion service.

A `HistoricalResolutionEpisode` is a reconstruction aggregate, not a corpus event. Before admission it projects deterministically into native `l9.historical-resolution-event/v1` observations using the existing corpus event semantics `CI_failure_classification`, `repair_attempt`, and `verification_outcome`. The adapter preserves each native event whole in `payload`, attaches a producer-event hash and parent-event lineage, and only then constructs `l9.corpus-event/v1` for `IngestionService.ingest()`.

Historical event time is the original source occurrence time. Mining/import time must never substitute for failure, intervention, or verification time. `snapshot_or_run_id` is derived from stable historical identity and must not contain bootstrap execution identity.

## Miner must not

- emit a corpus record;
- compute P1 `record_id`;
- compute P1 ingestion `observation_id`;
- assign ledger sequence;
- compute quarantine identity;
- bypass event validation;
- bypass redaction assessment;
- bypass producer compatibility;
- fabricate SDK-owned fields;
- persist raw logs in corpus payloads.

## Adapter must

- validate the native historical event against the Intelligence consumer view;
- preserve the complete native event in corpus `payload`;
- map only into existing event classes;
- preserve explicit unknowns and limitations;
- attach `producer_event_hash` and `parent_event_ids`;
- reject floating-point diagnostics before P1;
- invoke the real `IngestionService` through the bootstrap path.

## Compatibility gate

CI must exercise the real P1 schema, producer registry, normalizer, redaction assessment, identity implementation, and `IngestionService`. At minimum it proves:

1. valid failure, repair, and verification events are accepted;
2. exact repeat delivery is duplicate with stable record identity;
3. an incompatible producer contract is quarantined;
4. sensitive native content is quarantined;
5. deterministic native input produces deterministic corpus projection;
6. historical runtime code does not own P1 record/storage identity.

No fake ingestion mock may satisfy this compatibility gate.

## Consequences

P1 itself becomes the executable specification for miner admission. Historical reconstruction can evolve independently, additive native producer fields can pass through the consumer subset, and corpus authority remains singular. A producer/consumer drift that P1 cannot accept fails before the historical subsystem can claim completion.
