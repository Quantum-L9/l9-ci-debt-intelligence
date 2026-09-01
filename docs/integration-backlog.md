# Integration backlog: declared producers that are not active in v0.1

`.l9/producer-compatibility.json` is the machine-readable statement of which
upstream repositories may feed the corpus. It once named five producers. A
token search across every repository in the constellation found that four of the
five contracts it attributed to those producers exist nowhere but this
repository's own contracts, documentation, and fixtures — the named
repositories have never emitted them.

One of those four turned out to be a mis-declaration rather than a gap.
`l9-ci-debt-resolver` emits nothing called `l9.resolver-corpus-event/v1`, but it
does emit `l9.intelligence-feedback-event/v1`, complete with deterministic event
identity, an idempotency key, a durable outbox, dead-letter handling, producer
privacy validation, and both a JSON-file and an HTTPS transport — the latter
already aimed at this repository. The missing piece was never a producer; it was
a projection onto the envelope Intelligence owns. That projection now exists as
`ResolverFeedbackAdapter`, and the resolver is active against the contract it
actually ships.

The remaining three entries are retained in the registry as reviewable
architecture intent, marked `"status": "planned"`, and refused at ingestion.
Marking rather than deleting keeps the intended shape of the integration
visible; refusing means a declaration cannot be mistaken for a live channel.

## Active in v0.1

| Producer | Contract | Event classes |
|---|---|---|
| `Quantum-L9/l9-ci-sdk` | `l9.finding-bundle/v1` | `static_finding` |
| `Quantum-L9/l9-ci-debt-resolver` | `l9.intelligence-feedback-event/v1` | `verification_outcome` |

These are the production-compatible corpus inputs. Every learning metric,
candidate rule, and defense pack downstream derives from them.

### How the resolver seam is wired

```
resolution outcome
  → l9.intelligence-feedback-event/v1     (producer-owned, privacy validated)
  → durable outbox
  → JSON-file or HTTPS transport
  → ResolverFeedbackAdapter               (Intelligence-owned projection)
  → l9.corpus-event/v1
  → IngestionService
  → corpus / analytics / learning
```

The producer's document is carried into `payload` whole — never flattened —
so failure fingerprint and category, resolution terminal state, validation
outcome, finding and contract identifiers, capability profile, hashed
provenance and the idempotency key all survive for downstream learning.
`lineage.producer_event_hash` is the SHA-256 of the canonical producer document,
binding the corpus record to the exact bytes the resolver emitted.

Intelligence validates the incoming document against
`schemas/intelligence/consumers/resolver-feedback.schema.json` — deliberately a
compatibility *subset*, not a copy of the resolver's authoritative schema.
Unknown properties pass through at every level, so an additive, backwards
compatible producer extension does not break ingestion. The resolver remains
the sole authority for `l9.intelligence-feedback-event/v1`; Intelligence
declares only what it reads or carries.

Run the seam with:

```bash
l9-intelligence ingest-resolver-feedback feedback-event.json --storage-root ./corpus
```

Duplicate handling is the producer's already: an identical replay through the
resolver's file transport answers `409`, and an identical replay through
ingestion resolves to the same corpus record with a second ledger observation.
Retries are bounded by the resolver's outbox, so Intelligence adds no second
retry mechanism.

### Over the wire

The same adapter serves the resolver's `HTTPSFeedbackTransport`:

```bash
L9_INTELLIGENCE_INGRESS_TOKEN=<token> \
  l9-intelligence serve-feedback-ingress --storage-root ./corpus
```

```
l9-debt-resolver publish-feedback --transport https \
  --destination https://<intelligence>/api/v1/events
        |
        v
POST /api/v1/events   bearer auth - Idempotency-Key - 1 MiB body bound
        |
        v
ResolverFeedbackAdapter -> IngestionService -> corpus
```

The HTTP layer owns no learning logic and, deliberately, **no retry**. The
producer's transport already classifies every response, so the ingress answers
only in that vocabulary:

| Status | Meaning | Producer's reading |
|---|---|---|
| `201` | accepted | success |
| `409` | duplicate | success — duplicate acknowledgement |
| `422` | contract violation, or quarantined at ingestion | permanent → dead-letter |
| `401` | bearer authentication failed | permanent → dead-letter |
| `413` | body exceeds the size bound | permanent → dead-letter |
| `503` | ingestion storage unavailable | retryable → bounded by the outbox |

`401`, `413` and `422` are deliberately *outside* the producer's retryable set:
retrying a bad credential or a malformed document can never succeed, and would
burn a bounded outbox budget that a real outage needs. Retry and backoff belong
to the resolver's durable outbox; a second mechanism here would fight it. A test
asserts the ingress contains no retry, backoff, or queue construct.

It is built on the standard library — no web framework, so no new runtime
dependency — and terminates no TLS. The resolver refuses any endpoint that is
not `https://`, so the ingress is designed to sit behind TLS termination.

### Not yet: effectiveness

Resolver feedback lands in the **corpus**. It is not routed into
`l9.effectiveness-outcome/v1`, whose schema requires `pack_id`, `pack_version`,
and `canonical_rule_id` for every observation — fields the resolver's feedback
contract does not carry. A resolver outcome becomes an effectiveness
observation only once it can be proven to correspond to a deployed defense
pack and rule. Fabricating those identifiers to satisfy the Phase 7 schema
would convert *unknown* into a false measurement, which the effectiveness
contract prohibits.

## Planned, not active in v0.1

These contracts are architecture intent only. They are not emitted by the named
repositories and must not be treated as production-compatible inputs.

| Producer | Contract | Why it is not active |
|---|---|---|
| `Quantum-L9/l9-ci-core` | `l9.core-gate-event/v1` | `l9-ci-core` does not emit the contract. It orchestrates `l9-ci-sdk` and routes artifacts to CI storage; it has no corpus emitter. |
| `Quantum-L9/PR_Repair` | `l9.repair-learning-packet/v1` | `PR_Repair` does not emit the contract, and in v0.1 it is a standalone PR assistant outside the debt pipeline entirely. |
| `Quantum-L9/l9-ci-debt-lsp` | `l9.editor-outcome-event/v1` | The LSP does not emit the contract. Its real seam is consuming defense packs, not producing corpus events. |

## Closing an entry

An entry moves from `planned` to `active` when, and only when, the named
repository actually emits the declared contract:

1. Implement the emitter in the producing repository against the declared token.
2. Add a fixture under `tests/fixtures/producers/` carrying real producer output.
3. Flip `"status"` to `"active"` in `.l9/producer-compatibility.json`.
4. Update `tests/contracts/test_producer_status.py`, which asserts the active
   and planned sets, so the change is deliberate rather than incidental.

The alternative is equally acceptable: if a contract is abandoned rather than
deferred, delete the entry. What is not acceptable is leaving it declared as
active, which asserts an integration that does not exist.
