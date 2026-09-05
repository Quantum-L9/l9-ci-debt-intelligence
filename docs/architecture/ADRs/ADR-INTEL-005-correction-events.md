# ADR-INTEL-005: Corpus history uses correction and retraction events
- Status: Accepted
- Phase: INTEL-P0
## Decision
Historical records are never silently overwritten.
Corrections identify the target record and replacement event. Retractions
identify the target record, issuer, timestamp, and reason. Consumers reconstruct
the current logical view from the append-only event history.
Historical source observations remain observations of what was acquired.
Reconstruction or schema upgrades produce new derived claims; an already
admitted historical claim changes only through the existing corpus correction
or retraction contracts.
