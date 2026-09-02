"""Project a native Resolver feedback event onto the corpus envelope.

`Quantum-L9/l9-ci-debt-resolver` already emits a complete, privacy-validated
feedback contract — `l9.intelligence-feedback-event/v1` — with deterministic
identity, an idempotency key, a durable outbox and both file and HTTPS
transports. Intelligence already owns `l9.corpus-event/v1` and everything
downstream of it. The only thing missing between them was a projection.

This adapter is that projection, and it lives here because the corpus envelope
is Intelligence's to own: asking the Resolver to emit `l9.corpus-event/v1`
would duplicate schema authority rather than close a wire.

The producer's document is carried into `payload` whole. It is never flattened,
re-keyed or summarised, so failure fingerprint and category, resolution
terminal state, validation outcome, finding and contract identifiers,
capability profile, hashed provenance and the idempotency key all survive
intact for downstream learning. `lineage.producer_event_hash` binds the
projection to the canonical producer document, independent of JSON key order
or insignificant whitespace.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.contracts.errors import ContractError

PRODUCER_ID = "Quantum-L9/l9-ci-debt-resolver"
PRODUCER_CONTRACT = "l9.intelligence-feedback-event/v1"
SDK_CONTRACT = "l9.integration-contract/v1"
EVENT_CLASS = "verification_outcome"

DEFAULT_CONSUMER_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "schemas/intelligence/consumers/resolver-feedback.schema.json"
)


class ResolverFeedbackError(ContractError):
    """The document does not satisfy Intelligence's consumer view."""


class ResolverFeedbackAdapter:
    """Validate a Resolver feedback document and project it onto the envelope.

    Validation is against Intelligence's own compatibility subset, not against
    a copy of the producer's authoritative schema. Intelligence requires only
    the fields it reads or carries; anything the Resolver adds additively
    passes through untouched.
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
            raise ResolverFeedbackError(message)

    def project(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Return the `l9.corpus-event/v1` envelope for one feedback event."""
        self.validate(document)
        native = dict(document)
        limitations = [str(item) for item in native.get("limitations", [])]
        return {
            "schema_version": "l9.corpus-event/v1",
            "producer_id": PRODUCER_ID,
            "producer_contract": PRODUCER_CONTRACT,
            "sdk_contract": SDK_CONTRACT,
            "event_id": str(native["event_id"]),
            "event_class": EVENT_CLASS,
            "event_time": str(native["occurred_at"]),
            "snapshot_or_run_id": str(native["event_id"]),
            # The producer validates its own privacy boundary before delivery
            # and emits only pseudonyms, fingerprints and bucketed magnitudes.
            # Intelligence still runs its own redaction inspection over the
            # payload during ingestion; this records who redacted, not that the
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
