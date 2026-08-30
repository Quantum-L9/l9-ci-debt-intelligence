"""The production compatibility registry must describe executable reality.

`.l9/producer-compatibility.json` is the constellation's written wiring intent.
It named five upstream producers, but four of the contracts it attributed to
them exist nowhere outside this repository -- the named repositories have never
heard of them. A machine-readable registry that lists a producer as a
production-compatible input, when nothing emits that contract, is a claim about
wiring that does not exist.

The registry keeps those four entries, because they are reviewable architecture
intent worth preserving, but marks them `planned` and refuses them at
ingestion. These tests hold that line: exactly one producer is active in v0.1,
and a planned producer cannot be ingested by declaring itself.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from l9_debt_intelligence.contracts.errors import ProducerCompatibilityError
from l9_debt_intelligence.contracts.registry import CompatibilityRegistry
from l9_debt_intelligence.contracts.validator import EventValidator

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".l9/producer-compatibility.json"

# The only contract any repository in the constellation actually emits.
ACTIVE_PRODUCER = "Quantum-L9/l9-ci-sdk"
ACTIVE_CONTRACT = "l9.finding-bundle/v1"

PLANNED = {
    "Quantum-L9/l9-ci-core": "l9.core-gate-event/v1",
    "Quantum-L9/l9-ci-debt-resolver": "l9.resolver-corpus-event/v1",
    "Quantum-L9/PR_Repair": "l9.repair-learning-packet/v1",
    "Quantum-L9/l9-ci-debt-lsp": "l9.editor-outcome-event/v1",
}


class ProducerStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CompatibilityRegistry.load(REGISTRY)
        self.document = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_exactly_one_producer_is_active(self) -> None:
        self.assertEqual({ACTIVE_PRODUCER}, set(self.registry.active_producer_ids))

    def test_every_phantom_producer_is_marked_planned(self) -> None:
        self.assertEqual(set(PLANNED), set(self.registry.planned_producer_ids))

    def test_every_producer_declares_an_explicit_status(self) -> None:
        """No entry may rely on the backwards-compatible `active` default."""
        for producer_id, value in self.document["producers"].items():
            with self.subTest(producer=producer_id):
                self.assertIn(value.get("status"), {"active", "planned"})

    def test_every_planned_producer_records_why(self) -> None:
        for producer_id, value in self.document["producers"].items():
            if value.get("status") != "planned":
                continue
            with self.subTest(producer=producer_id):
                self.assertTrue(value.get("planned_reason"))

    def test_the_sdk_finding_bundle_input_is_still_accepted(self) -> None:
        contract = self.registry.validate(
            producer_id=ACTIVE_PRODUCER,
            event_class="static_finding",
            producer_contract=ACTIVE_CONTRACT,
            sdk_contract="l9.integration-contract/v1",
        )
        self.assertEqual(ACTIVE_PRODUCER, contract.producer_id)

    def test_planned_producers_are_refused_by_the_registry(self) -> None:
        for producer_id, contract_version in PLANNED.items():
            with self.subTest(producer=producer_id):
                with self.assertRaises(ProducerCompatibilityError) as caught:
                    self.registry.validate(
                        producer_id=producer_id,
                        event_class=next(
                            iter(
                                self.document["producers"][producer_id]["event_classes"]
                            )
                        ),
                        producer_contract=contract_version,
                        sdk_contract="l9.integration-contract/v1",
                    )
                self.assertIn("not active", str(caught.exception))

    def test_a_planned_producer_event_is_quarantined_not_ingested(self) -> None:
        """End to end: a real l9-ci-core gate event does not enter the corpus."""
        validator = EventValidator(
            event_schema=(ROOT / "schemas/intelligence/corpus-event.schema.json"),
            compatibility_registry=REGISTRY,
        )
        event = json.loads(
            (ROOT / "tests/fixtures/producers/valid-core-gate.json").read_text(
                encoding="utf-8"
            )
        )
        result = validator.validate(event)
        self.assertEqual("quarantined", result.status)
        self.assertEqual("ProducerCompatibilityError", result.quarantine_reason)

    def test_an_unknown_status_is_rejected_rather_than_assumed_active(self) -> None:
        document = json.loads(REGISTRY.read_text(encoding="utf-8"))
        document["producers"][ACTIVE_PRODUCER]["status"] = "probably-fine"
        path = ROOT / "tests" / "fixtures" / "producers" / ".tmp-invalid-status.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        try:
            with self.assertRaises(ProducerCompatibilityError):
                CompatibilityRegistry.load(path)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
