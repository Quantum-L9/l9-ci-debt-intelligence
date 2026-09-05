# ADR-INTEL-029: Repair credit requires materially equivalent validation
- Status: Accepted
- Phase: INTEL-P1
## Decision
A later green result supports `clean_verified`, `target_failure_resolved`, or
evidence grade A/B only when the failure-observing and post-intervention
validation are materially equivalent in workflow identity, job semantics,
validation contract, relevant configuration, required gate presence, and
target failure scope.
Removed jobs, disabled tests, skipped gates, material unaccounted environment
changes, and missing target validation are non-equivalent.
Evidence grades are policy-bearing: A replay-verified, B direct transition,
C inferred transition, D textual hint, U unresolved. Numeric completeness is
diagnostic only.
## Consequences
Rerun-without-change is a flake signal, not repair credit. Multiple
interventions or material confounders cap attribution at C; missing or
non-equivalent evidence remains U. New failures, repeated failures, validation
weakening, and ineffective interventions are retained rather than laundered
into success.
