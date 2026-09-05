# ADR-INTEL-023: Unknown or incomplete outcomes are not successful outcomes
- Status: Accepted
- Phase: INTEL-P6
## Decision
`rule_not_evaluated`, `evaluation_incomplete`, and `outcome_unknown` remain
explicit unknown observations.
They cannot increase prevention, repair-success, or quality scores.
Historical ambiguity, missing provider evidence, non-equivalent validation,
and unresolved attribution likewise remain explicit unknowns and cannot be
upgraded to repair success.
## Consequences
Incomplete telemetry lowers evidence coverage rather than producing false
success.
Failure disappearance, an unrelated green check, or a successful merge is not
historical repair proof.
