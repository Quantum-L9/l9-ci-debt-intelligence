from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from l9_debt_intelligence.contracts.errors import SchemaValidationError
from l9_debt_intelligence.ingestion.historical_resolution import (
    HistoricalResolutionAdapter,
)
from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.ingestion.verify import verify_store
from l9_debt_intelligence.snapshots.source import load_verified_records

ROOT = Path(__file__).resolve().parents[3]


def _adapter() -> HistoricalResolutionAdapter:
    return HistoricalResolutionAdapter(
        consumer_schema=(
            ROOT
            / "schemas/intelligence/consumers/historical-resolution-event.schema.json"
        )
    )


def _service(tmp_path: Path) -> IngestionService:
    return IngestionService(
        event_schema=ROOT / "schemas/intelligence/corpus-event.schema.json",
        compatibility_registry=ROOT / ".l9/producer-compatibility.json",
        storage_root=tmp_path,
    )


def _native(kind: str) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": "l9.historical-resolution-event/v1",
        "event_id": f"historical.hep_fixture.{kind}",
        "episode_id": "hep_fixture",
        "observation_kind": kind,
        "occurred_at": "2026-05-14T18:21:13Z",
        "repository_identity": "repository_" + "a" * 64,
        "snapshot_or_run_id": "hist-episode:hep_fixture",
        "parent_event_ids": [],
        "failure": {"semantic_failure_identity": "historical:abc"},
        "intervention": {"change_fingerprint": "c102"},
        "validation": {"outcome": "passed", "equivalent_validation": True},
        "historical_evidence": {
            "grade": "B",
            "attribution_strength": "strong",
            "evidence_completeness_percent": 92,
            "replay_fidelity": "not_attempted",
        },
        "source": {"provider": "github", "workflow_run_ref": "19281272"},
        "limitations": ["original_job_log_expired"],
        "unknowns": [{"field": "canonical_rule_id", "reason": "not_observed"}],
        "provenance": {
            "reconstruction_algorithm": "historical-reconstructor/1",
            "source_observation_hashes": ["9234", "a781"],
        },
    }
    if kind == "CI_failure_classification":
        event["intervention"] = None
        event["validation"] = None
    elif kind == "repair_attempt":
        event["validation"] = None
        event["parent_event_ids"] = ["historical.hep_fixture.failure"]
    else:
        event["intervention"] = None
        event["parent_event_ids"] = ["historical.hep_fixture.repair"]
    return event


@pytest.mark.parametrize(
    "kind",
    ["CI_failure_classification", "repair_attempt", "verification_outcome"],
)
def test_native_historical_event_traverses_real_p1(kind: str, tmp_path: Path) -> None:
    adapter = _adapter()
    service = _service(tmp_path)
    projected = adapter.project(_native(kind))
    first = service.ingest(projected)
    second = service.ingest(projected)
    assert first.status == "accepted"
    assert second.status == "duplicate"
    assert first.record_id == second.record_id


def test_additive_native_field_is_preserved(tmp_path: Path) -> None:
    native = _native("verification_outcome")
    native["future_additive_field"] = {"version": 2}
    projected = _adapter().project(native)
    assert projected["payload"]["future_additive_field"] == {"version": 2}
    assert _service(tmp_path).ingest(projected).status == "accepted"


def test_float_diagnostic_is_rejected_before_p1() -> None:
    native = _native("verification_outcome")
    native["historical_evidence"]["causal_confidence"] = 0.94
    with pytest.raises(SchemaValidationError):
        _adapter().project(native)


def test_unknown_contract_is_quarantined_by_real_p1(tmp_path: Path) -> None:
    projected = _adapter().project(_native("verification_outcome"))
    projected["producer_contract"] = "l9.historical-resolution-event/v999"
    result = _service(tmp_path).ingest(projected)
    assert result.status == "quarantined"


def test_sensitive_native_payload_is_quarantined_by_real_p1(
    tmp_path: Path,
) -> None:
    native = _native("verification_outcome")
    native["source"]["authorization"] = "Bearer ghp_abcdefghijklmnopqrstuvwxyz123456"
    projected = _adapter().project(native)
    result = _service(tmp_path).ingest(projected)
    assert result.status == "quarantined"


def test_projection_is_deterministic() -> None:
    native = _native("verification_outcome")
    assert _adapter().project(native) == _adapter().project(deepcopy(native))


def test_algorithm_replacement_emits_correction_instead_of_second_active_claim(
    tmp_path: Path,
) -> None:
    adapter = _adapter()
    service = _service(tmp_path)
    first_native = _native("verification_outcome")
    first = service.ingest_or_correct(adapter.project(first_native))
    replacement_native = deepcopy(first_native)
    replacement_native["provenance"]["reconstruction_algorithm"] = (
        "historical-reconstructor/2"
    )
    second = service.ingest_or_correct(adapter.project(replacement_native))
    assert first.status == "accepted"
    assert second.status == "accepted"
    assert first.record_id != second.record_id
    corrections = list((tmp_path / "corrections").glob("cc_*.json"))
    assert len(corrections) == 1
    document = json.loads(corrections[0].read_text(encoding="utf-8"))
    assert document["schema_version"] == "l9.corpus-correction/v1"
    assert document["target_record_id"] == first.record_id
    assert document["replacement_event_id"] == first_native["event_id"]
    assert document["reason"] == (
        "reconstruction algorithm replacement without contract change"
    )
    records = list((tmp_path / "records").glob("cr_*.json"))
    assert len(records) == 2
    for path in records:
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["superseded_by"] is None
    assert verify_store(tmp_path)["correction_count"] == 1
    snapshot = {
        item.record_id: item.superseded_by for item in load_verified_records(tmp_path)
    }
    assert snapshot[first.record_id] == second.record_id
    assert snapshot[second.record_id] is None


def test_identical_redelivery_does_not_write_a_correction(tmp_path: Path) -> None:
    adapter = _adapter()
    service = _service(tmp_path)
    native = _native("repair_attempt")
    first = service.ingest_or_correct(adapter.project(native))
    second = service.ingest_or_correct(adapter.project(deepcopy(native)))
    assert first.status == "accepted"
    assert second.status == "duplicate"
    assert first.record_id == second.record_id
    assert list((tmp_path / "corrections").glob("cc_*.json")) == []
