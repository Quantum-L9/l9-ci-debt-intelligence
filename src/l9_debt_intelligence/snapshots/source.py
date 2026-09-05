from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.contracts.learning_columns import (
    LearningColumnError,
    coerce_row,
    sort_key,
)
from l9_debt_intelligence.ingestion.verify import verify_store

from .errors import SnapshotSourceError
from .models import SnapshotRecord


def _load_rows(
    rows_root: Path,
    record_id: str,
) -> tuple[Mapping[str, Any], ...]:
    """The stored rows this record contributes, reduced to the column contract.

    Absent is not an error: a record written before the projection that derives
    these has none, and still contributes exactly one row. The column contract
    lives in `contracts.learning_columns` precisely so this phase can carry the
    values without naming what they mean.
    """
    path = rows_root / f"{record_id}.json"
    if not path.is_file():
        return ()
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, list):
        raise SnapshotSourceError(f"stored rows are not an array: {path}")
    rows: list[Mapping[str, Any]] = []
    for item in document:
        if not isinstance(item, dict):
            raise SnapshotSourceError(f"stored row is not an object: {path}")
        try:
            rows.append(coerce_row(item))
        except LearningColumnError as error:
            raise SnapshotSourceError(f"{error}: {path}") from error
    return tuple(sorted(rows, key=sort_key))


def load_verified_records(storage_root: Path) -> tuple[SnapshotRecord, ...]:
    verification = verify_store(storage_root)
    if verification.get("status") != "valid":
        raise SnapshotSourceError("ingestion store verification did not return valid")
    records_root = storage_root / "records"
    rows_root = storage_root / "observations"
    records: list[SnapshotRecord] = []
    for path in sorted(records_root.glob("cr_*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise SnapshotSourceError(f"record is not an object: {path}")
        payload_reference = document.get("payload_reference")
        if not isinstance(payload_reference, dict):
            raise SnapshotSourceError(f"record has no payload_reference: {path}")
        record_id = document.get("record_id")
        if record_id != path.stem:
            raise SnapshotSourceError(
                f"record identity does not match filename: {path}"
            )
        lifecycle_state = document.get("lifecycle_state")
        if lifecycle_state in {"RETRACTED", "REJECTED", "QUARANTINED"}:
            continue
        limitations = document.get("limitations", [])
        if not isinstance(limitations, list):
            raise SnapshotSourceError(f"record limitations must be a list: {path}")
        records.append(
            SnapshotRecord(
                record_id=str(record_id),
                source_event_id=str(document["source_event_id"]),
                producer_id=str(document["producer_id"]),
                event_class=str(document["event_class"]),
                lifecycle_state=str(lifecycle_state),
                redaction_status=str(document["redaction_status"]),
                producer_contract=str(payload_reference["producer_contract"]),
                payload_content_hash=str(payload_reference["content_hash"]),
                limitations_json=json.dumps(
                    sorted(set(str(item) for item in limitations)),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                superseded_by=(
                    str(document["superseded_by"])
                    if document.get("superseded_by")
                    else None
                ),
                source_record_hash=sha256_document(document),
                observations=_load_rows(rows_root, str(record_id)),
            )
        )
    return tuple(sorted(records, key=lambda value: value.record_id))
