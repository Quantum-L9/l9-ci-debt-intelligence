from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from l9_debt_intelligence.contracts.canonical import sha256_document

ACQUISITION_SCHEMA = "l9.historical-acquisition-observation/v1"
NORMALIZED_SCHEMA = "l9.historical-normalized-observation/v1"
EPISODE_SCHEMA = "l9.historical-resolution-episode/v1"
COLLECTION_CONTRACT_VERSION = "l9.github-historical-collector/v1"
NORMALIZATION_VERSION = "l9.historical-normalizer/v1"
RECONSTRUCTION_CONTRACT_VERSION = "l9.historical-reconstruction/v1"
RECONSTRUCTION_ALGORITHM_VERSION = "historical-reconstructor/1"

NormalizedKind = Literal[
    "ci_execution",
    "ci_job",
    "failure",
    "commit",
    "change",
    "pull_request",
    "validation",
    "review_signal",
    "textual_hint",
]
Outcome = Literal[
    "clean_verified",
    "target_failure_resolved",
    "repeated_failure",
    "new_failure",
    "partial_resolution",
    "rollback",
    "superseded",
    "unresolved",
    "outcome_unknown",
]
EvidenceGrade = Literal["A", "B", "C", "D", "U"]
AttributionClass = Literal[
    "replay_verified",
    "direct_transition_verified",
    "transition_inferred",
    "textual_hint",
    "unresolved",
]


def deterministic_id(prefix: str, payload: Any) -> str:
    return f"{prefix}{sha256_document(payload)}"


@dataclass(frozen=True)
class AcquisitionObservation:
    provider: str
    repository_ref: str
    object_kind: str
    provider_object_id: str
    observed_content_digest: str
    collection_contract_version: str
    limitations: tuple[str, ...]
    provenance: dict[str, Any]
    payload: Any
    observation_id: str
    schema_version: str = ACQUISITION_SCHEMA

    @classmethod
    def build(
        cls,
        *,
        provider: str,
        repository_ref: str,
        object_kind: str,
        provider_object_id: str,
        payload: Any,
        provenance: dict[str, Any],
        limitations: tuple[str, ...] = (),
        collection_contract_version: str = COLLECTION_CONTRACT_VERSION,
    ) -> AcquisitionObservation:
        content_digest = sha256_document(payload)
        observation_id = deterministic_id(
            "hso_",
            {
                "provider": provider,
                "repository_ref": repository_ref,
                "object_kind": object_kind,
                "provider_object_id": provider_object_id,
                "observed_content_digest": content_digest,
                "collection_contract_version": collection_contract_version,
            },
        )
        return cls(
            provider,
            repository_ref,
            object_kind,
            provider_object_id,
            content_digest,
            collection_contract_version,
            tuple(sorted(set(limitations))),
            provenance,
            payload,
            observation_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "provider": self.provider,
            "repository_ref": self.repository_ref,
            "object_kind": self.object_kind,
            "provider_object_id": self.provider_object_id,
            "observed_content_digest": self.observed_content_digest,
            "collection_contract_version": self.collection_contract_version,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class NormalizedObservation:
    kind: NormalizedKind
    repository_ref: str
    provenance_refs: tuple[str, ...]
    evidence_availability: str
    limitations: tuple[str, ...]
    normalization_version: str
    data: dict[str, Any]
    observation_id: str
    schema_version: str = NORMALIZED_SCHEMA

    @classmethod
    def build(
        cls,
        *,
        kind: NormalizedKind,
        repository_ref: str,
        provenance_refs: tuple[str, ...],
        evidence_availability: str,
        limitations: tuple[str, ...],
        data: dict[str, Any],
        normalization_version: str = NORMALIZATION_VERSION,
    ) -> NormalizedObservation:
        refs = tuple(sorted(set(provenance_refs)))
        limits = tuple(sorted(set(limitations)))
        observation_id = deterministic_id(
            "hno_",
            {
                "kind": kind,
                "repository_ref": repository_ref,
                "provenance_refs": refs,
                "evidence_availability": evidence_availability,
                "limitations": limits,
                "normalization_version": normalization_version,
                "data": data,
            },
        )
        return cls(
            kind,
            repository_ref,
            refs,
            evidence_availability,
            limits,
            normalization_version,
            data,
            observation_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "kind": self.kind,
            "repository_ref": self.repository_ref,
            "provenance_refs": list(self.provenance_refs),
            "evidence_availability": self.evidence_availability,
            "limitations": list(self.limitations),
            "normalization_version": self.normalization_version,
            "data": self.data,
        }


@dataclass(frozen=True)
class ResolutionEpisode:
    episode_id: str
    context: dict[str, Any]
    failure_state: dict[str, Any]
    intervention: dict[str, Any]
    validation: dict[str, Any]
    outcome: Outcome
    attribution: dict[str, Any]
    provenance: dict[str, Any]
    schema_version: str = EPISODE_SCHEMA

    @classmethod
    def build(
        cls,
        *,
        context: dict[str, Any],
        failure_state: dict[str, Any],
        intervention: dict[str, Any],
        validation: dict[str, Any],
        outcome: Outcome,
        attribution: dict[str, Any],
        provenance: dict[str, Any],
        reconstruction_contract_version: str = RECONSTRUCTION_CONTRACT_VERSION,
    ) -> ResolutionEpisode:
        failure_identity = _identity_string(
            failure_state.get("semantic_failure_identity"),
            "semantic_failure_identity",
        )
        repository_ref = _identity_string(
            context.get("repository_ref"), "repository_ref"
        )
        before_revision = _identity_string(
            intervention.get("before_revision"), "before_revision"
        )
        after_revision = _identity_string(
            intervention.get("after_revision"), "after_revision"
        )
        execution = _identity_string(
            validation.get("execution_ref"), "validation_execution_ref"
        )
        episode_id = deterministic_id(
            "hep_",
            {
                "repository_ref": repository_ref,
                "normalized_failure_identity": failure_identity,
                "before_revision": before_revision,
                "after_revision": after_revision,
                "validation_execution_ref": execution,
                "reconstruction_contract_version": reconstruction_contract_version,
            },
        )
        return cls(
            episode_id,
            context,
            failure_state,
            intervention,
            validation,
            outcome,
            attribution,
            provenance,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "context": self.context,
            "failure_state": self.failure_state,
            "intervention": self.intervention,
            "validation": self.validation,
            "outcome": self.outcome,
            "attribution": self.attribution,
            "provenance": self.provenance,
        }


def _identity_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"historical identity input is unavailable: {field}")
    return value
