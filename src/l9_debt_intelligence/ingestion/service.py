from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.contracts.errors import ContractError
from l9_debt_intelligence.contracts.validator import EventValidator

from .identity import (
    observation_id,
    quarantine_id,
    record_id,
)
from .models import IngestionResult
from .normalization import (
    NormalizationError,
    normalize_event,
    normalized_payload_hash,
)
from .redaction import assess_redaction
from .storage import FilesystemCorpusStore

Clock = Callable[[], dt.datetime]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def format_time(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("ingestion clock must return timezone-aware values")
    return (
        value.astimezone(dt.UTC)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


class IngestionService:
    def __init__(
        self,
        *,
        event_schema: Path,
        compatibility_registry: Path,
        storage_root: Path,
        clock: Clock = utc_now,
    ) -> None:
        self.validator = EventValidator(
            event_schema=event_schema,
            compatibility_registry=compatibility_registry,
        )
        self.store = FilesystemCorpusStore(storage_root)
        self.clock = clock

    def ingest(self, event: dict[str, Any]) -> IngestionResult:
        observed_at = format_time(self.clock())
        sequence = self.store.next_sequence()
        try:
            normalized = normalize_event(event)
            event_hash = sha256_document(normalized)
        except (NormalizationError, ValueError) as error:
            return self._quarantine(
                event=event,
                event_hash=sha256_document(event),
                reason="malformed_event",
                limitations=(str(error),),
                observed_at=observed_at,
                sequence=sequence,
            )
        try:
            validation = self.validator.validate(normalized)
        except ContractError as error:
            return self._quarantine(
                event=normalized,
                event_hash=event_hash,
                reason="invalid_schema",
                limitations=(str(error),),
                observed_at=observed_at,
                sequence=sequence,
            )
        if validation.status != "accepted":
            reason = self._map_validation_reason(validation.quarantine_reason)
            return self._quarantine(
                event=normalized,
                event_hash=event_hash,
                reason=reason,
                limitations=validation.limitations,
                observed_at=observed_at,
                sequence=sequence,
            )
        assessment = assess_redaction(normalized)
        if not assessment.safe:
            return self._quarantine(
                event=normalized,
                event_hash=event_hash,
                reason=assessment.reason or "sensitive_content",
                limitations=(tuple(validation.limitations) + assessment.limitations),
                observed_at=observed_at,
                sequence=sequence,
            )
        payload_hash = normalized_payload_hash(normalized)
        corpus_record_id = record_id(
            producer_id=normalized["producer_id"],
            producer_contract=normalized["producer_contract"],
            event_class=normalized["event_class"],
            snapshot_or_run_id=normalized["snapshot_or_run_id"],
            payload_hash=payload_hash,
        )
        existing = self.store.read_record(corpus_record_id)
        if existing is not None:
            stored_hash = existing.get("payload_reference", {}).get("content_hash")
            if stored_hash != payload_hash:
                return self._quarantine(
                    event=normalized,
                    event_hash=event_hash,
                    reason="fingerprint_collision",
                    limitations=("record identity matched but payload hash differed",),
                    observed_at=observed_at,
                    sequence=sequence,
                )
            status = "duplicate"
        else:
            record = {
                "schema_version": "l9.corpus-record/v1",
                "record_id": corpus_record_id,
                "source_event_id": normalized["event_id"],
                "producer_id": normalized["producer_id"],
                "event_class": normalized["event_class"],
                "lifecycle_state": "NORMALIZED",
                "redaction_status": normalized["redaction_status"],
                "payload_reference": {
                    "producer_contract": normalized["producer_contract"],
                    "sdk_schema_references": [],
                    "content_hash": payload_hash,
                },
                "limitations": normalized.get("limitations", []),
                "superseded_by": None,
            }
            self.store.write_record(record)
            status = "accepted"
        observation = observation_id(
            event_hash=event_hash,
            observed_at=observed_at,
            sequence=sequence,
        )
        self.store.append_ledger(
            {
                "schema_version": "l9.ingestion-ledger-entry/v1",
                "sequence": sequence,
                "observation_id": observation,
                "event_id": normalized["event_id"],
                "event_hash": event_hash,
                "producer_id": normalized["producer_id"],
                "event_class": normalized["event_class"],
                "record_id": corpus_record_id,
                "disposition": status,
                "quarantine_reason": None,
                "observed_at": observed_at,
                "limitations": normalized.get("limitations", []),
            }
        )
        return IngestionResult(
            schema_version="l9.ingestion-result/v1",
            status=status,
            event_id=normalized["event_id"],
            event_hash=event_hash,
            record_id=corpus_record_id,
            quarantine_id=None,
            observation_id=observation,
            ledger_sequence=sequence,
            limitations=tuple(normalized.get("limitations", [])),
        )

    def _quarantine(
        self,
        *,
        event: dict[str, Any],
        event_hash: str,
        reason: str,
        limitations: tuple[str, ...],
        observed_at: str,
        sequence: int,
    ) -> IngestionResult:
        event_id = str(event.get("event_id", "unknown"))
        producer_id = str(event.get("producer_id", "unknown"))
        event_class = str(event.get("event_class", "unknown"))
        quarantine_record_id = quarantine_id(
            event_hash,
            reason,
        )
        observation = observation_id(
            event_hash=event_hash,
            observed_at=observed_at,
            sequence=sequence,
        )
        self.store.write_quarantine(
            {
                "schema_version": "l9.quarantine-record/v1",
                "quarantine_id": quarantine_record_id,
                "event_id": event_id,
                "event_hash": event_hash,
                "producer_id": producer_id,
                "event_class": event_class,
                "reason": reason,
                "observed_at": observed_at,
                "limitations": list(limitations),
                "event": event,
            }
        )
        self.store.append_ledger(
            {
                "schema_version": "l9.ingestion-ledger-entry/v1",
                "sequence": sequence,
                "observation_id": observation,
                "event_id": event_id,
                "event_hash": event_hash,
                "producer_id": producer_id,
                "event_class": event_class,
                "record_id": None,
                "disposition": "quarantined",
                "quarantine_reason": reason,
                "observed_at": observed_at,
                "limitations": list(limitations),
            }
        )
        return IngestionResult(
            schema_version="l9.ingestion-result/v1",
            status="quarantined",
            event_id=event_id,
            event_hash=event_hash,
            record_id=None,
            quarantine_id=quarantine_record_id,
            observation_id=observation,
            ledger_sequence=sequence,
            limitations=limitations,
        )

    @staticmethod
    def _map_validation_reason(reason: str | None) -> str:
        if reason is None:
            return "incompatible_producer_contract"
        mapping = {
            "ProducerCompatibilityError": "unknown_producer",
            "SDKCompatibilityError": "incompatible_sdk_contract",
            "redaction_required": "redaction_required",
        }
        return mapping.get(reason, "incompatible_producer_contract")
