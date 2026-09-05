from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import (
    AttributionClass,
    EvidenceGrade,
    NormalizedObservation,
    Outcome,
)
from .equivalence import ValidationEquivalence


@dataclass(frozen=True)
class AttributionAssessment:
    evidence_grade: EvidenceGrade
    attribution_class: AttributionClass
    confounders: tuple[str, ...]
    evidence_completeness: int
    limitations: tuple[str, ...]
    outcome: Outcome
    suspected_flake: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_grade": self.evidence_grade,
            "attribution_class": self.attribution_class,
            "confounders": list(self.confounders),
            "evidence_completeness": self.evidence_completeness,
            "limitations": list(self.limitations),
            "suspected_flake": self.suspected_flake,
        }


def assess_attribution(
    *,
    before_run: NormalizedObservation,
    after_run: NormalizedObservation,
    target_after_job: NormalizedObservation | None,
    all_after_jobs: tuple[NormalizedObservation, ...],
    changes: tuple[NormalizedObservation, ...],
    equivalence: ValidationEquivalence,
    same_revision: bool,
    target_failure_present: bool,
    new_failure_count: int,
    before_failure_count: int = 1,
    extra_confounders: tuple[str, ...] = (),
) -> AttributionAssessment:
    confounders = detect_confounders(
        before_run=before_run,
        after_run=after_run,
        changes=changes,
        same_revision=same_revision,
        before_failure_count=before_failure_count,
        extra_confounders=extra_confounders,
    )
    result = _conclusion(target_after_job)

    if same_revision and result == "success":
        return AttributionAssessment(
            "C",
            "transition_inferred",
            tuple(
                sorted(
                    set(
                        confounders
                        + ("flaky_failure_pattern", "rerun_without_code_change")
                    )
                )
            ),
            min(equivalence.completeness, 70),
            ("same revision fail/pass cannot receive repair credit",),
            "outcome_unknown",
            True,
        )

    if equivalence.status != "equivalent":
        return AttributionAssessment(
            "U",
            "unresolved",
            confounders,
            min(equivalence.completeness, 50),
            tuple(
                sorted(
                    set(
                        equivalence.reasons
                        + ("validation_equivalence_not_proved",)
                    )
                )
            ),
            "outcome_unknown",
            False,
        )

    if "intervention_evidence_missing" in confounders or (
        not same_revision and not changes
    ):
        return AttributionAssessment(
            "U",
            "unresolved",
            tuple(
                sorted(set(confounders + ("intervention_evidence_missing",)))
            ),
            min(equivalence.completeness, 50),
            ("revision changed without complete intervention evidence",),
            "outcome_unknown",
            False,
        )

    if result is None or result in {"cancelled", "timed_out", "skipped"}:
        return AttributionAssessment(
            "U",
            "unresolved",
            confounders,
            min(equivalence.completeness, 60),
            ("validation_outcome_unavailable",),
            "unresolved",
            False,
        )

    target_after_job_id = target_after_job.observation_id if target_after_job else ""
    other_failure = any(
        job.observation_id != target_after_job_id and _conclusion(job) == "failure"
        for job in all_after_jobs
    )

    outcome: Outcome
    if target_failure_present:
        outcome = "repeated_failure"
    elif new_failure_count or other_failure:
        outcome = "new_failure"
    elif result == "success":
        outcome = "clean_verified"
    elif result == "failure":
        outcome = "partial_resolution"
    else:
        outcome = "outcome_unknown"

    if same_revision:
        return AttributionAssessment(
            "C",
            "transition_inferred",
            tuple(sorted(set(confounders + ("rerun_without_code_change",)))),
            min(equivalence.completeness, 75),
            ("rerun without revision change carries no repair credit",),
            outcome if outcome != "clean_verified" else "outcome_unknown",
            False,
        )

    material = {
        "multiple_commits_between_failure_and_success",
        "multiple_failure_fingerprints",
        "dependency_lockfile_change",
        "workflow_definition_change",
        "environment_change",
        "test_change",
        "base_branch_update",
        "merge_commit",
        "squash_merge",
        "force_updated_pr_branch",
        "concurrency_cancellation",
        "provider_missing_attempt_history",
    }
    grade: EvidenceGrade = (
        "C" if material.intersection(confounders) or len(changes) > 1 else "B"
    )
    return AttributionAssessment(
        grade,
        "transition_inferred" if grade == "C" else "direct_transition_verified",
        confounders,
        min(equivalence.completeness, 85 if grade == "C" else 100),
        ("material confounders cap attribution strength",) if grade == "C" else (),
        outcome,
        False,
    )


def detect_confounders(
    *,
    before_run: NormalizedObservation,
    after_run: NormalizedObservation,
    changes: tuple[NormalizedObservation, ...],
    same_revision: bool,
    before_failure_count: int = 1,
    extra_confounders: tuple[str, ...] = (),
) -> tuple[str, ...]:
    confounders = set(extra_confounders)
    if len(changes) > 1:
        confounders.add("multiple_commits_between_failure_and_success")
    if before_failure_count > 1:
        confounders.add("multiple_failure_fingerprints")
    if same_revision:
        confounders.add("rerun_without_code_change")

    for change in changes:
        if change.data.get("dependency_lockfile_change"):
            confounders.add("dependency_lockfile_change")
        if change.data.get("workflow_changed"):
            confounders.add("workflow_definition_change")
        if change.data.get("environment_changed"):
            confounders.add("environment_change")
        if change.data.get("test_changed"):
            confounders.add("test_change")
        if change.data.get("is_merge"):
            confounders.add("merge_commit")

    if (
        "provider_attempt_history_missing" in before_run.limitations
        or "provider_attempt_history_missing" in after_run.limitations
    ):
        confounders.add("provider_missing_attempt_history")
    if (
        before_run.data.get("conclusion") == "cancelled"
        or after_run.data.get("conclusion") == "cancelled"
    ):
        confounders.add("concurrency_cancellation")
    return tuple(sorted(confounders))


def _conclusion(job: NormalizedObservation | None) -> str | None:
    if job is None:
        return None
    value = job.data.get("conclusion")
    return value if isinstance(value, str) else None
