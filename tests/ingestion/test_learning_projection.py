"""One delivery, many observations: the grain Phase 3 has always expected.

`analytics/projection.py` reads `occurrence_scope`, `recurrence_fingerprint`,
`canonical_rule_id` and the rest off snapshot rows, and
`schemas/intelligence/learning-observation.schema.json` has always declared
them. Nothing wrote them. Every fallback in that reader fired for every record
from every producer, so a bundle of thirteen findings became one opaque
observation, recurrence could never aggregate, and no candidate could exceed
0.35 against a promotion threshold of 4.0.

The property that matters most is `test_the_same_rule_in_two_repositories_shares_a_key`.
Fleet breadth is measured by grouping on the key and counting the distinct
scopes inside each group, so a key that folded the scope in would put exactly
one scope in every group and reproduce the bug it was meant to fix.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from l9_debt_intelligence.contracts.learning_columns import (
    LEARNING_COLUMNS,
    LearningColumnError,
    coerce_row,
)
from l9_debt_intelligence.ingestion.learning import (
    LearningProjectionError,
    LearningProjector,
)
from l9_debt_intelligence.ingestion.sdk_finding_bundle import SdkFindingBundleAdapter

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "tests/fixtures/producers/native-sdk-finding-bundle.json"
RESOLVER = ROOT / "tests/fixtures/producers/valid-resolver-feedback.json"
RECORD_ID = "cr_" + "a" * 64
OTHER_RECORD_ID = "cr_" + "b" * 64
PSEUDONYM_KEY = b"p" * 48
PATH_KEY = b"t" * 48


def _sdk_event(repository: str = "Acme-Corp/private-service") -> dict[str, Any]:
    return SdkFindingBundleAdapter().project(
        json.loads(NATIVE.read_text(encoding="utf-8")),
        repository=repository,
        pseudonym_key=PSEUDONYM_KEY,
        path_key=PATH_KEY,
    )


def _resolver_event() -> dict[str, Any]:
    from l9_debt_intelligence.ingestion.resolver_feedback import (
        ResolverFeedbackAdapter,
    )

    return ResolverFeedbackAdapter().project(
        json.loads(RESOLVER.read_text(encoding="utf-8"))
    )


class FindingBundleGrain(unittest.TestCase):
    def test_one_observation_per_finding(self) -> None:
        """The regression: N canonical findings must produce N observations."""
        event = _sdk_event()
        expected = len(event["payload"]["bundle"]["findings"])
        observations, _ = LearningProjector().project(event, record_id=RECORD_ID)
        self.assertEqual(len(observations), expected)
        self.assertGreater(expected, 1, "fixture must carry more than one finding")

    def test_every_observation_names_its_parent_record(self) -> None:
        observations, _ = LearningProjector().project(_sdk_event(), record_id=RECORD_ID)
        self.assertTrue(all(item["record_id"] == RECORD_ID for item in observations))

    def test_scope_is_the_repository_pseudonym_not_the_record(self) -> None:
        """A record-local scope is what made every record its own scope."""
        event = _sdk_event()
        pseudonym = event["payload"]["repository_pseudonym"]
        observations, _ = LearningProjector().project(event, record_id=RECORD_ID)
        self.assertTrue(
            all(item["occurrence_scope"] == pseudonym for item in observations)
        )
        self.assertTrue(
            all(
                not item["occurrence_scope"].startswith("record:")
                for item in observations
            )
        )

    def test_the_same_rule_in_two_repositories_shares_a_key(self) -> None:
        """The property the whole fix rests on.

        `recurrence_rows` groups by key and counts the distinct scopes within
        each group. If the key folded the scope in, every group would hold one
        scope and `distinct_scope_count` would be permanently 1 -- which is
        exactly the failure being repaired.
        """
        first, _ = LearningProjector().project(
            _sdk_event("Acme-Corp/one"), record_id=RECORD_ID
        )
        second, _ = LearningProjector().project(
            _sdk_event("Acme-Corp/two"), record_id=OTHER_RECORD_ID
        )
        by_rule = {
            item["canonical_rule_id"]: item["recurrence_fingerprint"] for item in first
        }
        for item in second:
            self.assertEqual(
                by_rule[item["canonical_rule_id"]],
                item["recurrence_fingerprint"],
                f"key for {item['canonical_rule_id']} differs between repositories",
            )
        self.assertNotEqual(
            first[0]["occurrence_scope"],
            second[0]["occurrence_scope"],
            "the two repositories must still be distinct scopes",
        )

    def test_the_key_is_the_rule_not_the_producer_instance_fingerprint(self) -> None:
        """The SDK `fingerprint` is per-instance, not per-rule.

        In the real fixture, findings of one rule carry distinct fingerprints,
        so keying on them would prevent aggregation even inside one repository.
        """
        event = _sdk_event()
        findings = event["payload"]["bundle"]["findings"]
        instance_fingerprints = {finding["fingerprint"] for finding in findings}
        self.assertGreater(len(instance_fingerprints), 1)

        observations, _ = LearningProjector().project(event, record_id=RECORD_ID)
        by_rule: dict[str, set[str]] = {}
        for item in observations:
            by_rule.setdefault(item["canonical_rule_id"], set()).add(
                item["recurrence_fingerprint"]
            )
        repeated = {rule for rule, keys in by_rule.items() if len(keys) > 1}
        self.assertEqual(repeated, set(), "one rule must resolve to one key")
        # And the fixture genuinely repeats a rule, so the assertion has teeth.
        self.assertTrue(
            any(
                sum(1 for i in observations if i["canonical_rule_id"] == rule) > 1
                for rule in by_rule
            )
        )

    def test_a_finding_without_a_canonical_rule_id_is_recorded_not_guessed(
        self,
    ) -> None:
        event = _sdk_event()
        for finding in event["payload"]["bundle"]["findings"]:
            finding.pop("canonical_rule_id", None)
        observations, limitations = LearningProjector().project(
            event, record_id=RECORD_ID
        )
        self.assertTrue(all(item["canonical_rule_id"] is None for item in observations))
        self.assertTrue(
            any("canonical_rule_id" in item for item in limitations), limitations
        )

    def test_the_component_is_the_redacted_path_token(self) -> None:
        """Privacy-safe, and a stable identity for "the same file"."""
        observations, _ = LearningProjector().project(_sdk_event(), record_id=RECORD_ID)
        components = {item["component"] for item in observations}
        self.assertTrue(components)
        for component in components:
            self.assertIsNotNone(component)
            self.assertRegex(str(component), r"^path_[0-9a-f]{64}$")

    def test_no_effort_or_disposition_is_invented(self) -> None:
        """A static finding knows nothing about repair effort."""
        observations, _ = LearningProjector().project(_sdk_event(), record_id=RECORD_ID)
        for item in observations:
            self.assertIsNone(item["effort_minutes"])
            self.assertIsNone(item["validation_outcome"])
            self.assertIsNone(item["false_positive_disposition"])
            self.assertIsNone(item["remediation_class"])

    def test_a_bundle_with_no_findings_is_recorded(self) -> None:
        event = _sdk_event()
        event["payload"]["bundle"]["findings"] = []
        observations, limitations = LearningProjector().project(
            event, record_id=RECORD_ID
        )
        self.assertEqual(observations, ())
        self.assertIn("finding bundle contained no findings", limitations)

    def test_a_malformed_payload_is_refused(self) -> None:
        event = _sdk_event()
        del event["payload"]["bundle"]
        with self.assertRaises(LearningProjectionError):
            LearningProjector().project(event, record_id=RECORD_ID)


class ResolverFeedbackGrain(unittest.TestCase):
    def test_one_verification_outcome_is_one_observation(self) -> None:
        observations, _ = LearningProjector().project(
            _resolver_event(), record_id=RECORD_ID
        )
        self.assertEqual(len(observations), 1)

    def test_the_dimensions_the_resolver_already_carried_are_read(self) -> None:
        """These were present in the event and nothing consumed them."""
        observations, _ = LearningProjector().project(
            _resolver_event(), record_id=RECORD_ID
        )
        observation = observations[0]
        self.assertEqual(observation["remediation_class"], "bounded_source")
        self.assertEqual(observation["validation_outcome"], "passed")
        self.assertTrue(observation["occurrence_scope"].startswith("repository_"))

    def test_bucketed_duration_does_not_become_a_number(self) -> None:
        """The producer reports a bucket; inventing minutes would invent precision."""
        observations, limitations = LearningProjector().project(
            _resolver_event(), record_id=RECORD_ID
        )
        self.assertIsNone(observations[0]["effort_minutes"])
        self.assertTrue(any("bucket" in item for item in limitations), limitations)

    def test_an_unrecognised_validation_result_becomes_unknown(self) -> None:
        event = _resolver_event()
        event["payload"]["validation"]["result"] = "something-new"
        observations, limitations = LearningProjector().project(
            event, record_id=RECORD_ID
        )
        self.assertEqual(observations[0]["validation_outcome"], "unknown")
        self.assertTrue(
            any("not a" in item for item in limitations),
            limitations,
        )


class UnknownProducerContract(unittest.TestCase):
    def test_an_unprojected_contract_still_produces_one_observation(self) -> None:
        """Dropping it would make the corpus and the learning view disagree."""
        event = _sdk_event()
        event["producer_contract"] = "l9.some-future-contract/v1"
        observations, limitations = LearningProjector().project(
            event, record_id=RECORD_ID
        )
        self.assertEqual(len(observations), 1)
        self.assertTrue(
            any("no learning projection" in item for item in limitations), limitations
        )

    def test_it_contributes_no_recurrence(self) -> None:
        event = _sdk_event()
        event["producer_contract"] = "l9.some-future-contract/v1"
        first, _ = LearningProjector().project(event, record_id=RECORD_ID)
        second, _ = LearningProjector().project(event, record_id=OTHER_RECORD_ID)
        self.assertNotEqual(
            first[0]["recurrence_fingerprint"],
            second[0]["recurrence_fingerprint"],
        )


class ColumnContract(unittest.TestCase):
    def test_the_column_tuple_matches_the_published_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/intelligence/learning-observation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        identity = {
            "schema_version",
            "record_id",
            "producer_id",
            "event_class",
            "producer_contract",
        }
        declared = set(schema["properties"]) - identity
        self.assertEqual(declared, set(LEARNING_COLUMNS))

    def test_the_column_tuple_matches_the_phase_3_model(self) -> None:
        """Three places name these; none may drift from the others."""
        from dataclasses import fields

        from l9_debt_intelligence.analytics.models import LearningObservation

        identity = {
            "record_id",
            "producer_id",
            "event_class",
            "producer_contract",
        }
        model = {field.name for field in fields(LearningObservation)} - identity
        self.assertEqual(model, set(LEARNING_COLUMNS))

    def test_a_row_without_a_grouping_key_is_refused(self) -> None:
        with self.assertRaises(LearningColumnError):
            coerce_row({"occurrence_scope": "repository_x"})

    def test_a_row_without_a_scope_is_refused(self) -> None:
        with self.assertRaises(LearningColumnError):
            coerce_row({"recurrence_fingerprint": "a" * 64})

    def test_unknown_keys_are_dropped_rather_than_widening_the_schema(self) -> None:
        row = coerce_row(
            {
                "occurrence_scope": "repository_x",
                "recurrence_fingerprint": "a" * 64,
                "surprise": "value",
            }
        )
        self.assertEqual(set(row), set(LEARNING_COLUMNS))

    def test_a_negative_effort_is_treated_as_unknown(self) -> None:
        row = coerce_row(
            {
                "occurrence_scope": "repository_x",
                "recurrence_fingerprint": "a" * 64,
                "effort_minutes": -5,
            }
        )
        self.assertIsNone(row["effort_minutes"])


if __name__ == "__main__":
    unittest.main()
