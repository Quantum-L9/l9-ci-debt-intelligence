"""Project LSP telemetry events onto the corpus envelope.

`Quantum-L9/l9-ci-debt-lsp` emits `l9.telemetry-event/v1` into a local spool and
delivers it as `application/x-ndjson` batches. Intelligence has modelled the
editor surface since INTEL-P1 -- `corpus-event.schema.json` carries
`editor_diagnostic_outcome` and `false_positive_disposition` -- but nothing
projected the producer's document onto that surface, so the surface existed
without a wire. This adapter is the projection, and it lives here for the same
reason the Resolver's does: the corpus envelope is Intelligence's to own.

The difference between the two producers is the reason this edge matters. The
Resolver emits what already failed. The LSP emits what happened while the
developer was still typing: a diagnostic shown, dismissed, accepted as a false
positive, a quick fix applied or reverted. It is the only producer in the
constellation that can report a failure that never reached CI, which makes it
the denominator the corpus has been missing.

The producer's document is carried into `payload` whole -- never flattened or
re-keyed -- so rule identity, pack version, disposition, latency bucket and the
installation pseudonym survive intact for downstream learning.
`lineage.producer_event_hash` binds the projection to the canonical producer
document independent of key order or insignificant whitespace.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.contracts.errors import ContractError

PRODUCER_ID = "Quantum-L9/l9-ci-debt-lsp"
PRODUCER_CONTRACT = "l9.telemetry-event/v1"
SDK_CONTRACT = "l9.integration-contract/v1"

#: The producer's own event types, mapped onto the corpus classes Intelligence
#: already defines. Everything the LSP reports about a diagnostic or a quick fix
#: is an editor diagnostic outcome; the one event that records a false positive
#: has its own class because the corpus scores it differently.
_EVENT_CLASS = {
    "false_positive_disposition": "false_positive_disposition",
}
DEFAULT_EVENT_CLASS = "editor_diagnostic_outcome"

DEFAULT_CONSUMER_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "schemas/intelligence/consumers/lsp-telemetry.schema.json"
)


class LspTelemetryError(ContractError):
    """The document does not satisfy Intelligence's consumer view."""


def event_class(document: Mapping[str, Any]) -> str:
    """Return the corpus class for one telemetry event."""
    declared = document.get("event_type")
    if isinstance(declared, str) and declared in _EVENT_CLASS:
        return _EVENT_CLASS[declared]
    return DEFAULT_EVENT_CLASS


class LspTelemetryAdapter:
    """Validate an LSP telemetry event and project it onto the envelope.

    Validation is against Intelligence's own compatibility subset, not against a
    copy of the producer's authoritative schema. Intelligence requires only the
    fields it reads or carries; anything the LSP adds additively passes through
    untouched.
    """

    def __init__(
        self,
        *,
        consumer_schema: Path = DEFAULT_CONSUMER_SCHEMA,
    ) -> None:
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
            raise LspTelemetryError(message)

    def project(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Return the `l9.corpus-event/v1` envelope for one telemetry event."""
        self.validate(document)
        native = dict(document)
        limitations = [str(item) for item in native.get("limitations", [])]
        # The pack snapshot the diagnostic was produced against, when the
        # producer knows it; otherwise the editor session is the only stable
        # grouping the event carries.
        snapshot = native.get("corpus_snapshot") or native["session_id"]
        return {
            "schema_version": "l9.corpus-event/v1",
            "producer_id": PRODUCER_ID,
            "producer_contract": PRODUCER_CONTRACT,
            "sdk_contract": SDK_CONTRACT,
            "event_id": str(native["event_id"]),
            "event_class": event_class(native),
            "event_time": str(native["occurred_at"]),
            "snapshot_or_run_id": str(snapshot),
            # The producer validates its own privacy boundary before spooling
            # and emits only pseudonyms, rule identifiers and bucketed
            # magnitudes. Intelligence still runs its own redaction inspection
            # during ingestion; this records who redacted, not that the
            # inspection was skipped.
            "redaction_status": "producer_redacted",
            "limitations": limitations,
            "unknowns": [],
            "lineage": {
                "producer_event_hash": sha256_document(native),
                "parent_event_ids": [],
            },
            "payload": native,
        }
