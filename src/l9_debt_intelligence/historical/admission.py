from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from l9_debt_intelligence.ingestion.identity import repository_pseudonym

from .contracts import ResolutionEpisode

HISTORICAL_EVENT_SCHEMA = "l9.historical-resolution-event/v1"
ObservationKind = Literal[
    "CI_failure_classification",
    "repair_attempt",
    "verification_outcome",
]


@dataclass(frozen=True)
class HistoricalResolutionEvent:
    event_id: str
    episode_id: str
    observation_kind: ObservationKind
    occurred_at: str
    repository_identity: str
    snapshot_or_run_id: str
    parent_event_ids: tuple[str, ...]
    failure: dict[str, Any] | None
    intervention: dict[str, Any] | None
    validation: dict[str, Any] | None
    historical_evidence: dict[str, Any]
    source: dict[str, Any]
    limitations: tuple[str, ...]
    unknowns: tuple[dict[str, str], ...]
    provenance: dict[str, Any]
    schema_version: str = HISTORICAL_EVENT_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "episode_id": self.episode_id,
            "observation_kind": self.observation_kind,
            "occurred_at": self.occurred_at,
            "repository_identity": self.repository_identity,
            "snapshot_or_run_id": self.snapshot_or_run_id,
            "parent_event_ids": list(self.parent_event_ids),
            "failure": self.failure,
            "intervention": self.intervention,
            "validation": self.validation,
            "historical_evidence": self.historical_evidence,
            "source": self.source,
            "limitations": list(self.limitations),
            "unknowns": list(self.unknowns),
            "provenance": self.provenance,
        }


class HistoricalEventProjector:
    """Project a reconstructed episode into native historical producer events.

    This boundary intentionally does not know the corpus envelope, P1 record
    identity, observation identity, ledger sequence, quarantine identity, or
    corpus storage. Those remain INTEL-P1 concerns.
    """

    def __init__(self, *, pseudonym_key: bytes) -> None:
        if len(pseudonym_key) < 32:
            raise ValueError("pseudonym key must be at least 32 bytes")
        self._pseudonym_key = pseudonym_key

    def project(self, episode: ResolutionEpisode) -> tuple[HistoricalResolutionEvent, ...]:
        repository = _required_string(episode.context.get("repository_ref"), "repository_ref")
        repository_identity = repository_pseudonym(
            repository=repository,
            pseudonym_key=self._pseudonym_key,
        )
        failure_time = _required_string(
            episode.failure_state.get("provider_time"), "failure provider time"
        )
        intervention_time = _required_string(
            episode.intervention.get("provider_time"), "intervention provider time"
        )
        validation_time = _required_string(
            episode.validation.get("provider_time"), "validation provider time"
        )
        before_execution = _required_string(
            episode.failure_state.get("execution_ref"), "failure execution ref"
        )
        validation_execution = _required_string(
            episode.validation.get("execution_ref"), "validation execution ref"
        )
        relationship = episode.validation.get("equivalent_check_relationship")
        if episode.outcome in {"clean_verified", "target_failure_resolved"}:
            if relationship != "equivalent":
                raise ValueError(
                    "successful historical outcome requires equivalent validation"
                )

        limitations = tuple(
            sorted(
                set(
                    str(item)
                    for item in episode.attribution.get("limitations", [])
                    if isinstance(item, str) and item
                )
                or {"historical evidence is reconstructed and subordinate to live CI"}
            )
        )
        unknowns = _unknowns(episode, relationship)
        evidence = {
            "grade": episode.attribution.get("evidence_grade"),
            "attribution_strength": _attribution_strength(episode),
            "evidence_completeness_percent": episode.attribution.get(
                "evidence_completeness"
            ),
            "replay_fidelity": "not_attempted",
            "suspected_flake": episode.attribution.get("suspected_flake", False),
        }
        provenance = {
            "reconstruction_algorithm": episode.provenance.get("algorithm_version"),
            "reconstruction_contract": episode.provenance.get("schema_version"),
            "source_observation_hashes": episode.provenance.get(
                "source_observation_refs", []
            ),
            "temporal_graph_digest": episode.provenance.get("temporal_graph_digest"),
            "closed_loop_lineage": episode.provenance.get("closed_loop_lineage", {}),
        }
        failure_id = f"historical.{episode.episode_id}.failure"
        repair_id = f"historical.{episode.episode_id}.repair"
        verification_id = f"historical.{episode.episode_id}.verification"
        failure_identity = episode.failure_state.get("semantic_failure_identity")

        failure = HistoricalResolutionEvent(
            event_id=failure_id,
            episode_id=episode.episode_id,
            observation_kind="CI_failure_classification",
            occurred_at=failure_time,
            repository_identity=repository_identity,
            snapshot_or_run_id=f"github-run:{before_execution}",
            parent_event_ids=(),
            failure={
                "semantic_failure_identity": failure_identity,
                "identity_authority": episode.failure_state.get("identity_authority"),
                "occurrence_identities": episode.failure_state.get(
                    "occurrence_identities", []
                ),
            },
            intervention=None,
            validation=None,
            historical_evidence=evidence,
            source=_source(episode, before_execution),
            limitations=limitations,
            unknowns=unknowns,
            provenance=provenance,
        )
        repair = HistoricalResolutionEvent(
            event_id=repair_id,
            episode_id=episode.episode_id,
            observation_kind="repair_attempt",
            occurred_at=intervention_time,
            repository_identity=repository_identity,
            snapshot_or_run_id=f"hist-episode:{episode.episode_id}",
            parent_event_ids=(failure_id,),
            failure={"semantic_failure_identity": failure_identity},
            intervention={
                "before_revision": _digest_revision(
                    episode.intervention.get("before_revision")
                ),
                "after_revision": _digest_revision(
                    episode.intervention.get("after_revision")
                ),
                "change_fingerprint": episode.intervention.get("change_fingerprint"),
                "remediation_class": episode.intervention.get(
                    "remediation_class_optional"
                ),
            },
            validation=None,
            historical_evidence=evidence,
            source=_source(episode, before_execution),
            limitations=limitations,
            unknowns=unknowns,
            provenance=provenance,
        )
        verification = HistoricalResolutionEvent(
            event_id=verification_id,
            episode_id=episode.episode_id,
            observation_kind="verification_outcome",
            occurred_at=validation_time,
            repository_identity=repository_identity,
            snapshot_or_run_id=f"github-run:{validation_execution}",
            parent_event_ids=(repair_id,),
            failure={"semantic_failure_identity": failure_identity},
            intervention=None,
            validation={
                "outcome": episode.outcome,
                "equivalent_validation": relationship == "equivalent",
                "equivalent_check_relationship": relationship,
                "failure_after_state": episode.validation.get("failure_after_state"),
                "newly_observed_failures": episode.validation.get(
                    "newly_observed_failures", []
                ),
                "validation_completeness_percent": episode.validation.get(
                    "validation_completeness"
                ),
            },
            historical_evidence=evidence,
            source=_source(episode, validation_execution),
            limitations=limitations,
            unknowns=unknowns,
            provenance=provenance,
        )
        return failure, repair, verification


def _source(episode: ResolutionEpisode, execution_ref: str) -> dict[str, Any]:
    return {
        "provider": "github",
        "workflow_run_ref": execution_ref,
        "pull_request": episode.context.get("pull_request_ref"),
    }


def _unknowns(
    episode: ResolutionEpisode, relationship: Any
) -> tuple[dict[str, str], ...]:
    values: list[dict[str, str]] = []
    if episode.failure_state.get("identity_authority") == "historical_noncanonical":
        values.append({"field": "canonical_rule_id", "reason": "not_observed"})
    if episode.outcome in {"outcome_unknown", "unresolved"}:
        values.append({"field": "historical_outcome", "reason": "unavailable"})
    if relationship != "equivalent":
        values.append({"field": "validation_equivalence", "reason": "unavailable"})
    return tuple(values)


def _attribution_strength(episode: ResolutionEpisode) -> str:
    grade = episode.attribution.get("evidence_grade")
    return {"A": "strong", "B": "strong", "C": "moderate", "D": "weak"}.get(
        grade, "unknown"
    )


def _digest_revision(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"historical producer field is unavailable: {field}")
    return value
