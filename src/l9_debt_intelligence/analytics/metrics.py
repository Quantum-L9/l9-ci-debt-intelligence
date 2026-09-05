from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations
from statistics import mean, median

from .models import LearningObservation


def percentile_95(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return float(ordered[rank])


def recurrence_rows(
    observations: Iterable[LearningObservation],
) -> list[dict[str, object]]:
    groups: dict[
        tuple[str, str],
        list[LearningObservation],
    ] = defaultdict(list)
    for item in observations:
        groups[(item.recurrence_fingerprint, item.event_class)].append(item)
    rows: list[dict[str, object]] = []
    for fingerprint, event_class in sorted(groups):
        members = groups[(fingerprint, event_class)]
        scopes = sorted({item.occurrence_scope for item in members})
        producers = {item.producer_id for item in members}
        # Carried so candidate compilation can join this row against
        # `effectiveness_rows`, which groups by `canonical_rule_id`. Without it
        # the only key a candidate could look up was None -- the unattributed
        # bucket -- so a rule's own repair-success and false-positive evidence
        # was unreachable and two of the five score components stayed zero for
        # every rule-attributed candidate, whatever feedback arrived.
        #
        # Only emitted when the group agrees. A fingerprint group is normally
        # one rule (the SDK construction derives the fingerprint from the rule
        # id), but that is a property of one producer's fingerprinting, not a
        # guarantee across producers, and joining a disagreeing group to one
        # rule's effectiveness would attribute another rule's repair history.
        rule_ids = {item.canonical_rule_id for item in members}
        canonical_rule_id = rule_ids.pop() if len(rule_ids) == 1 else None
        rows.append(
            {
                "recurrence_fingerprint": fingerprint,
                "event_class": event_class,
                "canonical_rule_id": canonical_rule_id,
                "occurrence_count": len(members),
                "distinct_scope_count": len(scopes),
                "distinct_producer_count": len(producers),
                "first_scope": scopes[0],
                "last_scope": scopes[-1],
            }
        )
    return rows


def cooccurrence_rows(
    observations: Iterable[LearningObservation],
) -> list[dict[str, object]]:
    scope_fingerprints: dict[str, set[str]] = defaultdict(set)
    for item in observations:
        scope_fingerprints[item.occurrence_scope].add(item.recurrence_fingerprint)
    fingerprint_scopes: dict[str, set[str]] = defaultdict(set)
    pair_scopes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for scope, fingerprints in scope_fingerprints.items():
        ordered = sorted(fingerprints)
        for fingerprint in ordered:
            fingerprint_scopes[fingerprint].add(scope)
        for left, right in combinations(ordered, 2):
            pair_scopes[(left, right)].add(scope)
    rows: list[dict[str, object]] = []
    for left, right in sorted(pair_scopes):
        shared = len(pair_scopes[(left, right)])
        left_count = len(fingerprint_scopes[left])
        right_count = len(fingerprint_scopes[right])
        union = left_count + right_count - shared
        rows.append(
            {
                "left_fingerprint": left,
                "right_fingerprint": right,
                "shared_scope_count": shared,
                "left_scope_count": left_count,
                "right_scope_count": right_count,
                "jaccard_ratio": (round(shared / union, 12) if union else 0.0),
            }
        )
    return rows


def effort_rows(
    observations: Iterable[LearningObservation],
) -> list[dict[str, object]]:
    groups: dict[
        tuple[str, str | None],
        list[LearningObservation],
    ] = defaultdict(list)
    for item in observations:
        groups[(item.event_class, item.remediation_class)].append(item)
    rows: list[dict[str, object]] = []
    for event_class, remediation_class in sorted(
        groups,
        key=lambda value: (
            value[0],
            value[1] or "",
        ),
    ):
        members = groups[(event_class, remediation_class)]
        known = [
            item.effort_minutes for item in members if item.effort_minutes is not None
        ]
        unknown_count = len(members) - len(known)
        rows.append(
            {
                "event_class": event_class,
                "remediation_class": remediation_class,
                "known_observation_count": len(known),
                "unknown_observation_count": unknown_count,
                "total_minutes": sum(known) if known else None,
                "mean_minutes": (round(mean(known), 12) if known else None),
                "median_minutes": (float(median(known)) if known else None),
                "p95_minutes": percentile_95(known),
            }
        )
    return rows


def effectiveness_rows(
    observations: Iterable[LearningObservation],
) -> list[dict[str, object]]:
    groups: dict[
        str | None,
        list[LearningObservation],
    ] = defaultdict(list)
    for item in observations:
        groups[item.canonical_rule_id].append(item)
    rows: list[dict[str, object]] = []
    for rule_id in sorted(
        groups,
        key=lambda value: value or "",
    ):
        members = groups[rule_id]
        dispositions = [item.false_positive_disposition for item in members]
        false_positive = dispositions.count("confirmed_false_positive")
        true_positive = dispositions.count("confirmed_true_positive")
        inconclusive = dispositions.count("inconclusive")
        unknown = len(dispositions) - (false_positive + true_positive + inconclusive)
        classified = false_positive + true_positive
        outcomes = [item.validation_outcome for item in members]
        successful = outcomes.count("passed")
        failed = outcomes.count("failed")
        partial = outcomes.count("partial")
        validation_unknown = len(outcomes) - (successful + failed + partial)
        known_attempts = successful + failed + partial
        rows.append(
            {
                "canonical_rule_id": rule_id,
                "confirmed_false_positive_count": false_positive,
                "confirmed_true_positive_count": true_positive,
                "inconclusive_count": inconclusive,
                "unknown_count": unknown,
                "false_positive_ratio": (
                    round(false_positive / classified, 12) if classified else None
                ),
                "attempt_count": len(members),
                "successful_count": successful,
                "failed_count": failed,
                "partial_count": partial,
                "validation_unknown_count": validation_unknown,
                "success_ratio": (
                    round(successful / known_attempts, 12) if known_attempts else None
                ),
            }
        )
    return rows
