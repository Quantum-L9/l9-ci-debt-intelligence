from __future__ import annotations

from l9_debt_intelligence.historical.attribution import assess_attribution
from l9_debt_intelligence.historical.contracts import NormalizedObservation
from l9_debt_intelligence.historical.equivalence import (
    evaluate_validation_equivalence,
)


def _obs(kind: str, data: dict, observation_id: str = "o1") -> NormalizedObservation:
    return NormalizedObservation.build(
        kind=kind,  # type: ignore[arg-type]
        repository_ref="Quantum-L9/l9-ci-debt-intelligence",
        provenance_refs=(observation_id,),
        evidence_availability="complete",
        limitations=(),
        data=data,
    )


def test_skipped_step_is_not_equivalent() -> None:
    before_job = _obs(
        "ci_job",
        {
            "name": "test",
            "steps": [
                {"name": "pytest", "conclusion": "success", "status": "completed"}
            ],
        },
        "bj",
    )
    after_job = _obs(
        "ci_job",
        {
            "name": "test",
            "steps": [
                {"name": "pytest", "conclusion": "skipped", "status": "completed"}
            ],
        },
        "aj",
    )
    run = _obs("ci_execution", {"workflow_identity": "ci"}, "r")
    result = evaluate_validation_equivalence(
        before_run=run,
        after_run=run,
        before_job=before_job,
        after_job=after_job,
        changes=(),
    )
    assert result.status == "not_equivalent"
    assert "validation_contract_changed" in result.reasons


def test_empty_file_count_denies_repair_credit() -> None:
    run = _obs(
        "ci_execution", {"workflow_identity": "ci", "conclusion": "success"}, "r"
    )
    job = _obs("ci_job", {"conclusion": "success"}, "j")
    change = _obs("change", {"file_count": 0, "change_fingerprint": "abc"}, "c")
    eq = evaluate_validation_equivalence(
        before_run=run,
        after_run=run,
        before_job=job,
        after_job=job,
        changes=(change,),
    )
    assessment = assess_attribution(
        before_run=run,
        after_run=run,
        target_after_job=job,
        all_after_jobs=(job,),
        changes=(change,),
        equivalence=eq,
        same_revision=False,
        target_failure_present=False,
        new_failure_count=0,
    )
    assert assessment.outcome == "outcome_unknown"
    assert "intervention_evidence_missing" in assessment.confounders
