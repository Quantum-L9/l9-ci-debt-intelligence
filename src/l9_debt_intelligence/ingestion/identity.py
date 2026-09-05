from __future__ import annotations

import hashlib
import hmac
from typing import Any

from l9_debt_intelligence.contracts.canonical import canonical_json


def namespaced_hash(prefix: str, document: Any) -> str:
    digest = hashlib.sha256(canonical_json(document)).hexdigest()
    return f"{prefix}{digest}"


def record_id(
    *,
    producer_id: str,
    producer_contract: str,
    event_class: str,
    snapshot_or_run_id: str,
    payload_hash: str,
) -> str:
    return namespaced_hash(
        "cr_",
        {
            "event_class": event_class,
            "payload_hash": payload_hash,
            "producer_contract": producer_contract,
            "producer_id": producer_id,
            "snapshot_or_run_id": snapshot_or_run_id,
        },
    )


def quarantine_id(event_hash: str, reason: str) -> str:
    return namespaced_hash(
        "qr_",
        {
            "event_hash": event_hash,
            "reason": reason,
        },
    )


def observation_id(
    *,
    event_hash: str,
    observed_at: str,
    sequence: int,
) -> str:
    return namespaced_hash(
        "obs_",
        {
            "event_hash": event_hash,
            "observed_at": observed_at,
            "sequence": sequence,
        },
    )


def _keyed_digest(key: bytes, value: str, *, purpose: str) -> str:
    """HMAC-SHA256 a single value under a caller-supplied key.

    Keyed rather than plain: a bare `sha256(path)` over a source tree is
    trivially reversible by hashing a candidate wordlist, so an unkeyed
    "pseudonym" would be a pseudonym in name only.

    The key must be stable for the life of the corpus. Rotating it
    re-pseudonymises every subsequent record, so longitudinal joins on
    repository identity silently split at the rotation boundary rather than
    failing loudly -- rotate only with a corpus migration.
    """
    if len(key) < 32:
        raise ValueError(f"{purpose} key must be at least 32 bytes")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def repository_pseudonym(*, repository: str, pseudonym_key: bytes) -> str:
    """Stable pseudonym for one repository.

    Same construction and `repository_` prefix the Resolver uses for its own
    feedback events, so a repository carries one identity across the corpus
    whichever producer a record arrived from. Supplying the same key to both
    producers is what makes that true; supplying different keys silently
    partitions the corpus by producer.

    Deliberately restated rather than imported: the seam between Intelligence
    and a producer is a contract, not a dependency, and
    `BoundaryTests.test_intelligence_never_imports_the_producer_implementation`
    enforces that by substring, so naming the producer's module path here --
    even in a comment -- is itself the violation.
    """
    return f"repository_{_keyed_digest(pseudonym_key, repository, purpose='pseudonym')}"


def path_token(*, repository_path: str, path_key: bytes) -> str:
    """Stable token for one repository-relative source path.

    Mirrors the Resolver's own path tokens, down to the `path_` prefix. Tokens
    are comparable across records, so "the same file keeps failing" survives
    redaction while the filename does not.
    """
    return f"path_{_keyed_digest(path_key, repository_path, purpose='path-token')}"
