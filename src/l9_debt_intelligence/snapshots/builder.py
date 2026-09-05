from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

import duckdb
import pyarrow

from l9_debt_intelligence import __version__
from l9_debt_intelligence.contracts.canonical import canonical_json

from .errors import SnapshotCollisionError, SnapshotError
from .hashing import (
    namespaced_document_hash,
    sha256_bytes,
    sha256_file,
)
from .models import SnapshotBuildResult
from .parquet import partition_row_count, write_partition
from .planner import plan_partitions
from .source import load_verified_records

Clock = Callable[[], dt.datetime]
FORMAT_VERSION = "l9.corpus-snapshot-format/v1"
SDK_CONTRACT_VERSION = "l9.integration-contract/v1"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def format_time(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise SnapshotError("snapshot clock must return a timezone-aware value")
    return (
        value.astimezone(dt.UTC)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def build_snapshot(
    *,
    storage_root: Path,
    snapshots_root: Path,
    clock: Clock = utc_now,
) -> SnapshotBuildResult:
    records = load_verified_records(storage_root)
    plans = plan_partitions(records)
    source_set = [
        {
            "record_id": record.record_id,
            "source_record_hash": record.source_record_hash,
            # The learning observations are part of what the snapshot contains,
            # so they belong in its identity. Without this a re-derivation under
            # a changed projector would keep the same snapshot id while writing
            # different parquet, and the collision check would report an
            # identity collision for what is really a new snapshot.
            "observation_set_hash": sha256_bytes(
                canonical_json([dict(row) for row in record.observations])
            ),
        }
        for record in records
    ]
    source_record_set_hash = sha256_bytes(canonical_json(source_set))
    identity_document = {
        "format_version": FORMAT_VERSION,
        "sdk_contract_version": SDK_CONTRACT_VERSION,
        "records": source_set,
        "partition_plan": [
            {
                "event_class": plan.event_class,
                "producer_id": plan.producer_id,
                "relative_path": plan.relative_path.as_posix(),
                "record_ids": [record.record_id for record in plan.records],
            }
            for plan in plans
        ],
    }
    snapshot_id = namespaced_document_hash(
        "cs_",
        identity_document,
    )
    destination = snapshots_root.resolve() / snapshot_id
    temporary_parent = snapshots_root.resolve()
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{snapshot_id}.",
            dir=temporary_parent,
        )
    )
    try:
        partition_entries: list[dict[str, object]] = []
        observation_total = 0
        for plan in plans:
            partition_path = temporary / plan.relative_path
            write_partition(partition_path, plan)
            partition_rows = partition_row_count(plan)
            observation_total += partition_rows
            partition_entries.append(
                {
                    "event_class": plan.event_class,
                    "producer_id": plan.producer_id,
                    "relative_path": plan.relative_path.as_posix(),
                    "record_count": len(plan.records),
                    # Parquet rows, which is one per learning observation and no
                    # longer one per record. Recorded separately so
                    # `record_count` keeps meaning corpus records; conflating
                    # the two would make the manifest lie about the corpus the
                    # moment a record described more than one observation.
                    "observation_count": partition_rows,
                    "sha256": sha256_file(partition_path),
                }
            )
        deterministic_document = {
            "snapshot_id": snapshot_id,
            "format_version": FORMAT_VERSION,
            "sdk_contract_version": SDK_CONTRACT_VERSION,
            "record_count": len(records),
            "observation_count": observation_total,
            "partition_count": len(partition_entries),
            "source_record_set_hash": source_record_set_hash,
            "partitions": partition_entries,
            "limitations": [],
        }
        deterministic_output_hash = sha256_bytes(canonical_json(deterministic_document))
        manifest = {
            "schema_version": "l9.corpus-snapshot/v1",
            **deterministic_document,
            "deterministic_output_hash": deterministic_output_hash,
            "build_metadata": {
                "created_at": format_time(clock()),
                "implementation_version": __version__,
                "pyarrow_version": pyarrow.__version__,
                "duckdb_version": duckdb.__version__,
            },
        }
        manifest_path = temporary / "manifest.json"
        manifest_path.write_bytes(canonical_json(manifest) + b"\n")
        if destination.exists():
            existing_manifest = destination / "manifest.json"
            if not existing_manifest.is_file():
                raise SnapshotCollisionError(
                    f"existing snapshot has no manifest: {destination}"
                )
            existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
            if existing.get("deterministic_output_hash") != deterministic_output_hash:
                raise SnapshotCollisionError(
                    f"snapshot identity collision: {snapshot_id}"
                )
            shutil.rmtree(temporary)
        else:
            os.replace(temporary, destination)
        return SnapshotBuildResult(
            snapshot_id=snapshot_id,
            snapshot_path=destination,
            manifest_path=destination / "manifest.json",
            record_count=len(records),
            partition_count=len(partition_entries),
            deterministic_output_hash=deterministic_output_hash,
        )
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
