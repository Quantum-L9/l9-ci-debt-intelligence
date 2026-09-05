from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .storage import FilesystemCorpusStore


class LedgerVerificationError(RuntimeError):
    """The ingestion ledger or immutable objects are inconsistent."""


def verify_store(root: Path) -> dict[str, Any]:
    store = FilesystemCorpusStore(root)
    store.initialize()
    entries: list[dict[str, Any]] = []
    with store.ledger_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise LedgerVerificationError(
                    f"ledger line {line_number} is not an object"
                )
            expected_sequence = len(entries) + 1
            if value.get("sequence") != expected_sequence:
                raise LedgerVerificationError(
                    f"ledger sequence gap at line {line_number}"
                )
            entries.append(value)
    accepted = 0
    duplicates = 0
    quarantined = 0
    for entry in entries:
        disposition = entry["disposition"]
        if disposition == "accepted":
            accepted += 1
        elif disposition == "duplicate":
            duplicates += 1
        elif disposition == "quarantined":
            quarantined += 1
        record_id = entry.get("record_id")
        if record_id:
            record = store.read_record(record_id)
            if record is None:
                raise LedgerVerificationError(
                    f"ledger references missing record {record_id}"
                )
    # Derived learning observations are a third immutable artifact in this
    # store, and `build_snapshot` verifies the store and then reads them. A
    # verification that ignored them would declare the store valid and hand the
    # snapshot builder unverified input.
    observation_count = 0
    for path in sorted(store.observations_path.glob("cr_*.json")):
        owner = path.stem
        if store.read_record(owner) is None:
            raise LedgerVerificationError(
                f"observations reference missing record {owner}"
            )
        observations = store.read_observations(owner)
        if observations is None:
            raise LedgerVerificationError(f"unreadable observations for {owner}")
        for observation in observations:
            if observation.get("record_id") != owner:
                raise LedgerVerificationError(
                    f"observation does not name its own record: {path}"
                )
        observation_count += len(observations)
    correction_count = 0
    for path in sorted(store.corrections_path.glob("cc_*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise LedgerVerificationError(f"correction is not an object: {path}")
        if document.get("correction_id") != path.stem:
            raise LedgerVerificationError(
                f"correction identity does not match filename: {path}"
            )
        target = document.get("target_record_id")
        if not isinstance(target, str) or store.read_record(target) is None:
            raise LedgerVerificationError(
                f"correction references missing record {target}"
            )
        correction_count += 1
    return {
        "schema": "l9.ingestion-verification/v1",
        "status": "valid",
        "ledger_entries": len(entries),
        "accepted": accepted,
        "duplicates": duplicates,
        "quarantined": quarantined,
        "record_count": len(list(store.records_path.glob("cr_*.json"))),
        "quarantine_count": len(list(store.quarantine_path.glob("qr_*.json"))),
        "observation_count": observation_count,
        "correction_count": correction_count,
    }
