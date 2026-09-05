from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/l9_debt_intelligence/historical"


class HistoricalBoundaryTests(unittest.TestCase):
    def test_historical_runtime_has_no_forbidden_authority_edges(self) -> None:
        prohibited = (
            "l9_debt_intelligence.snapshots", "l9_debt_intelligence.analytics",
            "l9_debt_intelligence.compilation", "l9_debt_intelligence.publication",
            "FilesystemCorpusStore", "l9_ci_debt_resolver", "l9_harness",
            "subprocess", "shell=True", "os.system", "git push", "git commit",
        )
        violations = []
        for path in SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            violations.extend(
                f"{path.relative_to(ROOT)}:{token}"
                for token in prohibited if token in text
            )
        self.assertEqual([], violations)

    def test_only_bootstrap_depends_on_existing_p1_service(self) -> None:
        importers = [
            path.name for path in SOURCE.rglob("*.py")
            if "l9_debt_intelligence.ingestion.service" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(["bootstrap.py"], sorted(importers))

    def test_historical_schemas_do_not_duplicate_sdk_finding_semantics(self) -> None:
        prohibited = {"canonical_rule_id", "provider_rule_id", "finding_id",
                      "evidence_id", "source_location"}
        for path in sorted((ROOT / "schemas/intelligence").glob("historical-*.json")):
            text = json.dumps(json.loads(path.read_text(encoding="utf-8")), sort_keys=True)
            self.assertTrue(all(token not in text for token in prohibited))

    def test_raw_log_text_has_no_corpus_projection_path(self) -> None:
        admission = (SOURCE / "admission.py").read_text(encoding="utf-8")
        storage = (SOURCE / "storage.py").read_text(encoding="utf-8")
        self.assertNotIn("job_log", admission)
        self.assertNotIn("raw_text", admission)
        self.assertNotIn("write_acquisition", storage)


if __name__ == "__main__":
    unittest.main()
