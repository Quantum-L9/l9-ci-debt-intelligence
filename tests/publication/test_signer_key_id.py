"""The publication manifest must name the key that signed it.

`l9.defense-publication/v1` was produced without `signer_key_id`. The consumer
contract for the same token -- `l9-ci-debt-lsp`'s
`.l9/pack-protocol-contract.yaml`, `status: authoritative` -- has always
required it: `public_key.source: trusted-key-registry`,
`embedded_key_behavior: must_match_trusted_key`, and `validate_trusted_signer`
in the verification order. Its installer resolves the trusted verification key
by that id.

So a manifest without it was never valid v1 as the consumer defines v1. It was
refused at install with `'signer_key_id' is a required property`, and the
trusted-signer step could not run at all. This is a producer-conformance fix,
not a new v1 field.

The derivation is consumer-defined. These tests pin it against the consumer's
own published definition rather than against a value copied from it, because a
copied constant would not notice the day the two drift.
"""

from __future__ import annotations

import base64
import json
import unittest

from l9_debt_intelligence.publication.crypto import public_key_id
from l9_debt_intelligence.publication.errors import SignatureVerificationError

# Reproduces `l9_debt_lsp.packs.trust.public_key_id` and
# `l9_debt_lsp.packs.hashing.namespaced_hash` from their published source. It is
# spelled out here rather than imported because the LSP is a separate
# distribution that this package must not depend on -- the point is that two
# independent implementations agree.
CONSUMER_PREFIX = "key_"


def consumer_public_key_id(public_key_base64: str) -> str:
    import hashlib

    raw = base64.b64decode(public_key_base64.encode("ascii"), validate=True)
    canonical = json.dumps(
        {"raw_public_key": raw.hex()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return CONSUMER_PREFIX + hashlib.sha256(canonical).hexdigest()


def _key(seed: int = 0) -> str:
    return base64.b64encode(bytes([seed] * 32)).decode("ascii")


class TestDerivationMatchesTheConsumer(unittest.TestCase):
    def test_the_two_implementations_agree(self) -> None:
        """The whole point of the field.

        If these ever diverge the consumer rejects a correctly signed pack, and
        the manifest gives no visible reason why.
        """
        for seed in (0, 1, 7, 255):
            with self.subTest(seed=seed):
                key = _key(seed)
                self.assertEqual(public_key_id(key), consumer_public_key_id(key))

    def test_it_matches_the_shape_the_consumer_schema_requires(self) -> None:
        import re

        value = public_key_id(_key(3))
        self.assertRegex(value, r"^key_[0-9a-f]{64}$")
        self.assertTrue(re.fullmatch(r"key_[0-9a-f]{64}", value))

    def test_distinct_keys_get_distinct_identities(self) -> None:
        self.assertNotEqual(public_key_id(_key(1)), public_key_id(_key(2)))

    def test_it_is_deterministic(self) -> None:
        self.assertEqual(public_key_id(_key(9)), public_key_id(_key(9)))


class TestItRefusesRatherThanGuessing(unittest.TestCase):
    """No fallback key guessing, per the contract."""

    def test_a_non_base64_key_is_refused(self) -> None:
        with self.assertRaises(SignatureVerificationError):
            public_key_id("not base64!!")

    def test_a_wrong_length_key_is_refused(self) -> None:
        """A 31-byte value is valid base64 and not an Ed25519 key."""
        with self.assertRaises(SignatureVerificationError):
            public_key_id(base64.b64encode(b"\x00" * 31).decode("ascii"))


class TestTheContractDeclaresIt(unittest.TestCase):
    def test_the_schema_requires_it_with_the_consumer_pattern(self) -> None:
        from pathlib import Path

        schema = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "schemas/intelligence/publication-manifest.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("signer_key_id", schema["required"])
        self.assertEqual(
            schema["properties"]["signer_key_id"]["pattern"],
            r"^key_[0-9a-f]{64}$",
        )

    def test_the_producer_schema_matches_the_consumer_required_set(self) -> None:
        """The divergence that caused this, pinned so it cannot silently return.

        Both schemas describe `l9.defense-publication/v1`. A field required by
        one and absent from the other is a manifest that validates on the
        producer and is refused by the consumer.
        """
        from pathlib import Path

        producer = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "schemas/intelligence/publication-manifest.schema.json"
            ).read_text(encoding="utf-8")
        )
        consumer_required = {
            "schema_version",
            "pack_id",
            "pack_version",
            "archive_name",
            "archive_sha256",
            "archive_size",
            "signature",
            "public_key",
            "signer_key_id",
            "signature_algorithm",
            "channel",
            "rollback",
            "publication_gates",
        }
        self.assertEqual(set(producer["required"]), consumer_required)


if __name__ == "__main__":
    unittest.main()
