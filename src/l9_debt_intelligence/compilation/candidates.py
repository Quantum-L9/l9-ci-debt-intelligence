from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from l9_debt_intelligence.snapshots.hashing import (
    namespaced_document_hash,
)

from .scoring import calculate_score, candidate_state


def load_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"report must be an object: {path}")
    return value


def index_effectiveness(
    report: dict[str, Any],
) -> dict[str | None, dict[str, Any]]:
    return {
        row.get("canonical_rule_id"): row
        for row in report.get("rows", [])
        if isinstance(row, dict)
    }


def mean_effort_by_event_class(
    report: dict[str, Any],
) -> dict[str, float | None]:
    values: dict[str, list[float]] = {}
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        event_class = row.get("event_class")
        mean_value = row.get("mean_minutes")
        if not isinstance(event_class, str):
            continue
        values.setdefault(event_class, [])
        if isinstance(mean_value, (int, float)):
            values[event_class].append(float(mean_value))
    return {
        key: (round(sum(items) / len(items), 6) if items else None)
        for key, items in values.items()
    }


def extract_candidates(
    analysis_path: Path,
) -> list[dict[str, Any]]:
    manifest = load_report(analysis_path / "manifest.json")
    recurrence = load_report(analysis_path / "recurrence-report.json")
    effort = load_report(analysis_path / "effort-atlas.json")
    effectiveness = load_report(analysis_path / "rule-effectiveness.json")
    effort_index = mean_effort_by_event_class(effort)
    effectiveness_index = index_effectiveness(effectiveness)
    candidates: list[dict[str, Any]] = []
    for row in recurrence.get("rows", []):
        if not isinstance(row, dict):
            continue
        fingerprint = str(row["recurrence_fingerprint"])
        event_class = str(row["event_class"])
        # Join on this row's own rule, falling back to the unattributed bucket.
        # This was pinned at `.get(None)`, which could only ever reach the
        # unattributed bucket because `recurrence_rows` emitted no rule id --
        # so `repair_success` and `false_positive_safety`, 0.35 of the score
        # between them, were unreachable for every rule-attributed candidate.
        canonical_rule_id = row.get("canonical_rule_id")
        rule_effectiveness = effectiveness_index.get(
            canonical_rule_id if isinstance(canonical_rule_id, str) else None,
            effectiveness_index.get(None, {}),
        )
        score = calculate_score(
            occurrence_count=int(row["occurrence_count"]),
            distinct_scope_count=int(row["distinct_scope_count"]),
            mean_effort_minutes=effort_index.get(event_class),
            repair_success_ratio=rule_effectiveness.get("success_ratio"),
            false_positive_ratio=rule_effectiveness.get("false_positive_ratio"),
        )
        candidate_kind = (
            "sdk_architecture_contract"
            if event_class
            in {
                "gate_outcome",
                "CI_failure_classification",
            }
            else "ast_grep"
        )
        match_contract = {
            "event_class": event_class,
            "recurrence_fingerprint": fingerprint,
        }
        action_contract = {
            "behavior": "diagnose",
            "automatic_fix": False,
            "blocking": False,
        }
        identity = {
            "source_snapshot_id": manifest["source_snapshot_id"],
            "analysis_run_id": manifest["analysis_run_id"],
            "recurrence_fingerprint": fingerprint,
            "candidate_kind": candidate_kind,
            "match_contract": match_contract,
            "action_contract": action_contract,
        }
        candidate_id = namespaced_document_hash(
            "candidate_",
            identity,
        )
        limitations = list(
            sorted(
                set(
                    recurrence.get("limitations", [])
                    + effort.get("limitations", [])
                    + effectiveness.get("limitations", [])
                )
            )
        )
        candidates.append(
            {
                "schema_version": "l9.candidate-rule/v1",
                "candidate_id": candidate_id,
                "source_snapshot_id": manifest["source_snapshot_id"],
                "analysis_run_id": manifest["analysis_run_id"],
                "candidate_kind": candidate_kind,
                "recurrence_fingerprint": fingerprint,
                "title": (
                    f"Prevent recurring {event_class} pattern {fingerprint[:12]}"
                ),
                "rationale": (
                    f"Observed {row['occurrence_count']} times across "
                    f"{row['distinct_scope_count']} distinct scopes."
                ),
                "match_contract": match_contract,
                "action_contract": action_contract,
                "score": score.total,
                "score_components": score.as_dict(),
                "state": candidate_state(score.total),
                "limitations": limitations,
            }
        )
    return sorted(
        candidates,
        key=lambda item: item["candidate_id"],
    )
