"""Candidate scoring must read a rule's own repair evidence.

`effectiveness_rows` groups by `canonical_rule_id`. `recurrence_rows` emitted no
rule id, so `extract_candidates` looked its effectiveness up as
`effectiveness_index.get(None, {})` -- the unattributed bucket, and the only key
that could ever match. Two of the five score components come from that lookup:

    repair_success           0.15
    false_positive_safety    0.20

So 0.35 of the weight was unreachable for every rule-attributed candidate no
matter what repair-outcome feedback arrived, and a candidate could never leave
`deferred`. That is separate from the structural ceiling pinned at the bottom of
this module, and it would have survived any amount of resolver feedback.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from l9_debt_intelligence.analytics.metrics import recurrence_rows
from l9_debt_intelligence.analytics.models import LearningObservation
from l9_debt_intelligence.compilation.candidates import extract_candidates
from l9_debt_intelligence.compilation.scoring import calculate_score

RULE = "l9.rule.python.broad-except"
OTHER_RULE = "l9.rule.python.mutable-default"
FINGERPRINT = "f" * 64


def _observation(
    *,
    scope: str,
    rule: str | None = RULE,
    fingerprint: str = FINGERPRINT,
) -> LearningObservation:
    return LearningObservation(
        record_id="cr_" + "0" * 61,
        producer_id="Quantum-L9/l9-ci-sdk",
        event_class="static_finding",
        producer_contract="l9.finding-bundle/v1",
        occurrence_scope=scope,
        recurrence_fingerprint=fingerprint,
        canonical_rule_id=rule,
    )


class TestRecurrenceRowsCarryTheRule(unittest.TestCase):
    def test_an_agreeing_group_carries_its_rule(self) -> None:
        rows = recurrence_rows(
            [
                _observation(scope="repository_a"),
                _observation(scope="repository_b"),
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["canonical_rule_id"], RULE)
        self.assertEqual(rows[0]["occurrence_count"], 2)

    def test_a_disagreeing_group_carries_no_rule(self) -> None:
        """Rather than attributing one rule's repair history to another.

        A fingerprint group is normally one rule, but that is a property of the
        SDK's fingerprint construction, not a cross-producer guarantee.
        """
        rows = recurrence_rows(
            [
                _observation(scope="repository_a", rule=RULE),
                _observation(scope="repository_b", rule=OTHER_RULE),
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["canonical_rule_id"])

    def test_a_group_with_no_rule_at_all_carries_none(self) -> None:
        rows = recurrence_rows([_observation(scope="repository_a", rule=None)])
        self.assertIsNone(rows[0]["canonical_rule_id"])


class TestCandidateJoin(unittest.TestCase):
    """`extract_candidates` against reports written to disk, as it runs."""

    def _analysis(
        self,
        root: Path,
        *,
        recurrence_rule: str | None,
        occurrence_count: int = 4,
        distinct_scope_count: int = 5,
    ) -> Path:
        path = root / "analysis"
        path.mkdir(parents=True, exist_ok=True)
        (path / "manifest.json").write_text(
            json.dumps(
                {
                    "source_snapshot_id": "snap_" + "1" * 59,
                    "analysis_run_id": "run_" + "2" * 60,
                }
            ),
            encoding="utf-8",
        )
        (path / "recurrence-report.json").write_text(
            json.dumps(
                {
                    "rows": [
                        {
                            "recurrence_fingerprint": FINGERPRINT,
                            "event_class": "static_finding",
                            "canonical_rule_id": recurrence_rule,
                            "occurrence_count": occurrence_count,
                            "distinct_scope_count": distinct_scope_count,
                        }
                    ],
                    "limitations": [],
                }
            ),
            encoding="utf-8",
        )
        (path / "effort-atlas.json").write_text(
            json.dumps(
                {
                    "rows": [
                        {"event_class": "static_finding", "mean_minutes": 120.0},
                    ],
                    "limitations": [],
                }
            ),
            encoding="utf-8",
        )
        # The rule's own evidence is clean and successful; the unattributed
        # bucket is the opposite. A candidate that reads the wrong one is
        # visible in the score rather than only in a field.
        (path / "rule-effectiveness.json").write_text(
            json.dumps(
                {
                    "rows": [
                        {
                            "canonical_rule_id": RULE,
                            "success_ratio": 1.0,
                            "false_positive_ratio": 0.0,
                        },
                        {
                            "canonical_rule_id": None,
                            "success_ratio": 0.0,
                            "false_positive_ratio": 1.0,
                        },
                    ],
                    "limitations": [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_a_candidate_reads_its_own_rules_repair_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            path = self._analysis(Path(tmp), recurrence_rule=RULE)
            candidates = extract_candidates(path)
        self.assertEqual(len(candidates), 1)
        expected = calculate_score(
            occurrence_count=4,
            distinct_scope_count=5,
            mean_effort_minutes=120.0,
            repair_success_ratio=1.0,
            false_positive_ratio=0.0,
        )
        self.assertEqual(candidates[0]["score"], expected.total)
        # And that is enough to leave `deferred`, which no rule-attributed
        # candidate could do while the join was pinned to None.
        self.assertEqual(candidates[0]["state"], "promotion_eligible")

    def test_the_unattributed_bucket_is_still_the_fallback(self) -> None:
        """A row with no rule id has nothing else to read."""
        with TemporaryDirectory() as tmp:
            path = self._analysis(Path(tmp), recurrence_rule=None)
            candidates = extract_candidates(path)
        expected = calculate_score(
            occurrence_count=4,
            distinct_scope_count=5,
            mean_effort_minutes=120.0,
            repair_success_ratio=0.0,
            false_positive_ratio=1.0,
        )
        self.assertEqual(candidates[0]["score"], expected.total)

    def test_an_unknown_rule_falls_back_rather_than_scoring_zero(self) -> None:
        """A rule with no effectiveness row reads the unattributed bucket.

        Scored identically to a row carrying no rule id, which is the honest
        reading: nothing is known about this rule specifically, so the corpus
        aggregate is the best available evidence. It must not silently become
        a zero, which would be a claim that repair always fails.
        """
        with TemporaryDirectory() as tmp:
            unknown = self._analysis(
                Path(tmp) / "unknown", recurrence_rule="l9.rule.not.present"
            )
            unattributed = self._analysis(Path(tmp) / "none", recurrence_rule=None)
            self.assertEqual(
                extract_candidates(unknown)[0]["score"],
                extract_candidates(unattributed)[0]["score"],
            )


class TestStructuralCeiling(unittest.TestCase):
    """Why L4-04 cannot be unblocked without the learning path.

    Not a defect -- an invariant worth stating in a test, because it is the
    reason `assemble-defense-pack` refuses on a corpus of static findings alone
    and no amount of SDK ingestion changes that.
    """

    def test_static_findings_alone_cannot_reach_promotion(self) -> None:
        best = calculate_score(
            # Both components maxed: 10+ occurrences, 5+ distinct scopes.
            occurrence_count=100,
            distinct_scope_count=100,
            # Only resolver repair-outcome feedback supplies these three.
            mean_effort_minutes=None,
            repair_success_ratio=None,
            false_positive_ratio=None,
        )
        self.assertEqual(best.total, 2.5)
        self.assertLess(best.total, 4.0)

    def test_repair_evidence_is_what_crosses_the_threshold(self) -> None:
        with_repair = calculate_score(
            occurrence_count=4,
            distinct_scope_count=5,
            mean_effort_minutes=120.0,
            repair_success_ratio=1.0,
            false_positive_ratio=0.0,
        )
        self.assertGreaterEqual(with_repair.total, 4.0)


if __name__ == "__main__":
    unittest.main()
