from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from l9_debt_intelligence.contracts.canonical import canonical_json

from .errors import SnapshotVerificationError
from .hashing import sha256_bytes, sha256_file


def verify_snapshot(snapshot_path: Path) -> dict[str, Any]:
    snapshot_path = snapshot_path.resolve()
    manifest_path = snapshot_path / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotVerificationError(
            f"snapshot manifest does not exist: {manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "l9.corpus-snapshot/v1":
        raise SnapshotVerificationError("unsupported snapshot manifest schema")
    if manifest.get("snapshot_id") != snapshot_path.name:
        raise SnapshotVerificationError(
            "snapshot directory does not match snapshot identity"
        )
    partitions = manifest.get("partitions")
    if not isinstance(partitions, list):
        raise SnapshotVerificationError("snapshot partitions must be a list")
    total_rows = 0
    for partition in partitions:
        if not isinstance(partition, dict):
            raise SnapshotVerificationError(
                "snapshot partition entry must be an object"
            )
        relative_path = partition.get("relative_path")
        if not isinstance(relative_path, str):
            raise SnapshotVerificationError("partition relative_path must be a string")
        path = (snapshot_path / relative_path).resolve()
        try:
            path.relative_to(snapshot_path)
        except ValueError as error:
            raise SnapshotVerificationError(
                "partition path escapes snapshot root"
            ) from error
        if not path.is_file():
            raise SnapshotVerificationError(
                f"partition does not exist: {relative_path}"
            )
        actual_hash = sha256_file(path)
        if actual_hash != partition.get("sha256"):
            raise SnapshotVerificationError(f"partition hash mismatch: {relative_path}")
        table = pq.ParquetFile(path).read()
        row_count = table.num_rows
        # A partition holds one row per learning observation, so its row count
        # is `observation_count`. `record_count` still means corpus records.
        # Snapshots written before the learning projection carry no
        # `observation_count` and had exactly one row per record, so falling
        # back to `record_count` keeps them verifiable rather than retroactively
        # invalid.
        expected_rows = partition.get("observation_count")
        if expected_rows is None:
            expected_rows = partition.get("record_count")
        if row_count != expected_rows:
            raise SnapshotVerificationError(
                f"partition row count mismatch: {relative_path}"
            )
        record_ids = table.column("record_id").to_pylist()
        if record_ids != sorted(record_ids):
            raise SnapshotVerificationError(
                f"partition row order is not deterministic: {relative_path}"
            )
        total_rows += row_count
    expected_total = manifest.get("observation_count")
    if expected_total is None:
        expected_total = manifest.get("record_count")
    if total_rows != expected_total:
        raise SnapshotVerificationError(
            "manifest observation count does not match partitions"
        )
    deterministic_document = {
        "snapshot_id": manifest["snapshot_id"],
        "format_version": manifest["format_version"],
        "sdk_contract_version": manifest["sdk_contract_version"],
        "record_count": manifest["record_count"],
        "partition_count": manifest["partition_count"],
        "source_record_set_hash": manifest["source_record_set_hash"],
        "partitions": manifest["partitions"],
        "limitations": manifest["limitations"],
    }
    # Included only when present, so the hash of a pre-projection manifest is
    # still reproduced exactly as it was written.
    if "observation_count" in manifest:
        deterministic_document["observation_count"] = manifest["observation_count"]
    actual_output_hash = sha256_bytes(canonical_json(deterministic_document))
    if actual_output_hash != manifest.get("deterministic_output_hash"):
        raise SnapshotVerificationError("deterministic output hash mismatch")
    return {
        "schema_version": "l9.snapshot-verification/v1",
        "status": "valid",
        "snapshot_id": manifest["snapshot_id"],
        "record_count": manifest["record_count"],
        "observation_count": total_rows,
        "partition_count": len(partitions),
        "verified_partition_count": len(partitions),
        "deterministic_output_hash": actual_output_hash,
    }
