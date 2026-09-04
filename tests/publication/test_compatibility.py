"""Coverage for the publication compatibility gate.

This module exists because its absence was load-bearing. ``tests/publication/``
previously held only ``test_archive``, ``test_channels`` and ``test_crypto`` --
nothing imported ``publication.compatibility`` or ``publication.assembler``. So
``VERSION`` sat with a raw-string ``\\\\.`` separator, which compiles to a regex
demanding a LITERAL BACKSLASH between version components, and ``parse_version``
rejected every ordinary semantic version. ``assemble_pack`` could not run at
all, and neither could ``load_compatibility``, which parses the shipped
``.l9/default-compatibility.json``. The only workflow that exercises the path,
``publish-defense-pack.yml``, is ``workflow_dispatch``-only, so CI never ran it.

The first test below is the one that would have caught it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from l9_debt_intelligence.publication.compatibility import (
    load_compatibility,
    parse_version,
)
from l9_debt_intelligence.publication.errors import PublicationGateError

REPO = Path(__file__).resolve().parents[2]


class ParseVersionTests(unittest.TestCase):
    def test_ordinary_semantic_versions_parse(self) -> None:
        self.assertEqual(parse_version("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_version("0.1.0"), (0, 1, 0))
        self.assertEqual(parse_version("2.3.4"), (2, 3, 4))
        self.assertEqual(parse_version("10.20.30"), (10, 20, 30))

    def test_prerelease_suffix_is_accepted_and_ignored_for_ordering(self) -> None:
        self.assertEqual(parse_version("1.0.0-rc1"), (1, 0, 0))
        self.assertEqual(parse_version("2.1.0-alpha.3"), (2, 1, 0))

    def test_literal_backslash_form_is_rejected(self) -> None:
        """The only form the broken pattern used to accept."""
        with self.assertRaises(PublicationGateError):
            parse_version(r"1\.0\.0")

    def test_malformed_versions_are_rejected(self) -> None:
        for value in ("", "1.0", "1.0.0.0", "v1.0.0", "01.0.0", "1.0.x", "1..0"):
            with self.subTest(value=value):
                with self.assertRaises(PublicationGateError):
                    parse_version(value)

    def test_error_names_the_offending_value(self) -> None:
        with self.assertRaises(PublicationGateError) as caught:
            parse_version("nope")
        self.assertIn("nope", str(caught.exception))


class LoadCompatibilityTests(unittest.TestCase):
    def test_shipped_default_matrix_loads(self) -> None:
        """The matrix this repository ships must satisfy its own gate.

        ``load_compatibility`` runs ``parse_version`` over the matrix's own
        ``minimum_version`` and ``maximum_version_exclusive``, so a broken parser
        made the repository's own committed default unloadable.
        """
        matrix = load_compatibility(REPO / ".l9" / "default-compatibility.json")

        self.assertEqual(matrix["schema_version"], "l9.defense-compatibility/v1")
        self.assertEqual(matrix["sdk"]["contract"], "l9.integration-contract/v1")

    def test_shipped_matrix_admits_the_current_sdk(self) -> None:
        """The pack's SDK range must actually contain the SDK in the fleet.

        The matrix previously declared ``maximum_version_exclusive`` of ``2.0.0``
        while ``l9-ci-sdk`` is at ``2.0.0``, so the current SDK fell outside the
        range of every pack this repository could publish. That is a silent
        no-op, not an error, which is why it needs a test rather than a gate.
        """
        matrix = load_compatibility(REPO / ".l9" / "default-compatibility.json")
        sdk_version = (2, 0, 0)

        minimum = parse_version(str(matrix["sdk"]["minimum_version"]))
        maximum = parse_version(str(matrix["sdk"]["maximum_version_exclusive"]))

        self.assertLessEqual(minimum, sdk_version)
        self.assertLess(sdk_version, maximum)

    def test_inverted_range_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "l9.defense-compatibility/v1",
                        "sdk": {
                            "contract": "l9.integration-contract/v1",
                            "minimum_version": "3.0.0",
                            "maximum_version_exclusive": "2.0.0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(PublicationGateError):
                load_compatibility(path)

    def test_unsupported_matrix_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            path.write_text(
                json.dumps(
                    {"schema_version": "l9.defense-compatibility/v99", "sdk": {}}
                ),
                encoding="utf-8",
            )
            with self.assertRaises(PublicationGateError):
                load_compatibility(path)

    def test_matrix_without_sdk_section_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            path.write_text(
                json.dumps({"schema_version": "l9.defense-compatibility/v1"}),
                encoding="utf-8",
            )
            with self.assertRaises(PublicationGateError):
                load_compatibility(path)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
