from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from l9_debt_intelligence.contracts.canonical import canonical_json
from l9_debt_intelligence.snapshots.hashing import (
    namespaced_document_hash,
    sha256_bytes,
)

from .metrics import pack_metrics, rule_metrics
from .recommendations import (
    pack_recommendation,
    rule_recommendation,
)
from .storage import OutcomeStore


def load_pack(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("defense pack must contain a JSON object")
    if value.get("schema_version") != "l9.debt-defense/v1":
        raise ValueError("unsupported defense-pack schema")
    return value


def build_effectiveness_report(
    *,
    store_root: Path,
    defense_pack_path: Path,
    reports_root: Path,
) -> dict[str, Any]:
    pack = load_pack(defense_pack_path)
    store = OutcomeStore(store_root)
    outcomes = store.load(pack_id=pack["pack_id"])
    outcome_documents = [
        {key: value for key, value in outcome.items() if key != "observed_at"}
        for outcome in outcomes
    ]
    outcome_snapshot_hash = sha256_bytes(canonical_json(outcome_documents))
    rows = rule_metrics(outcomes)
    metrics = pack_metrics(
        rows=rows,
        active_rule_count=len(pack["rules"]),
    )
    rule_recommendations = [rule_recommendation(row) for row in rows]
    recommendation_rows = [
        *rule_recommendations,
        pack_recommendation(
            pack_id=pack["pack_id"],
            metrics=metrics,
            rule_recommendations=rule_recommendations,
        ),
    ]
    limitations: list[str] = []
    if not outcomes:
        limitations.append("no effectiveness outcomes were available")
    if metrics["coverage_ratio"] != 1.0:
        limitations.append("not all active rules have effectiveness observations")
    identity = {
        "pack_id": pack["pack_id"],
        "pack_version": pack["version"],
        "outcome_snapshot_hash": outcome_snapshot_hash,
        "rule_metrics": rows,
        "pack_metrics": metrics,
        "recommendations": recommendation_rows,
    }
    report_id = namespaced_document_hash(
        "effect_",
        identity,
    )
    report = {
        "schema_version": "l9.effectiveness-report/v1",
        "report_id": report_id,
        "outcome_snapshot_hash": outcome_snapshot_hash,
        "pack_id": pack["pack_id"],
        "pack_version": pack["version"],
        "observation_count": len(outcomes),
        "rule_metrics": rows,
        "pack_metrics": metrics,
        "recommendations": recommendation_rows,
        "limitations": limitations,
    }
    reports_root = reports_root.resolve()
    reports_root.mkdir(parents=True, exist_ok=True)
    destination = reports_root / report_id
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{report_id}.",
            dir=reports_root,
        )
    )
    try:
        report_path = temporary / "effectiveness-report.json"
        report_path.write_bytes(canonical_json(report) + b"\n")
        manifest_document = {
            "schema_version": "l9.effectiveness-manifest/v1",
            "report_id": report_id,
            "pack_id": pack["pack_id"],
            "pack_version": pack["version"],
            "outcome_snapshot_hash": outcome_snapshot_hash,
            "report_sha256": sha256_bytes(canonical_json(report)),
            "observation_count": len(outcomes),
        }
        (temporary / "manifest.json").write_bytes(
            canonical_json(manifest_document) + b"\n"
        )
        if destination.exists():
            existing = json.loads(
                (destination / "effectiveness-report.json").read_text(encoding="utf-8")
            )
            if existing != report:
                raise RuntimeError("effectiveness report identity collision")
            shutil.rmtree(temporary)
        else:
            os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "schema_version": "l9.effectiveness-build-result/v1",
        "report_id": report_id,
        "report_path": (destination / "effectiveness-report.json").as_posix(),
        "manifest_path": (destination / "manifest.json").as_posix(),
        "pack_id": pack["pack_id"],
        "pack_version": pack["version"],
        "observation_count": len(outcomes),
    }
