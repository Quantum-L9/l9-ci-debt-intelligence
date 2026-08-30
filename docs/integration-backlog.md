# Integration backlog: declared producers that are not active in v0.1

`.l9/producer-compatibility.json` is the machine-readable statement of which
upstream repositories may feed the corpus. It once named five producers. A
token search across every repository in the constellation found that four of the
five contracts it attributed to those producers exist nowhere but this
repository's own contracts, documentation, and fixtures — the named
repositories have never emitted them.

Those four entries are retained in the registry as reviewable architecture
intent, marked `"status": "planned"`, and refused at ingestion. Marking rather
than deleting keeps the intended shape of the integration visible; refusing
means a declaration cannot be mistaken for a live channel.

## Active in v0.1

| Producer | Contract | Event classes |
|---|---|---|
| `Quantum-L9/l9-ci-sdk` | `l9.finding-bundle/v1` | `static_finding` |

This is the only production-compatible corpus input. Every learning metric,
candidate rule, and defense pack downstream derives from it.

## Planned, not active in v0.1

These contracts are architecture intent only. They are not emitted by the named
repositories and must not be treated as production-compatible inputs.

| Producer | Contract | Why it is not active |
|---|---|---|
| `Quantum-L9/l9-ci-core` | `l9.core-gate-event/v1` | `l9-ci-core` does not emit the contract. It orchestrates `l9-ci-sdk` and routes artifacts to CI storage; it has no corpus emitter. |
| `Quantum-L9/l9-ci-debt-resolver` | `l9.resolver-corpus-event/v1` | The resolver does not emit the contract. Its classification and remediation results stay local. |
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
