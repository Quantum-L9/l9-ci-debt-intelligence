from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from l9_debt_intelligence.contracts.canonical import canonical_json


class StorageError(RuntimeError):
    """Filesystem ingestion storage failed."""


class FilesystemCorpusStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.ledger_path = self.root / "ledger/events.jsonl"
        self.records_path = self.root / "records"
        self.quarantine_path = self.root / "quarantine"
        self.observations_path = self.root / "observations"
        self.corrections_path = self.root / "corrections"
        self.index_path = self.root / "indexes/record-ids.txt"

    def initialize(self) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.records_path.mkdir(parents=True, exist_ok=True)
        self.quarantine_path.mkdir(parents=True, exist_ok=True)
        self.observations_path.mkdir(parents=True, exist_ok=True)
        self.corrections_path.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.touch(exist_ok=True)
        self.index_path.touch(exist_ok=True)

    def next_sequence(self) -> int:
        self.initialize()
        sequence = 0
        with self.ledger_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    sequence += 1
        return sequence + 1

    def has_record(self, record_id: str) -> bool:
        return (self.records_path / f"{record_id}.json").is_file()

    def read_record(self, record_id: str) -> dict[str, Any] | None:
        path = self.records_path / f"{record_id}.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise StorageError(f"invalid stored record: {path}")
        return value

    def write_record(self, record: dict[str, Any]) -> None:
        record_id = record.get("record_id")
        if not isinstance(record_id, str):
            raise StorageError("record_id is required")
        destination = self.records_path / f"{record_id}.json"
        self._write_once(destination, record)
        existing = set(self._read_index())
        if record_id not in existing:
            existing.add(record_id)
            self._atomic_write_bytes(
                self.index_path,
                ("\n".join(sorted(existing)) + "\n").encode("utf-8"),
            )

    def read_observations(self, record_id: str) -> list[dict[str, Any]] | None:
        path = self.observations_path / f"{record_id}.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise StorageError(f"invalid stored observations: {path}")
        observations: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                raise StorageError(f"invalid stored observation: {path}")
            observations.append(item)
        return observations

    def write_observations(
        self,
        record_id: str,
        observations: list[dict[str, Any]],
    ) -> None:
        """Store the learning observations derived from one record's event.

        Written through the same write-once path as the record itself, so a
        replayed delivery either matches byte for byte or raises. Learning
        observations are derived, not received, but they are derived from an
        immutable record and must not drift from it.

        Keyed by record id rather than given ids of their own: the observation
        is a view of that record, and the snapshot joins them on it.
        """
        self._write_once(
            self.observations_path / f"{record_id}.json",
            observations,
        )

    def iter_records(self) -> Iterable[dict[str, Any]]:
        self.initialize()
        for path in sorted(self.records_path.glob("cr_*.json")):
            record = self.read_record(path.stem)
            if record is not None:
                yield record

    def iter_corrections(self) -> Iterable[dict[str, Any]]:
        self.initialize()
        for path in sorted(self.corrections_path.glob("cc_*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise StorageError(f"invalid stored correction: {path}")
            yield value

    def write_correction(self, document: dict[str, Any]) -> None:
        correction_id = document.get("correction_id")
        if not isinstance(correction_id, str):
            raise StorageError("correction_id is required")
        destination = self.corrections_path / f"{correction_id}.json"
        self._write_once(destination, document)

    def write_quarantine(self, record: dict[str, Any]) -> None:
        quarantine_id = record.get("quarantine_id")
        if not isinstance(quarantine_id, str):
            raise StorageError("quarantine_id is required")
        destination = self.quarantine_path / f"{quarantine_id}.json"
        self._write_once(destination, record)

    def append_ledger(self, entry: dict[str, Any]) -> None:
        self.initialize()
        encoded = canonical_json(entry) + b"\n"
        with self.ledger_path.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

    def _read_index(self) -> Iterable[str]:
        self.initialize()
        with self.index_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                value = line.strip()
                if value:
                    yield value

    def _write_once(
        self,
        destination: Path,
        document: Any,
    ) -> None:
        encoded = canonical_json(document) + b"\n"
        if destination.exists():
            existing = destination.read_bytes()
            if existing != encoded:
                raise StorageError(f"immutable object collision: {destination}")
            return
        self._atomic_write_bytes(destination, encoded)

    @staticmethod
    def _atomic_write_bytes(
        destination: Path,
        content: bytes,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
