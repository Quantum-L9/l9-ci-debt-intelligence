# ADR-INTEL-027: Historical acquisition, reconstruction, and corpus authority are separated
- Status: Accepted
- Phase: INTEL-P1
## Decision
Provider objects are non-authoritative acquisition observations bound to
content digests and provenance. GitHub authentication, pagination, attempts,
rate-limit state, pulls, commits, runs, jobs, checks, and logs remain behind a
provider adapter.
Historical normalization and reconstruction consume provider-neutral
observations, not GitHub-specific APIs.
Rebuildable normalized observations, graphs, episodes, and quarantine metadata
live outside canonical P1 storage. Checkpoints are operational only and never
identity inputs. Raw logs are not persisted by the historical derived store.
## Consequences
Provider material is data, never executable instruction. Missing provider data
stays explicit. Sensitive material is quarantined before normalization and no
fabricated redacted payload is created.
Changing reconstruction logic may create a new derived version without
rewriting the acquired observation or an accepted corpus record.
