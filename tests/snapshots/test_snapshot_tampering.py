from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.snapshots.builder import build_snapshot
from l9_debt_intelligence.snapshots.errors import (
    SnapshotVerificationError,
)
from l9_debt_intelligence.snapshots.verify import verify_snapshot

ROOT = Path(__file__).resolve().parents[2]


def fixed_clock() -> dt.datetime:
    return dt.datetime(
        2026,
        7,
        17,
        12,
        0,
        tzinfo=dt.UTC,
    )


class SnapshotTamperingTests(unittest.TestCase):
    def test_partition_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "ingestion"
            snapshots = root / "snapshots"
            event = json.loads(
                (
                    ROOT / "tests/fixtures/producers/valid-sdk-finding-bundle.json"
                ).read_text(encoding="utf-8")
            )
            service = IngestionService(
                event_schema=(ROOT / "schemas/intelligence/corpus-event.schema.json"),
                compatibility_registry=(ROOT / ".l9/producer-compatibility.json"),
                storage_root=storage,
                clock=fixed_clock,
            )
            service.ingest(event)
            result = build_snapshot(
                storage_root=storage,
                snapshots_root=snapshots,
                clock=fixed_clock,
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            partition = (
                result.snapshot_path / manifest["partitions"][0]["relative_path"]
            )
            with partition.open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaises(SnapshotVerificationError):
                verify_snapshot(result.snapshot_path)


if __name__ == "__main__":
    unittest.main()
