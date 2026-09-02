from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.snapshots.builder import build_snapshot
from l9_debt_intelligence.snapshots.duckdb_projection import (
    create_projection,
)

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


class DuckDBProjectionTests(unittest.TestCase):
    def test_projection_reads_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "ingestion"
            snapshots = root / "snapshots"
            database = root / "analytics/corpus.duckdb"
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
            snapshot = build_snapshot(
                storage_root=storage,
                snapshots_root=snapshots,
                clock=fixed_clock,
            )
            create_projection(
                snapshot_path=snapshot.snapshot_path,
                database_path=database,
            )
            connection = duckdb.connect(
                str(database),
                read_only=True,
            )
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM corpus_records"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(1, count)


if __name__ == "__main__":
    unittest.main()
