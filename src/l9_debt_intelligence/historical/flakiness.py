from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import NormalizedObservation


@dataclass(frozen=True)
class FlakeAssessment:
    classification: str
    indicators: tuple[str, ...]

    @property
    def repair_credit_allowed(self) -> bool:
        return self.classification == "none"


def classify_flakiness(
    *,
    failure_run: NormalizedObservation,
    runs: tuple[NormalizedObservation, ...],
) -> FlakeAssessment:
    revision = failure_run.data.get("revision")
    workflow = failure_run.data.get("workflow_identity")
    relevant = [
        run
        for run in runs
        if run.data.get("revision") == revision
        and run.data.get("workflow_identity") == workflow
    ]
    relevant.sort(
        key=lambda run: (
            _attempt(run.data.get("attempt")),
            str(run.data.get("updated_at") or ""),
            run.observation_id,
        )
    )
    conclusions: list[str] = []
    for run in relevant:
        conclusion = run.data.get("conclusion")
        if isinstance(conclusion, str):
            conclusions.append(conclusion)
    indicators: set[str] = set()
    if "failure" in conclusions and "success" in conclusions:
        indicators.add("fail_then_pass_without_revision_change")
    alternations = sum(
        left != right
        for left, right in zip(conclusions, conclusions[1:], strict=False)
        if left in {"failure", "success"} and right in {"failure", "success"}
    )
    if alternations >= 2:
        indicators.add("alternating_results_same_revision")
    if conclusions.count("failure") >= 2 and "success" in conclusions:
        indicators.add("intermittent_same_failure_same_revision")
    if any(value in {"cancelled", "timed_out"} for value in conclusions):
        indicators.add("cancelled_or_timed_out_attempt")
    if "alternating_results_same_revision" in indicators:
        classification = "verified"
    elif "fail_then_pass_without_revision_change" in indicators:
        classification = "suspected"
    else:
        classification = "none"
    return FlakeAssessment(
        classification=classification,
        indicators=tuple(sorted(indicators)),
    )


def _attempt(value: Any) -> int:
    return value if isinstance(value, int) else 0
