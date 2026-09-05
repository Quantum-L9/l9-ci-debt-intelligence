from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from l9_debt_intelligence.ingestion.redaction import inspect_value

from .contracts import AcquisitionObservation


@dataclass(frozen=True)
class QuarantinedObservation:
    observation_id: str
    observed_content_digest: str
    reason: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "observed_content_digest": self.observed_content_digest,
            "reason": self.reason,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class SafetyScreenResult:
    safe: tuple[AcquisitionObservation, ...]
    quarantined: tuple[QuarantinedObservation, ...]


def screen_observation(
    observation: AcquisitionObservation,
) -> AcquisitionObservation | QuarantinedObservation:
    findings = tuple(sorted(set(inspect_value(observation.payload))))
    if findings:
        return QuarantinedObservation(
            observation_id=observation.observation_id,
            observed_content_digest=observation.observed_content_digest,
            reason="sensitive_content",
            limitations=findings,
        )
    return observation


def screen_observations(
    observations: tuple[AcquisitionObservation, ...],
) -> SafetyScreenResult:
    digests_by_id: dict[str, set[str]] = {}
    for observation in observations:
        digests_by_id.setdefault(observation.observation_id, set()).add(
            observation.observed_content_digest
        )
    collision_ids = {
        observation_id
        for observation_id, digests in digests_by_id.items()
        if len(digests) > 1
    }

    safe_by_id: dict[str, AcquisitionObservation] = {}
    quarantined: list[QuarantinedObservation] = []
    for observation in observations:
        if observation.observation_id in collision_ids:
            quarantined.append(
                QuarantinedObservation(
                    observation_id=observation.observation_id,
                    observed_content_digest=observation.observed_content_digest,
                    reason="source_identity_collision",
                    limitations=(
                        "one logical source identity was supplied with "
                        "different content digests",
                    ),
                )
            )
            continue
        result = screen_observation(observation)
        if isinstance(result, QuarantinedObservation):
            quarantined.append(result)
        else:
            safe_by_id[result.observation_id] = result
    return SafetyScreenResult(
        safe=tuple(safe_by_id[key] for key in sorted(safe_by_id)),
        quarantined=tuple(
            sorted(
                quarantined,
                key=lambda item: (item.observation_id, item.observed_content_digest),
            )
        ),
    )
