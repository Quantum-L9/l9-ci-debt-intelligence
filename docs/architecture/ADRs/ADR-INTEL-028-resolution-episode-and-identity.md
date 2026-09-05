# ADR-INTEL-028: Resolution episodes are the historical learning atom
- Status: Accepted
- Phase: INTEL-P1
## Decision
A PR is context, not the historical learning unit. The learning unit is a
deterministic `l9.historical-resolution-episode/v1` describing failure state,
intervention, materially comparable validation, outcome, attribution, and
provenance.
Semantic failure identity is separate from occurrence, execution, delivery,
and episode identity. SDK canonical identity is preferred when available;
otherwise historical mining may create a collision-resistant surrogate under
the `historical:` namespace that is explicitly noncanonical.
Episode identity binds repository, normalized failure identity, before and
after revisions, validation execution, and reconstruction contract version.
## Consequences
One PR may contain multiple episodes. Failed interventions, regressions, and
partial resolutions remain first-class evidence. Arrival time and machine
identity cannot change an episode identity.
