"""The production compatibility registry must describe executable reality.

`.l9/producer-compatibility.json` is the constellation's written wiring intent.
It named five upstream producers, but four of the contracts it attributed to
them exist nowhere outside this repository -- the named repositories have never
heard of them. A machine-readable registry that lists a producer as a
production-compatible input, when nothing emits that contract, is a claim about
wiring that does not exist.

One of those four was a mis-declaration rather than a gap.
`l9-ci-debt-resolver` emits nothing called `l9.resolver-corpus-event/v1`, but it
does emit `l9.intelligence-feedback-event/v1` -- with deterministic identity, a
durable outbox, and a transport already pointed at this repository. The registry
now names the contract that exists, and `ResolverFeedbackAdapter` projects it
onto the corpus envelope, so the resolver is active on the strength of shipped
code rather than intent.

The remaining three entries stay in the registry, because they are reviewable
architecture intent worth preserving, but are marked `planned` and refused at
ingestion. These tests hold that line: only producers that actually emit their
declared contract are active, and a planned producer cannot be ingested by
declaring itself.
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

# Contracts a repository in the constellation actually emits today.
SDK_PRODUCER = "Quantum-L9/l9-ci-sdk"
SDK_CONTRACT = "l9.finding-bundle/v1"
RESOLVER_PRODUCER = "Quantum-L9/l9-ci-debt-resolver"
RESOLVER_CONTRACT = "l9.intelligence-feedback-event/v1"

ACTIVE = {
    SDK_PRODUCER: (SDK_CONTRACT, "static_finding"),
    RESOLVER_PRODUCER: (RESOLVER_CONTRACT, "verification_outcome"),
}

PLANNED = {
    "Quantum-L9/l9-ci-core": "l9.core-gate-event/v1",
    "Quantum-L9/PR_Repair": "l9.repair-learning-packet/v1",
    "Quantum-L9/l9-ci-debt-lsp": "l9.editor-outcome-event/v1",
}

# The contract the registry once attributed to the resolver. Nothing emits it.
RETIRED_PHANTOM_CONTRACT = "l9.resolver-corpus-event/v1"


class ProducerStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CompatibilityRegistry.load(REGISTRY)
        self.document = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_only_shipped_producers_are_active(self) -> None:
        self.assertEqual(set(ACTIVE), set(self.registry.active_producer_ids))

    def test_the_phantom_resolver_contract_is_gone(self) -> None:
        """The registry may not name a token no repository emits."""
        self.assertNotIn(
            RETIRED_PHANTOM_CONTRACT,
            REGISTRY.read_text(encoding="utf-8"),
        )

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

    def test_every_active_producer_input_is_accepted(self) -> None:
        for producer_id, (contract_version, event_class) in ACTIVE.items():
            with self.subTest(producer=producer_id):
                contract = self.registry.validate(
                    producer_id=producer_id,
                    event_class=event_class,
                    producer_contract=contract_version,
                    sdk_contract="l9.integration-contract/v1",
                )
                self.assertEqual(producer_id, contract.producer_id)

    def test_the_resolver_may_not_emit_its_retired_contract(self) -> None:
        with self.assertRaises(ProducerCompatibilityError):
            self.registry.validate(
                producer_id=RESOLVER_PRODUCER,
                event_class="verification_outcome",
                producer_contract=RETIRED_PHANTOM_CONTRACT,
                sdk_contract="l9.integration-contract/v1",
            )

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
        document["producers"][SDK_PRODUCER]["status"] = "probably-fine"
        path = ROOT / "tests" / "fixtures" / "producers" / ".tmp-invalid-status.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        try:
            with self.assertRaises(ProducerCompatibilityError):
                CompatibilityRegistry.load(path)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
