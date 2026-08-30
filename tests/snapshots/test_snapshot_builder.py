from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.snapshots.builder import build_snapshot
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


class SnapshotBuilderTests(unittest.TestCase):
    def event(self) -> dict:
        return json.loads(
            (ROOT / "tests/fixtures/producers/valid-sdk-finding-bundle.json").read_text(
                encoding="utf-8"
            )
        )

    def ingest(self, storage: Path) -> None:
        service = IngestionService(
            event_schema=(ROOT / "schemas/intelligence/corpus-event.schema.json"),
            compatibility_registry=(ROOT / ".l9/producer-compatibility.json"),
            storage_root=storage,
            clock=fixed_clock,
        )
        result = service.ingest(self.event())
        self.assertEqual("accepted", result.status)

    def test_snapshot_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "ingestion"
            snapshots = root / "snapshots"
            self.ingest(storage)
            first = build_snapshot(
                storage_root=storage,
                snapshots_root=snapshots,
                clock=fixed_clock,
            )
            second = build_snapshot(
                storage_root=storage,
                snapshots_root=snapshots,
                clock=fixed_clock,
            )
            self.assertEqual(first.snapshot_id, second.snapshot_id)
            self.assertEqual(
                first.deterministic_output_hash,
                second.deterministic_output_hash,
            )
            self.assertEqual(1, first.record_count)
            self.assertEqual(1, first.partition_count)

    def test_snapshot_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "ingestion"
            snapshots = root / "snapshots"
            self.ingest(storage)
            result = build_snapshot(
                storage_root=storage,
                snapshots_root=snapshots,
                clock=fixed_clock,
            )
            verification = verify_snapshot(result.snapshot_path)
            self.assertEqual("valid", verification["status"])
            self.assertEqual(result.snapshot_id, verification["snapshot_id"])
            self.assertEqual(1, verification["record_count"])


if __name__ == "__main__":
    unittest.main()
