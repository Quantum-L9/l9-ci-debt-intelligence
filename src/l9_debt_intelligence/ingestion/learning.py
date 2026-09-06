"""Project one corpus event onto the learning observations it contains.

A corpus record is one immutable fact about one delivery: who produced it, under
which contract, and the hash of what arrived. That is the right shape for an
append-only ledger and the wrong shape for learning from, because a single
delivery can describe many independent things. An SDK finding bundle carrying
thirteen findings is thirteen observations of recurring debt, not one.

Phase 3 has always expected the finer grain. `analytics/projection.py` reads
`occurrence_scope`, `recurrence_fingerprint`, `canonical_rule_id`,
`effort_minutes`, `remediation_class`, `validation_outcome` and
`false_positive_disposition` off snapshot rows, and
`schemas/intelligence/learning-observation.schema.json` has always declared
them. Nothing wrote them. Every fallback in that reader fired for every record
from every producer: `occurrence_scope` degraded to `record:<record_id>` so each
record was its own scope, and `recurrence_fingerprint` degraded to a hash of the
payload so each record was unique. Recurrence and scope breadth could never
aggregate, three of the five candidate score components were structurally zero,
and no candidate could exceed 0.35 against a promotion threshold of 4.0.

This module is the missing projection. It runs at ingestion, where the payload
is still in hand -- the store deliberately keeps only a content hash, so this
cannot be recovered later from the corpus.

Recurrence key
--------------
`recurrence_fingerprint` answers "is this the same kind of debt", and
`occurrence_scope` answers "where". They must stay independent: `recurrence_rows`
groups by fingerprint and then counts the distinct scopes inside each group, so a
fingerprint that folded the scope in would put exactly one scope in every group
and `distinct_scope_count` would be permanently 1. Fleet breadth is the thing
being measured; it cannot be part of the key.

For the same reason the key is the canonical *rule* identity, not the producer's
per-finding fingerprint. The SDK's `fingerprint` is an instance identity -- in a
real bundle, nine findings of `AST-LOGGING-001` carry nine distinct fingerprints
-- so keying on it would prevent aggregation even within one repository. It is
used only when no canonical rule id is available, and that is recorded as a
limitation rather than passed off as recurrence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from l9_debt_intelligence.contracts.errors import ContractError

SCHEMA_VERSION = "l9.learning-observation/v1"
DEFAULT_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "schemas/intelligence/learning-observation.schema.json"
)

SDK_CONTRACT = "l9.finding-bundle/v1"
RESOLVER_CONTRACT = "l9.intelligence-feedback-event/v1"
HISTORICAL_CONTRACT = "l9.historical-resolution-event/v1"

#: Namespaces the recurrence key so two producers cannot collide on a shared
#: token, and so the derivation can be versioned without silently re-keying an
#: existing corpus.
_RULE_NAMESPACE = "l9.recurrence/v1:canonical-rule"
_INSTANCE_NAMESPACE = "l9.recurrence/v1:producer-fingerprint"
_FAILURE_NAMESPACE = "l9.recurrence/v1:failure-fingerprint"
_RECORD_NAMESPACE = "l9.recurrence/v1:record"

_VALIDATION_OUTCOMES = frozenset({"passed", "failed", "partial", "unknown"})

#: Reconstructed episode outcomes, mapped onto the learning vocabulary.
#: `clean_verified` and `target_failure_resolved` are the two the miner emits
#: for a validated repair; everything else is an explicit non-success, and
#: anything absent from this table becomes `unknown` rather than a guess.
_HISTORICAL_OUTCOMES: Mapping[str, str] = {
    "clean_verified": "passed",
    "target_failure_resolved": "passed",
    "repeated_failure": "failed",
    "new_failure": "failed",
    "outcome_unknown": "unknown",
    "unresolved": "unknown",
}


class LearningProjectionError(ContractError):
    """The event cannot be projected onto learning observations."""


def _digest(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}\0{value}".encode()).hexdigest()


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _scope(payload: Mapping[str, Any], record_id: str) -> tuple[str, list[str]]:
    """The repository pseudonym, or an honest per-record fallback.

    A missing pseudonym is not fatal -- the observation is still a real
    observation -- but it is recorded, because a corpus silently full of
    single-record scopes looks identical to a corpus with no recurrence.
    """
    pseudonym = _text(payload.get("repository_pseudonym"))
    if pseudonym is not None:
        return pseudonym, []
    return (
        f"record:{record_id}",
        ["repository pseudonym unavailable; occurrence scope is record-local"],
    )


def _observation(
    *,
    record_id: str,
    producer_id: str,
    event_class: str,
    producer_contract: str,
    occurrence_scope: str,
    recurrence_fingerprint: str,
    canonical_rule_id: str | None = None,
    repository_identity: str | None = None,
    component: str | None = None,
    remediation_class: str | None = None,
    effort_minutes: int | None = None,
    validation_outcome: str | None = None,
    false_positive_disposition: str | None = None,
    pack_version: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "producer_id": producer_id,
        "event_class": event_class,
        "producer_contract": producer_contract,
        "occurrence_scope": occurrence_scope,
        "recurrence_fingerprint": recurrence_fingerprint,
        "canonical_rule_id": canonical_rule_id,
        "repository_identity": repository_identity,
        "component": component,
        "remediation_class": remediation_class,
        "effort_minutes": effort_minutes,
        "validation_outcome": validation_outcome,
        "false_positive_disposition": false_positive_disposition,
        "pack_version": pack_version,
    }


def _finding_bundle_observations(
    event: Mapping[str, Any],
    *,
    record_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise LearningProjectionError("finding-bundle event has no payload object")
    bundle = payload.get("bundle")
    if not isinstance(bundle, Mapping):
        raise LearningProjectionError("finding-bundle payload has no bundle object")
    findings = bundle.get("findings")
    if not isinstance(findings, Sequence) or isinstance(findings, str | bytes):
        raise LearningProjectionError("finding-bundle has no findings array")

    scope, limitations = _scope(payload, record_id)
    observations: list[dict[str, Any]] = []
    without_rule_id = 0

    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        canonical_rule_id = _text(finding.get("canonical_rule_id"))
        if canonical_rule_id is not None:
            fingerprint = _digest(_RULE_NAMESPACE, canonical_rule_id)
        else:
            without_rule_id += 1
            instance = (
                _text(finding.get("fingerprint"))
                or _text(finding.get("finding_id"))
                or record_id
            )
            fingerprint = _digest(_INSTANCE_NAMESPACE, instance)
        # The location path is already a keyed token by the time it reaches
        # here, so it is a privacy-safe stable identity for "the same file".
        component = None
        locations = finding.get("locations")
        if isinstance(locations, Sequence) and not isinstance(locations, str | bytes):
            for location in locations:
                if isinstance(location, Mapping):
                    component = _text(location.get("normalized_path"))
                    break
        observations.append(
            _observation(
                record_id=record_id,
                producer_id=str(event["producer_id"]),
                event_class=str(event["event_class"]),
                producer_contract=SDK_CONTRACT,
                occurrence_scope=scope,
                recurrence_fingerprint=fingerprint,
                canonical_rule_id=canonical_rule_id,
                repository_identity=_text(payload.get("repository_pseudonym")),
                component=component,
            )
        )

    if without_rule_id:
        limitations.append(
            f"{without_rule_id} finding(s) carried no canonical_rule_id; "
            "recurrence for those is instance-level and will not aggregate"
        )
    if not observations:
        limitations.append("finding bundle contained no findings")
    return observations, limitations


def _resolver_feedback_observations(
    event: Mapping[str, Any],
    *,
    record_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """One verification outcome is one observation.

    Unlike a finding bundle this event describes a single resolution attempt, so
    the grain already matches; what this adds is the learning dimensions the
    resolver already carries and nothing read.
    """
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise LearningProjectionError("resolver feedback event has no payload object")

    scope, limitations = _scope(payload, record_id)
    failure = payload.get("failure")
    failure_fingerprint = (
        _text(failure.get("fingerprint")) if isinstance(failure, Mapping) else None
    )
    if failure_fingerprint is not None:
        fingerprint = _digest(_FAILURE_NAMESPACE, failure_fingerprint)
    else:
        fingerprint = _digest(_RECORD_NAMESPACE, record_id)
        limitations.append(
            "resolver event carried no failure fingerprint; recurrence is record-local"
        )

    resolution = payload.get("resolution")
    remediation_class = (
        _text(resolution.get("remediation_class"))
        if isinstance(resolution, Mapping)
        else None
    )
    validation = payload.get("validation")
    validation_outcome = (
        _text(validation.get("result")) if isinstance(validation, Mapping) else None
    )
    if (
        validation_outcome is not None
        and validation_outcome not in _VALIDATION_OUTCOMES
    ):
        limitations.append(
            f"resolver validation result {validation_outcome!r} is not a "
            "learning-observation outcome; recorded as unknown"
        )
        validation_outcome = "unknown"

    # The resolver reports effort as a bucket, never as minutes. Representing a
    # bucket as a number would invent precision the producer refused to claim.
    if isinstance(validation, Mapping) and validation.get("duration_bucket"):
        limitations.append(
            "resolver reports duration as a bucket; effort_minutes is unknown"
        )

    return (
        [
            _observation(
                record_id=record_id,
                producer_id=str(event["producer_id"]),
                event_class=str(event["event_class"]),
                producer_contract=RESOLVER_CONTRACT,
                occurrence_scope=scope,
                recurrence_fingerprint=fingerprint,
                repository_identity=_text(payload.get("repository_pseudonym")),
                remediation_class=remediation_class,
                validation_outcome=validation_outcome,
            )
        ],
        limitations,
    )


def _historical_resolution_observations(
    event: Mapping[str, Any],
    *,
    record_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """One mined episode observation, keyed on the failure it reconstructs.

    Without this branch the historical miner's whole output fell to
    `_generic_observations`: a record-local fingerprint that can never
    aggregate, and `validation_outcome`, `remediation_class` and
    `false_positive_disposition` all left `None`. Those three carry 0.50 of the
    candidate score between them, so mined repair history -- the only source of
    repair evidence the constellation has -- could not reach scoring at all,
    and no candidate could pass the 4.0 promotion threshold however much
    history was ingested.

    The miner emits three events per episode (`CI_failure_classification`,
    `repair_attempt`, `verification_outcome`) that share one
    `semantic_failure_identity`. Keying recurrence on that identity is what
    makes the three collapse into one recurrence group rather than three
    unrelated singletons, and what lets the verification event's outcome attach
    to the same group the failure event opened.

    `repository_identity` is used as the scope verbatim: the producer already
    pseudonymised it with an HMAC before the event left the historical
    boundary, so re-deriving a scope here would either double-pseudonymise a
    value that is already safe or, worse, reach for a raw identity that is not
    present.
    """
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise LearningProjectionError("historical event has no payload object")

    limitations: list[str] = []

    # Already a pseudonym from `HistoricalEventProjector`; not re-derived.
    scope = _text(payload.get("repository_identity"))
    if scope is None:
        # Same record-local form `_scope` uses, spelled here rather than
        # imported from `analytics`: ingestion must not depend on a later phase.
        scope = f"record:{record_id}"
        limitations.append(
            "historical event carried no repository identity; occurrence scope "
            "is record-local and cannot co-occur"
        )

    failure = payload.get("failure")
    failure_identity = (
        _text(failure.get("semantic_failure_identity"))
        if isinstance(failure, Mapping)
        else None
    )
    if failure_identity is not None:
        fingerprint = _digest(_FAILURE_NAMESPACE, failure_identity)
    else:
        fingerprint = _digest(_RECORD_NAMESPACE, record_id)
        limitations.append(
            "historical event carried no semantic failure identity; recurrence "
            "is record-local"
        )

    # The miner states plainly when the identity it reconstructed is not a
    # canonical rule, via an `unknowns` entry. Honour that rather than passing
    # a reconstructed identity off as a canonical rule id.
    canonical_rule_id = None
    if isinstance(failure, Mapping):
        authority = _text(failure.get("identity_authority"))
        if authority == "canonical" and failure_identity is not None:
            canonical_rule_id = failure_identity
        elif authority is not None and authority != "canonical":
            limitations.append(
                f"historical failure identity authority is {authority!r}; "
                "canonical_rule_id is unknown"
            )

    intervention = payload.get("intervention")
    remediation_class = (
        _text(intervention.get("remediation_class"))
        if isinstance(intervention, Mapping)
        else None
    )

    validation = payload.get("validation")
    validation_outcome = None
    if isinstance(validation, Mapping):
        outcome = _text(validation.get("outcome"))
        if outcome is not None:
            validation_outcome = _HISTORICAL_OUTCOMES.get(outcome)
            if validation_outcome is None:
                limitations.append(
                    f"historical outcome {outcome!r} is not a learning-observation "
                    "outcome; recorded as unknown"
                )
                validation_outcome = "unknown"

    # Disposition follows the evidence rather than being left unknown.
    #
    # A suspected flake is the miner's own false-positive signal: the failure
    # was observed but attributing a repair to it is unsafe. `attribution.py`
    # and `reconstruction.py` already refuse repair credit in that case, so
    # `inconclusive` keeps the corpus consistent with the grade rather than
    # letting a flaky failure look like a confirmed true positive.
    #
    # A validated repair of a failure that is *not* a suspected flake is the
    # opposite, and saying nothing about it is not neutral: `effectiveness_rows`
    # computes `false_positive_ratio` from confirmed dispositions only, so an
    # all-`None` corpus yields a ratio of `None`, which scores
    # `false_positive_safety` as 0.0 -- indistinguishable from a rule whose
    # findings were all false positives. An episode whose failure was real
    # enough to reproduce and whose repair was validated as equivalent is a
    # confirmed true positive on exactly the evidence the miner reconstructed.
    false_positive_disposition = None
    evidence = payload.get("historical_evidence")
    suspected_flake = (
        evidence.get("suspected_flake") is True
        if isinstance(evidence, Mapping)
        else False
    )
    if suspected_flake:
        false_positive_disposition = "inconclusive"
        limitations.append(
            "historical episode is a suspected flake; disposition is inconclusive "
            "and repair credit was withheld upstream"
        )
    elif validation_outcome == "passed":
        false_positive_disposition = "confirmed_true_positive"

    # Reconstructed history carries provider timestamps, not measured repair
    # effort. Deriving minutes from wall-clock between runs would attribute
    # queue time and unrelated work to the repair.
    limitations.append(
        "historical evidence is reconstructed; effort_minutes is unknown"
    )

    return (
        [
            _observation(
                record_id=record_id,
                producer_id=str(event["producer_id"]),
                event_class=str(event["event_class"]),
                producer_contract=HISTORICAL_CONTRACT,
                occurrence_scope=scope,
                recurrence_fingerprint=fingerprint,
                canonical_rule_id=canonical_rule_id,
                repository_identity=scope,
                remediation_class=remediation_class,
                validation_outcome=validation_outcome,
                false_positive_disposition=false_positive_disposition,
            )
        ],
        limitations,
    )


def _generic_observations(
    event: Mapping[str, Any],
    *,
    record_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """One record-local observation for a contract with no projector.

    Deliberately not an error: a contract this module does not understand is
    still a delivery the corpus accepted, and dropping it would make the corpus
    and the learning view disagree about what exists. It contributes no
    recurrence, and says so.
    """
    payload = event.get("payload")
    scope, limitations = _scope(
        payload if isinstance(payload, Mapping) else {},
        record_id,
    )
    contract = str(event["producer_contract"])
    limitations.append(
        f"no learning projection for producer contract {contract!r}; "
        "observation is record-local and contributes no recurrence"
    )
    return (
        [
            _observation(
                record_id=record_id,
                producer_id=str(event["producer_id"]),
                event_class=str(event["event_class"]),
                producer_contract=contract,
                occurrence_scope=scope,
                recurrence_fingerprint=_digest(_RECORD_NAMESPACE, record_id),
            )
        ],
        limitations,
    )


class LearningProjector:
    """Validate and emit the learning observations carried by one event."""

    def __init__(self, *, schema: Path = DEFAULT_SCHEMA) -> None:
        self._validator = Draft202012Validator(
            json.loads(schema.read_text(encoding="utf-8"))
        )

    def project(
        self,
        event: Mapping[str, Any],
        *,
        record_id: str,
    ) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
        """Return the observations for ``event`` and any limitations found."""
        contract = event.get("producer_contract")
        if contract == SDK_CONTRACT:
            observations, limitations = _finding_bundle_observations(
                event, record_id=record_id
            )
        elif contract == RESOLVER_CONTRACT:
            observations, limitations = _resolver_feedback_observations(
                event, record_id=record_id
            )
        elif contract == HISTORICAL_CONTRACT:
            observations, limitations = _historical_resolution_observations(
                event, record_id=record_id
            )
        else:
            observations, limitations = _generic_observations(
                event, record_id=record_id
            )

        for observation in observations:
            errors = sorted(
                self._validator.iter_errors(observation),
                key=lambda error: tuple(str(part) for part in error.path),
            )
            if errors:
                message = "; ".join(
                    f"{'/'.join(str(part) for part in error.path) or '<root>'}: "
                    f"{error.message}"
                    for error in errors
                )
                raise LearningProjectionError(message)

        return tuple(observations), tuple(limitations)
