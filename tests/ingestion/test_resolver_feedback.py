"""The Resolver feedback seam: native producer event -> corpus record.

`Quantum-L9/l9-ci-debt-resolver` emits `l9.intelligence-feedback-event/v1`
through a durable outbox and a file or HTTPS transport. Intelligence owns
`l9.corpus-event/v1` and everything downstream of it. `ResolverFeedbackAdapter`
is the projection between them, and it is Intelligence's to own: asking the
Resolver to emit the corpus envelope would duplicate schema authority instead
of closing a wire.

`tests/fixtures/producers/valid-resolver-feedback.json` is not hand-written.
It is the artifact `JSONFileFeedbackTransport` wrote, byte for byte, when the
real Resolver pipeline ran end to end -- repository correlation, root-cause
classification, `build_feedback_event`, `validate_feedback_event` (the
producer's privacy boundary), then delivery. That is asserted below rather than
described: the file equals the transport's canonical encoding plus its
terminating newline.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from l9_debt_intelligence.contracts.canonical import canonical_json, sha256_document
from l9_debt_intelligence.ingestion.resolver_feedback import (
    EVENT_CLASS,
    PRODUCER_CONTRACT,
    PRODUCER_ID,
    SDK_CONTRACT,
    ResolverFeedbackAdapter,
    ResolverFeedbackError,
)
from l9_debt_intelligence.ingestion.service import IngestionService

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".l9/producer-compatibility.json"
EVENT_SCHEMA = ROOT / "schemas/intelligence/corpus-event.schema.json"
FIXTURE = ROOT / "tests/fixtures/producers/valid-resolver-feedback.json"
SOURCE = ROOT / "src/l9_debt_intelligence"


def native_event() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return document


class TransportArtifactTests(unittest.TestCase):
    def test_fixture_is_the_resolver_file_transport_artifact(self) -> None:
        """The fixture is what the producer's transport writes, not a copy of it.

        `JSONFileFeedbackTransport` encodes with sorted keys, no whitespace,
        `ensure_ascii=False`, and one terminating newline. If the fixture were
        reformatted, or edited by hand, this fails.
        """
        raw = FIXTURE.read_bytes()
        self.assertEqual(canonical_json(json.loads(raw)) + b"\n", raw)

    def test_fixture_declares_the_producer_contract(self) -> None:
        self.assertEqual(
            "l9.intelligence-feedback-event/v1",
            native_event()["schema_version"],
        )


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ResolverFeedbackAdapter()
        self.native = native_event()
        self.envelope = self.adapter.project(self.native)

    def test_envelope_declares_the_intelligence_contract(self) -> None:
        self.assertEqual("l9.corpus-event/v1", self.envelope["schema_version"])
        self.assertEqual(PRODUCER_ID, self.envelope["producer_id"])
        self.assertEqual(PRODUCER_CONTRACT, self.envelope["producer_contract"])
        self.assertEqual(SDK_CONTRACT, self.envelope["sdk_contract"])
        self.assertEqual(EVENT_CLASS, self.envelope["event_class"])

    def test_envelope_takes_identity_and_time_from_the_producer(self) -> None:
        self.assertEqual(self.native["event_id"], self.envelope["event_id"])
        self.assertEqual(self.native["event_id"], self.envelope["snapshot_or_run_id"])
        self.assertEqual(self.native["occurred_at"], self.envelope["event_time"])
        self.assertEqual("producer_redacted", self.envelope["redaction_status"])

    def test_payload_is_the_whole_producer_document_unflattened(self) -> None:
        """Acceptance 2: the producer-owned document survives byte-canonically."""
        self.assertEqual(self.native, self.envelope["payload"])
        self.assertEqual(
            canonical_json(self.native),
            canonical_json(self.envelope["payload"]),
        )

    def test_payload_retains_every_learning_dimension(self) -> None:
        payload = self.envelope["payload"]
        self.assertEqual(
            self.native["failure"]["fingerprint"],
            payload["failure"]["fingerprint"],
        )
        self.assertEqual(
            self.native["failure"]["category"],
            payload["failure"]["category"],
        )
        self.assertEqual(
            self.native["resolution"]["terminal_state"],
            payload["resolution"]["terminal_state"],
        )
        self.assertEqual(
            self.native["validation"]["result"],
            payload["validation"]["result"],
        )
        self.assertEqual(
            self.native["correlation"]["finding_ids"],
            payload["correlation"]["finding_ids"],
        )
        self.assertEqual(
            self.native["correlation"]["contract_ids"],
            payload["correlation"]["contract_ids"],
        )
        self.assertEqual(
            self.native["correlation"]["capability_profile"],
            payload["correlation"]["capability_profile"],
        )
        self.assertEqual(self.native["provenance"], payload["provenance"])
        self.assertEqual(
            self.native["idempotency_key"],
            payload["idempotency_key"],
        )

    def test_lineage_binds_to_the_exact_producer_event(self) -> None:
        """Acceptance 3: the hash is of the producer's document, not the envelope."""
        self.assertEqual(
            sha256_document(self.native),
            self.envelope["lineage"]["producer_event_hash"],
        )

    def test_projection_is_deterministic(self) -> None:
        self.assertEqual(
            canonical_json(self.envelope),
            canonical_json(self.adapter.project(native_event())),
        )

    def test_an_additive_producer_field_does_not_break_the_consumer(self) -> None:
        """Intelligence owns a subset, not a copy of the producer's schema."""
        extended = native_event()
        extended["resolution"]["retry_budget_bucket"] = "1_3"
        extended["experimental_dimension"] = {"kind": "future"}
        envelope = self.adapter.project(extended)
        self.assertEqual(extended, envelope["payload"])

    def test_an_unsupported_producer_contract_version_fails_closed(self) -> None:
        """Acceptance 8."""
        future = native_event()
        future["schema_version"] = "l9.intelligence-feedback-event/v2"
        with self.assertRaises(ResolverFeedbackError):
            self.adapter.project(future)

    def test_a_document_missing_a_required_dimension_fails_closed(self) -> None:
        for field in ("failure", "resolution", "validation", "provenance"):
            with self.subTest(field=field):
                broken = native_event()
                del broken[field]
                with self.assertRaises(ResolverFeedbackError):
                    self.adapter.project(broken)

    def test_a_forged_producer_identity_fails_closed(self) -> None:
        forged = native_event()
        forged["event_id"] = "feedback_event_not-a-digest"
        with self.assertRaises(ResolverFeedbackError):
            self.adapter.project(forged)


class IngestionSeamTests(unittest.TestCase):
    """Acceptance 10: producer transport artifact -> IngestionService -> corpus."""

    def setUp(self) -> None:
        import tempfile

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.adapter = ResolverFeedbackAdapter()
        self.service = IngestionService(
            event_schema=EVENT_SCHEMA,
            compatibility_registry=REGISTRY,
            storage_root=Path(self.directory.name),
        )

    def ingest(self, document: dict[str, Any]) -> Any:
        return self.service.ingest(self.adapter.project(document))

    def test_a_native_feedback_event_is_accepted(self) -> None:
        """Acceptance 1."""
        result = self.ingest(native_event())
        self.assertEqual("accepted", result.status)
        self.assertIsNotNone(result.record_id)
        self.assertIsNone(result.quarantine_id)

    def test_the_stored_record_attributes_the_resolver(self) -> None:
        result = self.ingest(native_event())
        assert result.record_id is not None
        stored = json.loads(
            (
                Path(self.directory.name) / "records" / f"{result.record_id}.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(PRODUCER_ID, stored["producer_id"])
        self.assertEqual(EVENT_CLASS, stored["event_class"])
        self.assertEqual(
            PRODUCER_CONTRACT,
            stored["payload_reference"]["producer_contract"],
        )

    def test_replaying_the_identical_event_is_a_duplicate(self) -> None:
        """Acceptance 6: a second delivery is one record, two observations."""
        first = self.ingest(native_event())
        second = self.ingest(native_event())
        self.assertEqual("accepted", first.status)
        self.assertEqual("duplicate", second.status)
        self.assertEqual(first.record_id, second.record_id)
        self.assertNotEqual(first.observation_id, second.observation_id)

    def test_the_same_identity_with_an_altered_payload_is_never_conflated(
        self,
    ) -> None:
        """Acceptance 7, as the storage contract actually admits it.

        The literal `fingerprint_collision` disposition is unreachable for any
        producer: `normalized_payload_hash` is itself an input to
        `record_id`, so a changed payload cannot collide with a stored record's
        `content_hash`. The property that disposition exists to protect still
        has to hold, and it does -- two different producer documents claiming
        one identity resolve to two distinct records with distinct lineage,
        never to a silent duplicate observation of the first.
        """
        original = native_event()
        tampered = native_event()
        tampered["resolution"]["terminal_state"] = "repeated_failure"
        self.assertEqual(original["event_id"], tampered["event_id"])

        first = self.ingest(original)
        second = self.ingest(tampered)
        self.assertEqual("accepted", first.status)
        self.assertNotEqual("duplicate", second.status)
        self.assertNotEqual(first.record_id, second.record_id)
        self.assertNotEqual(
            self.adapter.project(original)["lineage"]["producer_event_hash"],
            self.adapter.project(tampered)["lineage"]["producer_event_hash"],
        )

    def test_a_sensitive_payload_is_quarantined(self) -> None:
        """Acceptance 9: Intelligence re-inspects, it does not trust the flag."""
        leaking = native_event()
        leaking["limitations"] = ["log truncated at /home/runner/work/repo/build.log"]
        result = self.ingest(leaking)
        self.assertEqual("quarantined", result.status)
        self.assertIsNone(result.record_id)
        self.assertTrue(
            any("absolute-path" in item for item in result.limitations),
            result.limitations,
        )

    def test_a_secret_bearing_payload_is_quarantined(self) -> None:
        leaking = native_event()
        leaking["provider"] = "authorization: Bearer ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        result = self.ingest(leaking)
        self.assertEqual("quarantined", result.status)
        self.assertIsNone(result.record_id)

    def test_the_retired_phantom_contract_is_refused(self) -> None:
        """Acceptance 5: nothing may enter the corpus as the old token."""
        envelope = self.adapter.project(native_event())
        envelope["producer_contract"] = "l9.resolver-corpus-event/v1"
        result = self.service.ingest(envelope)
        self.assertEqual("quarantined", result.status)


class BoundaryTests(unittest.TestCase):
    def test_intelligence_never_imports_the_producer_implementation(self) -> None:
        """Acceptance 11: the seam is a contract, not a dependency."""
        violations = [
            path.relative_to(ROOT).as_posix()
            for path in SOURCE.rglob("*.py")
            if "l9_debt_resolver" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], violations)

    def test_the_consumer_schema_is_a_subset_not_a_copy(self) -> None:
        """A copied producer schema would make Intelligence a second authority."""
        schema = json.loads(
            (
                ROOT / "schemas/intelligence/consumers/resolver-feedback.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(schema["additionalProperties"])
        self.assertNotIn(
            "l9://resolver/",
            schema["$id"],
        )


if __name__ == "__main__":
    unittest.main()
