"""`checksums.json` has a shape, and until now only the code knew it.

The assembler has always emitted

    {"schema_version": "l9.defense-checksums/v1", "files": {path: sha256}}

but no schema described it and no contract declared it. `l9-ci-debt-lsp`
consequently read the member with a loader written for a *different* document
-- the bare `checksums` mapping inside `defense-pack.json` -- and refused every
real pack at verification step 12 with

    ArchiveIntegrityError: checksum value must be a string: files

because `files` is where that loader expected a digest. An unpublished shape
cannot be conformed to; these tests publish it.

The pack here is built through the real pipeline rather than hand-written, so
the document under test is the one the assembler actually produces.
"""

from __future__ import annotations

import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any

import jsonschema

from l9_debt_intelligence.analytics.builder import build_analytics
from l9_debt_intelligence.compilation.builder import build_compilation
from l9_debt_intelligence.historical.bootstrap import repository_root
from l9_debt_intelligence.ingestion.historical_resolution import (
    HistoricalResolutionAdapter,
)
from l9_debt_intelligence.ingestion.learning import HISTORICAL_CONTRACT
from l9_debt_intelligence.ingestion.service import IngestionService
from l9_debt_intelligence.publication.assembler import assemble_pack
from l9_debt_intelligence.snapshots.builder import build_snapshot

ROOT = repository_root()
SCHEMA_PATH = ROOT / "schemas/intelligence/defense-checksums.schema.json"
RULE = "ruff::E501"


def _historical_event(index: int, scope_count: int) -> dict[str, Any]:
    scope = "repository_" + f"{index % scope_count:064x}"
    return {
        "schema_version": HISTORICAL_CONTRACT,
        "event_id": f"historical.ep{index}.verification",
        "episode_id": f"ep{index}",
        "observation_kind": "verification_outcome",
        "occurred_at": "2026-09-05T00:00:00Z",
        "repository_identity": scope,
        "snapshot_or_run_id": f"github-run:{1000 + index}",
        "parent_event_ids": [],
        "failure": {
            "semantic_failure_identity": RULE,
            "identity_authority": "canonical",
        },
        "intervention": None,
        "validation": {"outcome": "clean_verified", "equivalent_validation": True},
        "historical_evidence": {"grade": "B", "suspected_flake": False},
        "source": {"provider": "github", "workflow_run_ref": str(1000 + index)},
        "limitations": [],
        "unknowns": [],
        "provenance": {"reconstruction_algorithm": "v1"},
    }


def _build_pack(workspace: Path) -> Path:
    """Run the real chain far enough to get an archive, and return its path."""
    service = IngestionService(
        event_schema=ROOT / "schemas/intelligence/corpus-event.schema.json",
        compatibility_registry=ROOT / ".l9/producer-compatibility.json",
        storage_root=workspace / "store",
    )
    consumers = ROOT / "schemas/intelligence/consumers"
    adapter = HistoricalResolutionAdapter(
        consumer_schema=consumers / "historical-resolution-event.schema.json"
    )
    # Ten repairs across five repositories is what carries the single rule past
    # the promotion threshold; the assembler refuses a pack with no
    # promotion-eligible rule, so a smaller corpus produces no archive to test.
    for index in range(10):
        service.ingest(adapter.project(_historical_event(index, 5)))

    snapshot = build_snapshot(
        storage_root=workspace / "store",
        snapshots_root=workspace / "snapshots",
    )
    analysis = build_analytics(
        snapshot_path=Path(snapshot.snapshot_path),
        analytics_root=workspace / "analysis",
    )
    compilation = build_compilation(
        analysis_path=Path(analysis["analysis_path"]),
        compilation_root=workspace / "compilation",
    )
    build = assemble_pack(
        compilation_path=Path(compilation["compilation_path"]),
        output_root=workspace / "packs",
        version="0.1.0",
        taxonomy_version="1.0.0",
        sdk_contract_version="l9.integration-contract/v1",
        compatibility_path=ROOT / ".l9/default-compatibility.json",
    )
    return Path(build["archive_path"])


def _checksums_member(archive_path: Path) -> dict[str, Any]:
    with tarfile.open(archive_path, "r:gz") as archive:
        member = archive.extractfile("checksums.json")
        assert member is not None
        document = json.loads(member.read())
    assert isinstance(document, dict)
    return document


class ChecksumsDocumentTests(unittest.TestCase):
    """The assembler's real output against the newly published schema."""

    archive: Path
    workspace: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        # Pseudonymisation is fail-closed; the values are irrelevant to this
        # document, only their presence is.
        os.environ.setdefault("L9_INTELLIGENCE_PSEUDONYM_KEY", "test-pseudonym-key")
        os.environ.setdefault("L9_INTELLIGENCE_PATH_KEY", "test-path-key")
        cls.workspace = tempfile.TemporaryDirectory()
        cls.archive = _build_pack(Path(cls.workspace.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.workspace.cleanup()

    def test_the_emitted_member_validates_against_the_published_schema(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(_checksums_member(self.archive), schema)

    def test_it_carries_the_envelope_rather_than_a_bare_mapping(self) -> None:
        """The distinction the consumer got wrong, pinned.

        A bare `{path: digest}` mapping is indistinguishable from a future
        format; the envelope is what makes the document self-describing.
        """
        document = _checksums_member(self.archive)
        self.assertEqual(document["schema_version"], "l9.defense-checksums/v1")
        self.assertIsInstance(document["files"], dict)
        self.assertNotIn("checksums", document)

    def test_every_member_it_names_is_a_real_sha256(self) -> None:
        files = _checksums_member(self.archive)["files"]
        self.assertGreater(len(files), 0, "an empty document verifies nothing")
        for name, digest in files.items():
            with self.subTest(member=name):
                self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_it_covers_the_archive_members_that_carry_content(self) -> None:
        """`checksums.json` cannot checksum itself; everything else it must."""
        files = set(_checksums_member(self.archive)["files"])
        with tarfile.open(self.archive, "r:gz") as archive:
            members = {
                name for name in archive.getnames() if archive.getmember(name).isfile()
            }
        self.assertEqual(members - files, {"checksums.json"})


class SchemaRefusesMalformedDocuments(unittest.TestCase):
    """Strict negative coverage, so the schema is a gate and not a comment."""

    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def _refuses(self, document: object) -> None:
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(document, self.schema)

    def test_a_bare_path_to_digest_mapping_is_refused(self) -> None:
        """The shape the stale consumer accepted. It is not this document."""
        self._refuses({"defense-pack.json": "a" * 64})

    def test_the_packs_inline_checksums_field_is_refused(self) -> None:
        """`defense-pack.json` carries this shape; `checksums.json` does not."""
        self._refuses({"checksums": {"defense-pack.json": "a" * 64}})

    def test_a_wrong_schema_version_is_refused(self) -> None:
        self._refuses({"schema_version": "l9.defense-checksums/v2", "files": {}})

    def test_a_missing_schema_version_is_refused(self) -> None:
        self._refuses({"files": {"defense-pack.json": "a" * 64}})

    def test_a_non_object_files_value_is_refused(self) -> None:
        self._refuses({"schema_version": "l9.defense-checksums/v1", "files": []})

    def test_a_non_hex_digest_is_refused(self) -> None:
        self._refuses(
            {
                "schema_version": "l9.defense-checksums/v1",
                "files": {"defense-pack.json": "not a digest"},
            }
        )

    def test_a_short_digest_is_refused(self) -> None:
        self._refuses(
            {
                "schema_version": "l9.defense-checksums/v1",
                "files": {"defense-pack.json": "a" * 63},
            }
        )

    def test_an_uppercase_digest_is_refused(self) -> None:
        """Canonical output is lowercase; accepting both makes two identities."""
        self._refuses(
            {
                "schema_version": "l9.defense-checksums/v1",
                "files": {"defense-pack.json": "A" * 64},
            }
        )

    def test_a_traversing_member_path_is_refused(self) -> None:
        for name in ("../escape.json", "rules/../../escape.json", "/absolute.json"):
            with self.subTest(path=name):
                self._refuses(
                    {
                        "schema_version": "l9.defense-checksums/v1",
                        "files": {name: "a" * 64},
                    }
                )

    def test_an_unknown_top_level_field_is_refused(self) -> None:
        self._refuses(
            {
                "schema_version": "l9.defense-checksums/v1",
                "files": {},
                "extra": True,
            }
        )


if __name__ == "__main__":
    unittest.main()
