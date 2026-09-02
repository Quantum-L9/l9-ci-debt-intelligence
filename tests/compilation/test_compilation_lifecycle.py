from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from l9_debt_intelligence.analytics.builder import build_analytics
from l9_debt_intelligence.compilation.builder import (
    build_compilation,
)
from l9_debt_intelligence.compilation.verify import (
    verify_compilation,
)
from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.snapshots.builder import build_snapshot

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


class CompilationLifecycleTests(unittest.TestCase):
    def test_compilation_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingestion = root / "ingestion"
            snapshots = root / "snapshots"
            analytics = root / "analytics"
            compilations = root / "compilations"
            event = json.loads(
                (
                    ROOT / "tests/fixtures/producers/valid-sdk-finding-bundle.json"
                ).read_text(encoding="utf-8")
            )
            service = IngestionService(
                event_schema=(ROOT / "schemas/intelligence/corpus-event.schema.json"),
                compatibility_registry=(ROOT / ".l9/producer-compatibility.json"),
                storage_root=ingestion,
                clock=fixed_clock,
            )
            service.ingest(event)
            snapshot = build_snapshot(
                storage_root=ingestion,
                snapshots_root=snapshots,
                clock=fixed_clock,
            )
            analysis = build_analytics(
                snapshot_path=snapshot.snapshot_path,
                analytics_root=analytics,
            )
            first = build_compilation(
                analysis_path=Path(analysis["analysis_path"]),
                compilation_root=compilations,
            )
            second = build_compilation(
                analysis_path=Path(analysis["analysis_path"]),
                compilation_root=compilations,
            )
            self.assertEqual(
                first["compilation_id"],
                second["compilation_id"],
            )
            self.assertEqual(
                first["deterministic_output_hash"],
                second["deterministic_output_hash"],
            )
            verification = verify_compilation(Path(first["compilation_path"]))
            self.assertEqual("valid", verification["status"])


if __name__ == "__main__":
    unittest.main()
