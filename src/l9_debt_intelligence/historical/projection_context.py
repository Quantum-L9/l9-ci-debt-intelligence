from __future__ import annotations

from dataclasses import replace
from typing import Any

from .contracts import NormalizedObservation, ResolutionEpisode


def hydrate_projection_context(
    episode: ResolutionEpisode,
    observations: tuple[NormalizedObservation, ...],
) -> ResolutionEpisode:
    """Attach source-derived occurrence times required by the native event contract.

    Reconstruction remains the owner of episode semantics. This function only
    resolves projection metadata already present in the normalized evidence set;
    it never substitutes mining/import time.
    """
    by_id = {item.observation_id: item for item in observations}
    failure_refs = episode.failure_state.get("failure_refs", [])
    failure = next(
        (by_id[ref] for ref in failure_refs if isinstance(ref, str) and ref in by_id),
        None,
    )
    failure_execution = _string(failure.data.get("execution_ref")) if failure else None
    failure_job_ref = _string(failure.data.get("job_ref")) if failure else None
    failure_time = _job_time(observations, failure_execution, failure_job_ref)
    if failure_time is None:
        failure_time = _run_time(observations, failure_execution)

    after_revision = _string(episode.intervention.get("after_revision"))
    intervention_time = _commit_time(observations, after_revision)
    if intervention_time is None:
        intervention_time = _run_time(
            observations,
            _string(episode.validation.get("execution_ref")),
        )

    failure_state = dict(episode.failure_state)
    failure_state["execution_ref"] = failure_execution
    failure_state["provider_time"] = failure_time
    intervention = dict(episode.intervention)
    intervention["provider_time"] = intervention_time
    return replace(
        episode,
        failure_state=failure_state,
        intervention=intervention,
    )


def _job_time(
    observations: tuple[NormalizedObservation, ...],
    execution_ref: str | None,
    job_ref: str | None,
) -> str | None:
    for item in observations:
        if item.kind != "ci_job":
            continue
        if item.data.get("execution_ref") != execution_ref:
            continue
        if job_ref is not None and item.data.get("job_ref") != job_ref:
            continue
        return _string(item.data.get("completed_at")) or _string(
            item.data.get("started_at")
        )
    return None


def _run_time(
    observations: tuple[NormalizedObservation, ...], execution_ref: str | None
) -> str | None:
    for item in observations:
        if item.kind == "ci_execution" and item.data.get("execution_ref") == execution_ref:
            return _string(item.data.get("updated_at")) or _string(
                item.data.get("created_at")
            )
    return None


def _commit_time(
    observations: tuple[NormalizedObservation, ...], revision: str | None
) -> str | None:
    for item in observations:
        if item.kind == "commit" and item.data.get("revision") == revision:
            return _string(item.data.get("committed_at"))
    return None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
