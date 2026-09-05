# ADR-INTEL-025: Rollback and retirement recommendations require minimum samples
- Status: Accepted
- Phase: INTEL-P6
## Decision
Rule-level recommendations require at least 20 observations. Pack-level
recommendations require at least 100 observations.
Below those thresholds the state is `insufficient_evidence`, even when the
observed ratio appears poor.
Historical evidence preserves the same minimum-sample authority. Duplicate
delivery, retries of one failure at one revision, replay of the same episode,
and cherry-picks of the same patch are related evidence and do not count as
independent samples.
## Consequences
Small-sample noise cannot automatically escalate to rollback or retirement.
A single historical repair can remain a useful example without becoming a
generalized prevention rule.
