"""Ingest a real producer artifact and assert the pipeline can actually learn.

This is the test whose absence let L3-F8 stand. Every phase had its own tests
and they all passed: ingestion stored a valid record, the snapshot built and
verified, analytics produced a report, the compiler produced candidates. What no
test asserted was that a fact entering Phase 2 could still be *learned from* in
Phase 3 -- and it could not. The snapshot carried none of the columns analytics
reads, so every fallback fired, every record became its own scope with its own
unique key, and every candidate scored an identical 0.35 against a promotion
threshold of 4.0.

So the assertions here are about aggregation across the seam, not about any one
phase: a rule seen in several repositories must come out the far end as one
group with several scopes.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from l9_debt_intelligence.analytics.builder import build_analytics
from l9_debt_intelligence.analytics.projection import fallback_scope, load_observations
from l9_debt_intelligence.ingestion.sdk_finding_bundle import SdkFindingBundleAdapter
from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.snapshots.builder import build_snapshot
from l9_debt_intelligence.snapshots.verify import verify_snapshot

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "tests/fixtures/producers/native-sdk-finding-bundle.json"
EVENT_SCHEMA = ROOT / "schemas/intelligence/corpus-event.schema.json"
REGISTRY = ROOT / ".l9/producer-compatibility.json"
PSEUDONYM_KEY = b"p" * 48
PATH_KEY = b"t" * 48


def _event(repository: str) -> dict[str, Any]:
    return SdkFindingBundleAdapter().project(
        json.loads(NATIVE.read_text(encoding="utf-8")),
        repository=repository,
        pseudonym_key=PSEUDONYM_KEY,
        path_key=PATH_KEY,
    )


class LearningPipeline(unittest.TestCase):
    def _run(self, repositories: list[str]) -> dict[str, Any]:
        directory = tempfile.mkdtemp()
        root = Path(directory)
        service = IngestionService(
            event_schema=EVENT_SCHEMA,
            compatibility_registry=REGISTRY,
            storage_root=root / "store",
        )
        results = [service.ingest(_event(name)) for name in repositories]
        snapshot = build_snapshot(
            storage_root=root / "store",
            snapshots_root=root / "snapshots",
        )
        verification = verify_snapshot(snapshot.snapshot_path)
        observations = load_observations(snapshot.snapshot_path)
        analysis = build_analytics(
            snapshot_path=snapshot.snapshot_path,
            analytics_root=root / "analytics",
        )
        return {
            "results": results,
            "snapshot": snapshot,
            "verification": verification,
            "observations": observations,
            "analysis": analysis,
            "root": root,
        }

    def test_a_bundle_of_many_findings_becomes_many_observations(self) -> None:
        findings = len(json.loads(NATIVE.read_text(encoding="utf-8"))["findings"])
        self.assertGreater(findings, 1)
        outcome = self._run(["Acme-Corp/one"])
        self.assertEqual(len(outcome["observations"]), findings)
        self.assertEqual(outcome["snapshot"].record_count, 1)
        self.assertEqual(outcome["verification"]["observation_count"], findings)
        self.assertEqual(outcome["verification"]["record_count"], 1)

    def test_no_observation_falls_back_to_a_record_local_scope(self) -> None:
        """The fallbacks must stop firing. That is the whole repair."""
        outcome = self._run(["Acme-Corp/one", "Acme-Corp/two"])
        for observation in outcome["observations"]:
            self.assertNotEqual(
                observation.occurrence_scope,
                fallback_scope(observation.record_id),
            )
            self.assertTrue(observation.occurrence_scope.startswith("repository_"))
            self.assertIsNotNone(observation.canonical_rule_id)

    def test_recurrence_aggregates_across_repositories(self) -> None:
        """One rule in three repositories: one group, three scopes.

        Before the projection this produced three groups of one, each with a
        `distinct_scope_count` of 1, which is what pinned every candidate score
        at 0.35.
        """
        outcome = self._run(["Acme-Corp/one", "Acme-Corp/two", "Acme-Corp/three"])
        report = json.loads(
            (
                Path(outcome["analysis"]["analysis_path"]) / "recurrence-report.json"
            ).read_text(encoding="utf-8")
        )
        entries = report["rows"]
        self.assertTrue(entries)
        breadth = max(int(row["distinct_scope_count"]) for row in entries)
        self.assertEqual(breadth, 3, entries)
        repeated = max(int(row["occurrence_count"]) for row in entries)
        self.assertGreater(repeated, 3, entries)
        # And the fallback limitation that used to appear on every run is gone.
        self.assertNotIn(
            "occurrence_scope unavailable for some records; "
            "record identity was used as a non-cooccurring fallback",
            report["limitations"],
        )

    def test_the_snapshot_is_byte_identical_on_rebuild(self) -> None:
        """Determinism must survive the extra columns."""
        outcome = self._run(["Acme-Corp/one", "Acme-Corp/two"])
        first = outcome["snapshot"]
        again = build_snapshot(
            storage_root=outcome["root"] / "store",
            snapshots_root=outcome["root"] / "snapshots-2",
        )
        self.assertEqual(again.snapshot_id, first.snapshot_id)
        self.assertEqual(
            again.deterministic_output_hash,
            first.deterministic_output_hash,
        )

    def test_a_duplicate_delivery_does_not_duplicate_observations(self) -> None:
        findings = len(json.loads(NATIVE.read_text(encoding="utf-8"))["findings"])
        outcome = self._run(["Acme-Corp/one", "Acme-Corp/one"])
        self.assertEqual(
            [result.status for result in outcome["results"]],
            ["accepted", "duplicate"],
        )
        self.assertEqual(len(outcome["observations"]), findings)

    def test_a_record_with_no_stored_observations_still_appears(self) -> None:
        """A store written before this projection must not lose records.

        Its rows keep Phase 3's own fallbacks, which is the honest reading of a
        record whose learning view was never derived.
        """
        outcome = self._run(["Acme-Corp/one"])
        store = outcome["root"] / "store"
        for path in (store / "observations").glob("cr_*.json"):
            path.unlink()
        snapshot = build_snapshot(
            storage_root=store,
            snapshots_root=outcome["root"] / "snapshots-3",
        )
        observations = load_observations(snapshot.snapshot_path)
        self.assertEqual(len(observations), 1)
        self.assertEqual(
            observations[0].occurrence_scope,
            fallback_scope(observations[0].record_id),
        )


if __name__ == "__main__":
    unittest.main()
