from __future__ import annotations

import json
import unittest
from pathlib import Path

from l9_debt_intelligence.contracts.validator import EventValidator

ROOT = Path(__file__).resolve().parents[2]


class EventValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = EventValidator(
            event_schema=(ROOT / "schemas/intelligence/corpus-event.schema.json"),
            compatibility_registry=(ROOT / ".l9/producer-compatibility.json"),
        )
        self.valid_event = json.loads(
            (ROOT / "tests/fixtures/producers/valid-sdk-finding-bundle.json").read_text(
                encoding="utf-8"
            )
        )

    def test_known_compatible_event_is_accepted(self) -> None:
        result = self.validator.validate(self.valid_event)
        self.assertEqual("accepted", result.status)
        self.assertIsNone(result.quarantine_reason)

    def test_unknown_producer_is_quarantined(self) -> None:
        event = dict(self.valid_event)
        event["producer_id"] = "Unknown/example"
        result = self.validator.validate(event)
        self.assertEqual("quarantined", result.status)
        self.assertEqual(
            "ProducerCompatibilityError",
            result.quarantine_reason,
        )

    def test_incompatible_sdk_contract_is_quarantined(self) -> None:
        event = dict(self.valid_event)
        event["sdk_contract"] = "l9.integration-contract/v999"
        result = self.validator.validate(event)
        self.assertEqual("quarantined", result.status)
        self.assertEqual(
            "SDKCompatibilityError",
            result.quarantine_reason,
        )

    def test_event_hash_is_deterministic(self) -> None:
        first = self.validator.validate(self.valid_event)
        second = self.validator.validate(self.valid_event)
        self.assertEqual(first.event_hash, second.event_hash)
        self.assertEqual(64, len(first.event_hash))


if __name__ == "__main__":
    unittest.main()
