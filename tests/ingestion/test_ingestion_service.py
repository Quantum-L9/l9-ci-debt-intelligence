from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.ingestion.verify import verify_store

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


class IngestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = json.loads(
            (ROOT / "tests/fixtures/producers/valid-sdk-finding-bundle.json").read_text(
                encoding="utf-8"
            )
        )

    def service(self, storage: Path) -> IngestionService:
        return IngestionService(
            event_schema=(ROOT / "schemas/intelligence/corpus-event.schema.json"),
            compatibility_registry=(ROOT / ".l9/producer-compatibility.json"),
            storage_root=storage,
            clock=fixed_clock,
        )

    def test_event_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory)
            result = self.service(storage).ingest(self.event)
            self.assertEqual("accepted", result.status)
            self.assertIsNotNone(result.record_id)
            record = storage / "records" / f"{result.record_id}.json"
            self.assertTrue(record.is_file())

    def test_duplicate_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory)
            service = self.service(storage)
            first = service.ingest(self.event)
            second = service.ingest(self.event)
            self.assertEqual("accepted", first.status)
            self.assertEqual("duplicate", second.status)
            self.assertEqual(first.record_id, second.record_id)
            records = list((storage / "records").glob("cr_*.json"))
            self.assertEqual(1, len(records))

    def test_sensitive_event_is_quarantined(self) -> None:
        event = json.loads(
            (ROOT / "tests/fixtures/ingestion/sensitive-event.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory)
            result = self.service(storage).ingest(event)
            self.assertEqual("quarantined", result.status)
            self.assertIsNotNone(result.quarantine_id)
            self.assertIsNone(result.record_id)

    def test_store_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory)
            service = self.service(storage)
            service.ingest(self.event)
            service.ingest(self.event)
            report = verify_store(storage)
            self.assertEqual("valid", report["status"])
            self.assertEqual(2, report["ledger_entries"])
            self.assertEqual(1, report["accepted"])
            self.assertEqual(1, report["duplicates"])
            self.assertEqual(1, report["record_count"])


if __name__ == "__main__":
    unittest.main()
