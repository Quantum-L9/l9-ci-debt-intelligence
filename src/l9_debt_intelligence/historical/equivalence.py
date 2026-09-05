from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import NormalizedObservation


@dataclass(frozen=True)
class ValidationEquivalence:
    status: str
    reasons: tuple[str, ...]
    completeness: int

    @property
    def equivalent(self) -> bool:
        return self.status == "equivalent"


def evaluate_validation_equivalence(
    *,
    before_run: NormalizedObservation,
    after_run: NormalizedObservation,
    before_job: NormalizedObservation,
    after_job: NormalizedObservation | None,
    changes: tuple[NormalizedObservation, ...],
) -> ValidationEquivalence:
    reasons: list[str] = []
    completeness = 100
    if before_run.data.get("workflow_identity") != after_run.data.get(
        "workflow_identity"
    ):
        reasons.append("workflow_identity_changed")
    if after_job is None:
        reasons.append("job_removed")
    elif before_job.data.get("name") != after_job.data.get("name"):
        reasons.append("job_semantics_changed")
    if any(bool(change.data.get("workflow_changed")) for change in changes):
        reasons.append("workflow_definition_changed")
    if any(bool(change.data.get("environment_changed")) for change in changes):
        reasons.append("material_environment_change_unaccounted")
    weakening: list[str] = []
    for change in changes:
        value = change.data.get("validation_weakening_signals", [])
        if isinstance(value, list):
            weakening.extend(str(item) for item in value)
    reasons.extend(sorted(set(weakening)))

    if after_job is not None:
        before_steps = _step_names(before_job.data.get("steps"))
        after_steps = _step_names(after_job.data.get("steps"))
        if before_steps and after_steps and before_steps != after_steps:
            reasons.append("validation_contract_changed")
        elif not before_steps or not after_steps:
            completeness -= 15

    if reasons:
        return ValidationEquivalence(
            status="not_equivalent",
            reasons=tuple(sorted(set(reasons))),
            completeness=max(completeness - 35, 0),
        )
    return ValidationEquivalence(
        status="equivalent",
        reasons=(),
        completeness=completeness,
    )


def _step_names(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    output: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            output.append(name)
    return tuple(output)
