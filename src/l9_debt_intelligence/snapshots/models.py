from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SnapshotRecord:
    record_id: str
    source_event_id: str
    producer_id: str
    event_class: str
    lifecycle_state: str
    redaction_status: str
    producer_contract: str
    payload_content_hash: str
    limitations_json: str
    superseded_by: str | None
    source_record_hash: str
    #: Rows this record contributes, each already reduced to the column
    #: contract in `contracts.learning_columns` and carried opaquely: this phase
    #: writes them and does not interpret them. One record yields one row per
    #: entry, with its own provenance columns repeated across them. Empty only
    #: when the record predates the projection that derives them, in which case
    #: the record still contributes exactly one row.
    observations: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class PartitionPlan:
    event_class: str
    producer_id: str
    relative_path: Path
    records: tuple[SnapshotRecord, ...]


@dataclass(frozen=True)
class SnapshotBuildResult:
    snapshot_id: str
    snapshot_path: Path
    manifest_path: Path
    record_count: int
    partition_count: int
    deterministic_output_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "l9.snapshot-build-result/v1",
            "snapshot_id": self.snapshot_id,
            "snapshot_path": self.snapshot_path.as_posix(),
            "manifest_path": self.manifest_path.as_posix(),
            "record_count": self.record_count,
            "partition_count": self.partition_count,
            "deterministic_output_hash": (self.deterministic_output_hash),
        }
