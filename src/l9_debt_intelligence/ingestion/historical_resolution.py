from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.contracts.errors import SchemaValidationError

HISTORICAL_PRODUCER_ID = "Quantum-L9/l9-ci-debt-intelligence"
HISTORICAL_CONTRACT = "l9.historical-resolution-event/v1"
SDK_CONTRACT = "l9.integration-contract/v1"


class HistoricalResolutionAdapter:
    """Validate one native historical event and project it onto the P1 envelope."""

    def __init__(self, *, consumer_schema: Path) -> None:
        schema = json.loads(consumer_schema.read_text(encoding="utf-8"))
        self._validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    def validate(self, document: Mapping[str, Any]) -> None:
        errors = sorted(
            self._validator.iter_errors(dict(document)),
            key=lambda error: tuple(str(part) for part in error.path),
        )
        if errors:
            message = "; ".join(
                f"{'/'.join(str(part) for part in error.path) or '<root>'}: "
                f"{error.message}"
                for error in errors
            )
            raise SchemaValidationError(message)
        if _contains_float(document):
            raise SchemaValidationError(
                "native historical events must not contain floating-point diagnostics"
            )

    def project(self, document: Mapping[str, Any]) -> dict[str, Any]:
        self.validate(document)
        native = dict(document)
        observation_kind = str(native["observation_kind"])
        return {
            "schema_version": "l9.corpus-event/v1",
            "producer_id": HISTORICAL_PRODUCER_ID,
            "producer_contract": HISTORICAL_CONTRACT,
            "sdk_contract": SDK_CONTRACT,
            "event_id": str(native["event_id"]),
            "event_class": observation_kind,
            "event_time": str(native["occurred_at"]),
            "snapshot_or_run_id": str(native["snapshot_or_run_id"]),
            "redaction_status": "intelligence_redacted",
            "limitations": list(native.get("limitations", [])),
            "unknowns": list(native.get("unknowns", [])),
            "lineage": {
                "producer_event_hash": sha256_document(native),
                "parent_event_ids": list(native.get("parent_event_ids", [])),
            },
            "payload": native,
        }


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_float(child) for child in value)
    return False
