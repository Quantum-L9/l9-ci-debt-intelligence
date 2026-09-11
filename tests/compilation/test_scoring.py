from __future__ import annotations

import unittest

from l9_debt_intelligence.compilation.scoring import (
    calculate_score,
    candidate_state,
)


class ScoringTests(unittest.TestCase):
    def test_unknowns_provide_no_positive_score(self) -> None:
        score = calculate_score(
            occurrence_count=0,
            distinct_scope_count=0,
            mean_effort_minutes=None,
            repair_success_ratio=None,
            false_positive_ratio=None,
        )
        self.assertEqual(0.0, score.total)

    def test_high_evidence_is_promotion_eligible(self) -> None:
        score = calculate_score(
            occurrence_count=10,
            distinct_scope_count=5,
            mean_effort_minutes=120,
            repair_success_ratio=1.0,
            false_positive_ratio=0.0,
        )
        self.assertEqual(5.0, score.total)
        self.assertEqual(
            "promotion_eligible",
            candidate_state(score.total),
        )

    def test_low_score_is_deferred(self) -> None:
        self.assertEqual("deferred", candidate_state(2.99))

    def test_static_signal_alone_cannot_reach_promotion(self) -> None:
        """Recurrence and scope breadth are the only components SDK finding
        bundles can populate. Saturating both yields 2.5 of the 4.0 promotion
        threshold, so a corpus fed only by static findings can never emit a
        promotion-eligible candidate. This is the designed corpus-maturity gate
        behind the intelligence_to_lsp seam: repair-success and false-positive
        history from the resolver feedback seam are required to cross it."""
        score = calculate_score(
            occurrence_count=1_000,
            distinct_scope_count=1_000,
            mean_effort_minutes=None,
            repair_success_ratio=None,
            false_positive_ratio=None,
        )
        self.assertEqual(2.5, score.total)
        self.assertEqual("deferred", candidate_state(score.total))

    def test_static_signal_plus_effort_is_still_not_promotion_eligible(self) -> None:
        """Even with effort saturated, the three history-free components cap at
        3.25: a compiled candidate at most, never promotion eligible."""
        score = calculate_score(
            occurrence_count=1_000,
            distinct_scope_count=1_000,
            mean_effort_minutes=10_000,
            repair_success_ratio=None,
            false_positive_ratio=None,
        )
        self.assertEqual(3.25, score.total)
        self.assertEqual("compiled_candidate", candidate_state(score.total))
        self.assertNotEqual("promotion_eligible", candidate_state(score.total))


if __name__ == "__main__":
    unittest.main()
