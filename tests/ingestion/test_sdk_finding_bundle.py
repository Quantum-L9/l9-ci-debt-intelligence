"""The SDK finding-bundle seam: native producer artifact -> corpus record.

`Quantum-L9/l9-ci-sdk` emits `l9.finding-bundle/v1`. Intelligence owns
`l9.corpus-event/v1` and everything downstream of it. The producer registry has
listed the SDK as `active` for its contract, while ingestion accepted only the
corpus envelope and the sole projector was the Resolver's -- so the SDK path
was `active` in the registry and unreachable in code.
`SdkFindingBundleAdapter` is that projection.

`tests/fixtures/producers/native-sdk-finding-bundle.json` is not hand-written.
It is the bundle `l9-ci semgrep run`/`normalize` produced from a real Semgrep
1.176.1 scan of the l9-ci-sdk working tree (166 files analysed, 5 findings,
classified by the Core-provisioned policy), carried over unmodified. Its real
source paths are the reason this adapter redacts rather than carries whole.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.ingestion.redaction import assess_redaction
from l9_debt_intelligence.ingestion.sdk_finding_bundle import (
    EVENT_CLASS,
    PRODUCER_CONTRACT,
    PRODUCER_ID,
    REDACTION_STATUS,
    SdkFindingBundleAdapter,
    SdkFindingBundleError,
)

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "tests/fixtures/producers/native-sdk-finding-bundle.json"
CORPUS_SCHEMA = ROOT / "schemas/intelligence/corpus-event.schema.json"

REPOSITORY = "Acme-Corp/private-service"
PSEUDONYM_KEY = b"p" * 48
PATH_KEY = b"t" * 48


def _native() -> dict[str, Any]:
    return json.loads(NATIVE.read_text(encoding="utf-8"))


def _project(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "repository": REPOSITORY,
        "pseudonym_key": PSEUDONYM_KEY,
        "path_key": PATH_KEY,
    }
    kwargs.update(overrides)
    return SdkFindingBundleAdapter().project(_native(), **kwargs)


class SdkFindingBundleSeam(unittest.TestCase):
    def test_the_native_bundle_carries_source_paths(self) -> None:
        """The premise. If this ever stops holding, the adapter is unnecessary."""
        native = _native()
        paths = {
            location["normalized_path"]
            for finding in native["findings"]
            for location in finding["locations"]
        }
        self.assertIn("l9_ci/artifacts/serializer.py", paths)
        self.assertEqual(
            native["snapshot"]["revision"],
            "31003e1dffbb14eab98043ff5a9e1d43832b7a9d",
        )

    def test_intelligence_redaction_does_not_catch_the_native_bundle(self) -> None:
        """Why the adapter redacts instead of trusting the ingestion check.

        `assess_redaction` looks for sensitive keys, credential patterns and
        ABSOLUTE paths. A finding bundle carries repository-RELATIVE paths, so
        it passes the check while naming every file it scanned. Carrying it
        whole would have lowered the corpus privacy bar with nothing firing.
        """
        assessment = assess_redaction(
            {"redaction_status": "producer_redacted", "payload": _native()}
        )
        self.assertTrue(assessment.safe)

    def test_projection_replaces_every_source_path(self) -> None:
        envelope = _project()
        bundle = envelope["payload"]["bundle"]
        for collection in ("findings", "evidence"):
            for item in bundle[collection]:
                for location in item["locations"]:
                    self.assertRegex(
                        location["normalized_path"], r"^path_[0-9a-f]{64}$"
                    )

    def test_no_identifying_value_survives_anywhere_in_the_envelope(self) -> None:
        """Serialize the whole envelope and look for what must not be in it."""
        serialized = json.dumps(_project())
        for forbidden in (
            "l9_ci/artifacts/serializer.py",
            "tests/fixtures/semgrep",
            "31003e1dffbb14eab98043ff5a9e1d43832b7a9d",
            "Acme-Corp",
            "private-service",
            "repository_root",
        ):
            self.assertNotIn(
                forbidden, serialized, f"{forbidden!r} leaked into the envelope"
            )

    def test_the_learning_signal_survives_redaction(self) -> None:
        """Redaction that removed the signal would be a different bug."""
        bundle = _project()["payload"]["bundle"]
        rule_ids = {finding["canonical_rule_id"] for finding in bundle["findings"]}
        self.assertIn("L9-PYTHON-BROAD-EXCEPT", rule_ids)
        self.assertTrue(all(finding["severity"] for finding in bundle["findings"]))
        self.assertTrue(all(finding["fingerprint"] for finding in bundle["findings"]))
        self.assertEqual(bundle["providers"][0]["provider_version"], "1.176.1")
        self.assertEqual(bundle["coverage"][0]["files_analyzed"], 166)

    def test_envelope_declares_intelligence_redaction_not_producer_redaction(
        self,
    ) -> None:
        """The distinction is the whole point: we redacted this, the SDK did not."""
        self.assertEqual(_project()["redaction_status"], REDACTION_STATUS)
        self.assertEqual(REDACTION_STATUS, "intelligence_redacted")

    def test_envelope_validates_against_the_corpus_contract(self) -> None:
        schema = json.loads(CORPUS_SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(_project()), key=lambda e: list(e.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_envelope_identity_matches_the_producer_registry(self) -> None:
        envelope = _project()
        self.assertEqual(envelope["producer_id"], PRODUCER_ID)
        self.assertEqual(envelope["producer_contract"], PRODUCER_CONTRACT)
        self.assertEqual(envelope["event_class"], EVENT_CLASS)
        registry = json.loads(
            (ROOT / ".l9/producer-compatibility.json").read_text("utf-8")
        )
        entry = registry["producers"][PRODUCER_ID]
        self.assertEqual(entry["status"], "active")
        self.assertIn(PRODUCER_CONTRACT, entry["contract_versions"])
        self.assertIn(EVENT_CLASS, entry["event_classes"])

    def test_lineage_binds_the_producer_document_not_the_redaction(self) -> None:
        """The hash must identify the bundle the SDK emitted.

        Hashing the redacted copy instead would make provenance depend on this
        adapter's key material, so the same producer artifact would trace to
        different hashes after a key rotation.
        """
        envelope = _project()
        self.assertEqual(
            envelope["lineage"]["producer_event_hash"], sha256_document(_native())
        )
        rotated = _project(path_key=b"z" * 48, pseudonym_key=b"y" * 48)
        self.assertEqual(
            rotated["lineage"]["producer_event_hash"],
            envelope["lineage"]["producer_event_hash"],
        )

    def test_tokens_are_stable_under_one_key_and_differ_under_another(self) -> None:
        """Stability is what makes 'the same file keeps failing' answerable."""
        first = _project()["payload"]
        again = _project()["payload"]
        self.assertEqual(first, again)
        other = _project(path_key=b"z" * 48, pseudonym_key=b"y" * 48)["payload"]
        self.assertNotEqual(
            other["repository_pseudonym"], first["repository_pseudonym"]
        )

    def test_pseudonym_matches_the_resolver_construction(self) -> None:
        """Same repository, same identity, whichever producer the record came from."""
        import hashlib
        import hmac

        expected = hmac.new(
            PSEUDONYM_KEY, REPOSITORY.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        self.assertEqual(
            _project()["payload"]["repository_pseudonym"], f"repository_{expected}"
        )

    def test_a_short_key_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 32 bytes"):
            _project(path_key=b"short")

    def test_a_bundle_without_an_exact_revision_is_refused(self) -> None:
        native = _native()
        del native["snapshot"]["revision"]
        with self.assertRaises(SdkFindingBundleError):
            SdkFindingBundleAdapter().project(
                native,
                repository=REPOSITORY,
                pseudonym_key=PSEUDONYM_KEY,
                path_key=PATH_KEY,
            )

    def test_a_foreign_contract_is_refused(self) -> None:
        native = _native()
        native["schema"] = "l9.some-other-contract/v1"
        with self.assertRaises(SdkFindingBundleError):
            SdkFindingBundleAdapter().project(
                native,
                repository=REPOSITORY,
                pseudonym_key=PSEUDONYM_KEY,
                path_key=PATH_KEY,
            )


if __name__ == "__main__":
    unittest.main()
