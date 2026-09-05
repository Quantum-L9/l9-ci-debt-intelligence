"""Redact an SDK finding bundle and project it onto the corpus envelope.

`Quantum-L9/l9-ci-sdk` emits `l9.finding-bundle/v1` -- a canonical, validated,
revision-bound static-analysis artifact. Intelligence's producer registry has
listed the SDK as an `active` producer of that contract, while ingestion accepts
only `l9.corpus-event/v1` and the sole projector was the Resolver's. Nothing in
the constellation emits a corpus envelope, so the SDK path was `active` in the
registry and unreachable in code.

This adapter is that projection. It lives here for the reason
`resolver_feedback` gives: the corpus envelope is Intelligence's to own, and
asking the SDK to emit `l9.corpus-event/v1` would duplicate schema authority
rather than close a wire.

Redaction
---------
It differs from `resolver_feedback` in one way that matters. The Resolver
validates its own privacy boundary before delivery and emits only pseudonyms,
fingerprints and bucketed magnitudes, so that adapter carries the producer's
document into `payload` whole and records `redaction_status:
producer_redacted`.

A finding bundle is not privacy-safe. It carries repository-relative source
paths (`l9_ci/artifacts/serializer.py`) and the exact revision SHA, and
Intelligence's own ingestion redaction check does not catch either: its
`ABSOLUTE_PATH` pattern matches `/home`, `/Users`, `C:\\` and the like, so a
bundle passes `assess_redaction` unchanged while carrying every filename in the
repository it scanned. Carrying it whole would have quietly lowered the corpus
privacy bar with no check firing.

So this adapter redacts before projecting, and records `intelligence_redacted`
-- a first-class value of the envelope's `redaction_status` enum, distinct from
`producer_redacted`, which is exactly the distinction between "the producer
guaranteed this" and "we did". What survives is the learning signal: canonical
and provider rule identity, severity, category, confidence, fingerprints,
counts, coverage and provider versions. What does not survive is anything that
names the repository, its files, or its revision.

Tokens are keyed and stable, so "the same file keeps failing" is still
answerable across records while the filename is not recoverable from the
corpus.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.contracts.errors import ContractError

from .identity import path_token, repository_pseudonym

PRODUCER_ID = "Quantum-L9/l9-ci-sdk"
PRODUCER_CONTRACT = "l9.finding-bundle/v1"
SDK_CONTRACT = "l9.integration-contract/v1"
EVENT_CLASS = "static_finding"
REDACTION_STATUS = "intelligence_redacted"

DEFAULT_CONSUMER_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "schemas/intelligence/consumers/sdk-finding-bundle.schema.json"
)


class SdkFindingBundleError(ContractError):
    """The document does not satisfy Intelligence's consumer view."""


class SdkFindingBundleAdapter:
    """Validate an SDK finding bundle, redact it, and project the envelope.

    Validation is against Intelligence's own compatibility subset, not against a
    copy of the producer's authoritative schema. Intelligence requires only the
    fields it reads, redacts or carries; anything the SDK adds additively passes
    through untouched -- and is therefore also *not* redacted, which is why the
    consumer schema pins the shape of every location the adapter must rewrite.
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
            raise SdkFindingBundleError(message)

    def redact(
        self,
        document: Mapping[str, Any],
        *,
        path_key: bytes,
    ) -> dict[str, Any]:
        """Return a copy of the bundle with every identifying value replaced."""
        redacted = deepcopy(dict(document))

        for collection in ("findings", "evidence"):
            for item in redacted.get(collection, []):
                if not isinstance(item, dict):
                    continue
                for location in item.get("locations", []):
                    if not isinstance(location, dict):
                        continue
                    original = location.get("normalized_path")
                    if isinstance(original, str):
                        location["normalized_path"] = path_token(
                            repository_path=original,
                            path_key=path_key,
                        )

        snapshot = redacted.get("snapshot")
        if isinstance(snapshot, dict):
            # The revision is replaced rather than dropped: downstream needs to
            # know whether two records describe the same tree, and must not be
            # able to check out that tree.
            revision = snapshot.get("revision")
            if isinstance(revision, str):
                snapshot["revision"] = sha256_document(revision)
            # repository_root is a local filesystem path in the producer's
            # environment. It carries no cross-record meaning at all, so it is
            # dropped rather than tokenised.
            snapshot.pop("repository_root", None)

        return redacted

    def project(
        self,
        document: Mapping[str, Any],
        *,
        repository: str,
        pseudonym_key: bytes,
        path_key: bytes,
    ) -> dict[str, Any]:
        """Return the `l9.corpus-event/v1` envelope for one finding bundle.

        `repository` is supplied by the caller because a finding bundle does not
        name the repository it scanned -- `snapshot.repository_root` is a local
        path, not an identity. Requiring it explicitly is what lets the record
        join to Resolver records for the same repository under a shared key.
        """
        self.validate(document)
        native = dict(document)
        redacted = self.redact(native, path_key=path_key)

        snapshot = native.get("snapshot", {})
        snapshot_id = str(snapshot.get("snapshot_id", ""))

        # Binds the projection to the canonical *producer* document, so a record
        # can be traced to the exact bundle it came from without the corpus
        # holding that bundle. Deliberately hashed over `native`, not over the
        # redacted copy: it is the producer's event hash, and hashing the
        # redaction would make it depend on this adapter's key material.
        producer_event_hash = sha256_document(native)

        return {
            "schema_version": "l9.corpus-event/v1",
            "producer_id": PRODUCER_ID,
            "producer_contract": PRODUCER_CONTRACT,
            "sdk_contract": SDK_CONTRACT,
            "event_id": f"finding-bundle_{producer_event_hash}",
            "event_class": EVENT_CLASS,
            "event_time": str(native["generated_at"]),
            "snapshot_or_run_id": snapshot_id,
            "redaction_status": REDACTION_STATUS,
            "limitations": [str(item) for item in native.get("limitations", [])],
            "unknowns": [],
            "lineage": {
                "producer_event_hash": producer_event_hash,
                "parent_event_ids": [],
            },
            "payload": {
                "repository_pseudonym": repository_pseudonym(
                    repository=repository,
                    pseudonym_key=pseudonym_key,
                ),
                "bundle": redacted,
            },
        }
