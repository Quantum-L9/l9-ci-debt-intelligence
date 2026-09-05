from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import FilesystemCorpusStore

HISTORICAL_PRODUCER_CONTRACT = "l9.historical-resolution-event/v1"
ALGORITHM_REPLACE_REASON = (
    "reconstruction algorithm replacement without contract change"
)


def historical_predecessors(
    records: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
    *,
    event_id: str,
    producer_id: str,
    producer_contract: str,
    event_class: str,
    replacement_record_id: str,
    payload_hash: str,
) -> tuple[dict[str, Any], ...]:
    """Prior historical claims that this replacement must correct, not re-admit."""
    if producer_contract != HISTORICAL_PRODUCER_CONTRACT:
        return ()
    already_corrected = {
        str(item["target_record_id"])
        for item in corrections
        if item.get("target_record_id")
    }
    predecessors: list[dict[str, Any]] = []
    for record in records:
        if record.get("record_id") == replacement_record_id:
            continue
        if record.get("source_event_id") != event_id:
            continue
        if record.get("producer_id") != producer_id:
            continue
        if record.get("event_class") != event_class:
            continue
        payload_reference = record.get("payload_reference")
        if not isinstance(payload_reference, dict):
            continue
        if payload_reference.get("producer_contract") != producer_contract:
            continue
        if payload_reference.get("content_hash") == payload_hash:
            continue
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or record_id in already_corrected:
            continue
        predecessors.append(record)
    return tuple(predecessors)


def derived_superseded_by(storage_root: Path) -> dict[str, str]:
    """Logical supersession from append-only correction events.

    Record files stay write-once. Snapshot consumers reconstruct the current
    view from correction history instead of mutating ``superseded_by`` in place.
    """
    store = FilesystemCorpusStore(storage_root)
    records = list(store.iter_records())
    by_event: dict[str, list[str]] = {}
    for record in records:
        event_id = record.get("source_event_id")
        record_id = record.get("record_id")
        if isinstance(event_id, str) and isinstance(record_id, str):
            by_event.setdefault(event_id, []).append(record_id)
    targets = {
        str(item["target_record_id"]): str(item["replacement_event_id"])
        for item in store.iter_corrections()
        if item.get("target_record_id") and item.get("replacement_event_id")
    }
    overlay: dict[str, str] = {}
    for target, event_id in targets.items():
        candidates = [
            record_id for record_id in by_event.get(event_id, []) if record_id != target
        ]
        live = [record_id for record_id in candidates if record_id not in targets]
        chosen = live or candidates
        if chosen:
            overlay[target] = sorted(chosen)[-1]
    return overlay
