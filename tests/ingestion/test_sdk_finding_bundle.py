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
        # And repeats the snapshot id on every record, which is why redacting
        # `snapshot.snapshot_id` alone would leave it in clear 18 times over.
        self.assertTrue(
            all(finding["snapshot_id"] for finding in native["findings"]),
        )
        self.assertTrue(
            all(item["snapshot_id"] for item in native["evidence"]),
        )

    def test_intelligence_redaction_still_misses_relative_source_paths(self) -> None:
        """Why the adapter redacts instead of trusting the ingestion check.

        `assess_redaction` looks for sensitive keys, credential patterns,
        ABSOLUTE paths and -- since L3-F7 -- bare git object ids. A finding
        bundle carries repository-RELATIVE paths, which none of those match, so
        the filenames still pass the check unexamined. That is the standing
        reason this adapter redacts rather than carrying the bundle whole.

        The git-object-id rule does now fire on this fixture, via
        `snapshot.revision`. So the check is no longer blind to everything --
        it is blind to the paths, which is the narrower and still-true claim.
        """
        assessment = assess_redaction(
            {"redaction_status": "producer_redacted", "payload": _native()}
        )
        self.assertFalse(assessment.safe)
        self.assertTrue(
            any(item.startswith("git-object-id:") for item in assessment.limitations),
            assessment.limitations,
        )
        # The paths are what still gets through: no finding names one.
        self.assertFalse(
            any("serializer" in item for item in assessment.limitations),
            assessment.limitations,
        )

    def test_a_core_wired_snapshot_id_is_a_commit_sha_and_is_redacted(self) -> None:
        """L3-F7 regression: the snapshot id must not carry the revision.

        `l9-ci-core/.github/workflows/analyze-semgrep.yml` invokes the SDK with
        `snapshot-id: ${{ github.sha }}`, so in the constellation's own
        production wiring the snapshot id *is* the commit SHA -- and it is
        repeated on every finding and every evidence record.

        The committed native fixture cannot show this: it came from a run whose
        snapshot id was SDK-derived (`snapshot_<sha256>`), so the raw revision
        appeared only under `snapshot.revision`, which was already hashed. That
        is why the leak survived a suite that otherwise checks the envelope for
        identifying values. This test models Core's actual invocation instead.
        """
        native = _native()
        revision = native["snapshot"]["revision"]
        native["snapshot"]["snapshot_id"] = revision
        for collection in ("findings", "evidence"):
            for item in native[collection]:
                item["snapshot_id"] = revision

        envelope = SdkFindingBundleAdapter().project(
            native,
            repository=REPOSITORY,
            pseudonym_key=PSEUDONYM_KEY,
            path_key=PATH_KEY,
        )
        serialized = json.dumps(envelope)
        self.assertNotIn(revision, serialized)
        # Including the envelope's own correlation key, which leaves the
        # adapter and is what a subscriber to the HTTP ingress would see.
        self.assertNotEqual(envelope["snapshot_or_run_id"], revision)
        self.assertEqual(envelope["snapshot_or_run_id"], sha256_document(revision))

        bundle = envelope["payload"]["bundle"]
        self.assertEqual(bundle["snapshot"]["snapshot_id"], sha256_document(revision))
        for collection in ("findings", "evidence"):
            for item in bundle[collection]:
                self.assertEqual(item["snapshot_id"], sha256_document(revision))

    def test_the_redacted_envelope_passes_the_ingestion_check(self) -> None:
        """The new git-object-id rule must not fire on our own redaction.

        Every digest this adapter writes is sha256 (64 hex) and every token
        carries a `repository_`/`path_` prefix, so a rule bounded to a bare
        40-character object id cannot match them. If it could, every SDK event
        would self-quarantine.
        """
        assessment = assess_redaction(_project())
        self.assertTrue(assessment.safe, assessment.limitations)

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


class KeyMaterial(unittest.TestCase):
    """One key doing both jobs is an operator mistake with an invisible failure."""

    def test_the_two_keys_must_differ(self) -> None:
        same = b"s" * 48
        with self.assertRaisesRegex(ValueError, "must differ"):
            SdkFindingBundleAdapter().project(
                _native(),
                repository=REPOSITORY,
                pseudonym_key=same,
                path_key=same,
            )

    def test_one_key_would_collide_a_path_token_with_a_pseudonym(self) -> None:
        """The concrete reason the guard exists, asserted rather than described.

        The digest is over the bare value with no domain-separating prefix, so
        it is the key difference that separates the two namespaces. Strip that
        and the same input yields the same digest under both helpers.
        """
        from l9_debt_intelligence.ingestion.identity import (
            path_token,
            repository_pseudonym,
        )

        collided = "acme/widgets"
        one_key = b"s" * 48
        pseudonym = repository_pseudonym(repository=collided, pseudonym_key=one_key)
        token = path_token(repository_path=collided, path_key=one_key)
        self.assertEqual(
            pseudonym.removeprefix("repository_"), token.removeprefix("path_")
        )

    def test_distinct_keys_do_not_collide(self) -> None:
        from l9_debt_intelligence.ingestion.identity import (
            path_token,
            repository_pseudonym,
        )

        collided = "acme/widgets"
        pseudonym = repository_pseudonym(
            repository=collided, pseudonym_key=PSEUDONYM_KEY
        )
        token = path_token(repository_path=collided, path_key=PATH_KEY)
        self.assertNotEqual(
            pseudonym.removeprefix("repository_"), token.removeprefix("path_")
        )
