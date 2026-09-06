"""Mined repair history must reach candidate scoring.

`LearningProjector` dispatched on two contracts. The historical miner's
`l9.historical-resolution-event/v1` matched neither, so its whole output fell to
`_generic_observations`: a record-local fingerprint that can never aggregate,
and `validation_outcome`, `remediation_class` and `false_positive_disposition`
all left `None`.

Those three carry 0.50 of the candidate score between them, and reconstructed
repair history is the only source of repair evidence the constellation has. So
no candidate could pass the 4.0 promotion threshold however much history was
ingested, `assemble-defense-pack` refused at its publication gate, and the
Intelligence -> LSP seam stayed unestablished.

Measured before and after, through the repository's own scoring:

    static findings only ......................... 2.5  (hard ceiling)
    + historical repair outcomes ................. 2.5  (still, fp_ratio None)
    + confirmed-true-positive disposition ........ 3.5  compiled_candidate
    + 10 occurrences across 5 scopes ............. 4.25 promotion_eligible
"""

from __future__ import annotations

import unittest

from l9_debt_intelligence.compilation.scoring import calculate_score
from l9_debt_intelligence.ingestion.learning import (
    HISTORICAL_CONTRACT,
    LearningProjector,
)

RECORD = "cr_" + "b" * 64
SCOPE = "repository_" + "a" * 64
RULE = "ruff::E501"


def _event(
    *,
    outcome: str | None = "clean_verified",
    authority: str = "canonical",
    suspected_flake: bool = False,
    kind: str = "verification_outcome",
    intervention: dict[str, object] | None = None,
    repository_identity: str | None = SCOPE,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "failure": {
            "semantic_failure_identity": RULE,
            "identity_authority": authority,
        },
        "intervention": intervention,
        "validation": None if outcome is None else {"outcome": outcome},
        "historical_evidence": {"grade": "B", "suspected_flake": suspected_flake},
    }
    if repository_identity is not None:
        payload["repository_identity"] = repository_identity
    return {
        "producer_id": "Quantum-L9/l9-ci-debt-intelligence",
        "producer_contract": HISTORICAL_CONTRACT,
        "event_class": kind,
        "payload": payload,
    }


def _project(**kwargs: object) -> tuple[dict[str, object], list[str]]:
    observations, limitations = LearningProjector().project(
        _event(**kwargs),  # type: ignore[arg-type]
        record_id=RECORD,
    )
    return observations[0], list(limitations)


class TestTheContractIsRouted(unittest.TestCase):
    def test_it_no_longer_falls_to_the_generic_projector(self) -> None:
        """The generic fallback says so in a limitation; it must be absent."""
        _, limitations = _project()
        self.assertFalse(
            [item for item in limitations if "no learning projection" in item],
            limitations,
        )

    def test_the_outcome_reaches_the_observation(self) -> None:
        observation, _ = _project()
        self.assertEqual(observation["validation_outcome"], "passed")

    def test_recurrence_is_keyed_on_the_failure_not_the_record(self) -> None:
        """The miner emits three events per episode sharing one identity.

        Keying on the record would make each a singleton, so a rule seen in ten
        repositories would score as ten unrelated occurrences of one.
        """
        first, _ = _project(kind="CI_failure_classification")
        second, _ = _project(kind="verification_outcome")
        self.assertEqual(
            first["recurrence_fingerprint"], second["recurrence_fingerprint"]
        )

    def test_the_pseudonymised_scope_is_used_verbatim(self) -> None:
        """`repository_identity` is already an HMAC from the producer."""
        observation, _ = _project()
        self.assertEqual(observation["occurrence_scope"], SCOPE)

    def test_a_missing_identity_degrades_to_record_local_and_says_so(self) -> None:
        observation, limitations = _project(repository_identity=None)
        self.assertEqual(observation["occurrence_scope"], f"record:{RECORD}")
        self.assertTrue(
            [item for item in limitations if "cannot co-occur" in item], limitations
        )


class TestOutcomeMapping(unittest.TestCase):
    def test_a_validated_repair_is_passed(self) -> None:
        for outcome in ("clean_verified", "target_failure_resolved"):
            with self.subTest(outcome=outcome):
                observation, _ = _project(outcome=outcome)
                self.assertEqual(observation["validation_outcome"], "passed")

    def test_an_unresolved_episode_is_not_a_pass(self) -> None:
        for outcome in ("repeated_failure", "new_failure"):
            with self.subTest(outcome=outcome):
                observation, _ = _project(outcome=outcome)
                self.assertEqual(observation["validation_outcome"], "failed")

    def test_an_unknown_outcome_is_unknown_not_a_guess(self) -> None:
        observation, limitations = _project(outcome="something_new")
        self.assertEqual(observation["validation_outcome"], "unknown")
        self.assertTrue(
            [
                item
                for item in limitations
                if "not a learning-observation outcome" in item
            ]
        )

    def test_no_validation_leaves_the_outcome_absent(self) -> None:
        observation, _ = _project(outcome=None)
        self.assertIsNone(observation["validation_outcome"])


class TestDisposition(unittest.TestCase):
    def test_a_validated_non_flaky_repair_is_a_confirmed_true_positive(self) -> None:
        """Silence here is not neutral.

        `effectiveness_rows` derives `false_positive_ratio` from confirmed
        dispositions only, so an all-None corpus yields None, which scores
        `false_positive_safety` as 0.0 -- indistinguishable from a rule whose
        findings were all false positives.
        """
        observation, _ = _project()
        self.assertEqual(
            observation["false_positive_disposition"], "confirmed_true_positive"
        )

    def test_a_suspected_flake_is_inconclusive_never_a_true_positive(self) -> None:
        observation, limitations = _project(suspected_flake=True)
        self.assertEqual(observation["false_positive_disposition"], "inconclusive")
        self.assertTrue([item for item in limitations if "suspected flake" in item])

    def test_a_failed_episode_claims_no_disposition(self) -> None:
        observation, _ = _project(outcome="repeated_failure")
        self.assertIsNone(observation["false_positive_disposition"])


class TestHonestyAboutWhatIsNotKnown(unittest.TestCase):
    def test_a_noncanonical_identity_is_not_passed_off_as_a_rule(self) -> None:
        observation, limitations = _project(authority="historical_noncanonical")
        self.assertIsNone(observation["canonical_rule_id"])
        self.assertTrue(
            [item for item in limitations if "canonical_rule_id is unknown" in item]
        )

    def test_a_canonical_identity_is_carried(self) -> None:
        observation, _ = _project()
        self.assertEqual(observation["canonical_rule_id"], RULE)

    def test_effort_is_unknown_rather_than_derived_from_wall_clock(self) -> None:
        """Minutes between runs would attribute queue time to the repair."""
        observation, limitations = _project()
        self.assertIsNone(observation["effort_minutes"])
        self.assertTrue(
            [item for item in limitations if "effort_minutes is unknown" in item]
        )

    def test_a_remediation_class_is_carried_when_the_miner_supplies_one(self) -> None:
        observation, _ = _project(
            intervention={"remediation_class": "formatting"},
        )
        self.assertEqual(observation["remediation_class"], "formatting")


class TestTheCeilingIsBroken(unittest.TestCase):
    """The point of the change, in the scorer's own arithmetic."""

    def test_static_findings_alone_still_cap_at_2_5(self) -> None:
        self.assertEqual(
            calculate_score(
                occurrence_count=100,
                distinct_scope_count=100,
                mean_effort_minutes=None,
                repair_success_ratio=None,
                false_positive_ratio=None,
            ).total,
            2.5,
        )

    def test_historical_repair_evidence_reaches_promotion(self) -> None:
        """10 occurrences across 5 scopes, all validated, none flaky.

        Effort stays unknown -- reconstructed history has no measured repair
        duration -- so this crosses on recurrence, scope, repair success and
        false-positive safety alone.
        """
        score = calculate_score(
            occurrence_count=10,
            distinct_scope_count=5,
            mean_effort_minutes=None,
            repair_success_ratio=1.0,
            false_positive_ratio=0.0,
        )
        self.assertEqual(score.total, 4.25)
        self.assertGreaterEqual(score.total, 4.0)

    def test_without_the_disposition_the_same_history_falls_short(self) -> None:
        """Regression guard for the None-vs-0.0 distinction."""
        self.assertLess(
            calculate_score(
                occurrence_count=10,
                distinct_scope_count=5,
                mean_effort_minutes=None,
                repair_success_ratio=1.0,
                false_positive_ratio=None,
            ).total,
            4.0,
        )


if __name__ == "__main__":
    unittest.main()
