"""CLI-level tests: every subcommand reached through ``main`` with real argv.

There was no such module, which is why `generate-publication-key` could write
a keypair and then die on `arguments.output` -- a defect reachable only through
the CLI, since the Python API it calls is correct. `tests/publication/` covers
`generate_keypair` directly and passed throughout.

The shared tail of `main` reads `arguments.output` for every command, so every
subparser must declare it. `test_every_subcommand_declares_output` asserts that
structurally rather than one command at a time, so a new subcommand cannot
reintroduce the same crash.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from l9_debt_intelligence.cli import build_parser, main


class PublicationKeyCli(unittest.TestCase):
    def test_generate_publication_key_succeeds_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "pack.key"
            public = root / "pack.pub"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "generate-publication-key",
                        "--private-key",
                        str(private),
                        "--public-key",
                        str(public),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertTrue(private.is_file())
            self.assertTrue(public.is_file())
            document = json.loads(stdout.getvalue())
            self.assertEqual(document["status"], "created")
            self.assertEqual(document["private_key"], private.as_posix())
            self.assertEqual(document["public_key"], public.as_posix())

    def test_generate_publication_key_honours_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "nested" / "result.json"
            exit_code = main(
                [
                    "generate-publication-key",
                    "--private-key",
                    str(root / "pack.key"),
                    "--public-key",
                    str(root / "pack.pub"),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(exit_code, 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["schema_version"], "l9.publication-key-result/v1")

    def test_private_key_is_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "pack.key"
            with redirect_stdout(io.StringIO()):
                main(
                    [
                        "generate-publication-key",
                        "--private-key",
                        str(private),
                        "--public-key",
                        str(root / "pack.pub"),
                    ]
                )
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)

    def test_a_failed_keygen_leaves_no_private_key_behind(self) -> None:
        """Signing material must not accumulate on a failure path.

        The caller sees a non-zero exit and has no reason to go looking for the
        file, so a half-finished keygen that left a private key on disk would
        leave it there unnoticed.
        """
        from l9_debt_intelligence.publication.crypto import generate_keypair

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "pack.key"
            # A directory in the private key's place makes write_bytes raise
            # after the public half has already been written.
            private.mkdir()
            public = root / "pack.pub"
            with self.assertRaises(OSError):
                generate_keypair(
                    private_key_path=private,
                    public_key_path=public,
                )
            self.assertFalse(public.exists())


class ParserContract(unittest.TestCase):
    # Commands that return from `main` before the shared tail and so never read
    # `arguments.output`. `serve-feedback-ingress` blocks in `serve_forever`
    # and has no result document to emit. Anything added here is a deliberate
    # exemption, not an oversight.
    NO_RESULT_DOCUMENT = frozenset({"serve-feedback-ingress"})

    def test_every_subcommand_declares_output(self) -> None:
        """`main` reads `arguments.output` for every command it dispatches.

        Asserted structurally rather than one command at a time, because the
        omission that broke `generate-publication-key` is invisible until that
        specific command is run through the CLI.
        """
        parser = build_parser()
        subparsers = [
            action
            for action in parser._actions  # noqa: SLF001 - argparse has no public API
            if hasattr(action, "choices") and isinstance(action.choices, dict)
        ]
        self.assertTrue(subparsers, "no subcommand group found")
        missing: list[str] = []
        for group in subparsers:
            for name, subparser in group.choices.items():
                if name in self.NO_RESULT_DOCUMENT:
                    continue
                options = {
                    option
                    for action in subparser._actions  # noqa: SLF001
                    for option in action.option_strings
                }
                if "--output" not in options:
                    missing.append(name)
        self.assertEqual(missing, [], f"subcommands without --output: {missing}")

    def test_the_exemption_list_names_only_real_subcommands(self) -> None:
        """A stale exemption would silently re-open the hole it documents."""
        parser = build_parser()
        names: set[str] = set()
        for action in parser._actions:  # noqa: SLF001
            if hasattr(action, "choices") and isinstance(action.choices, dict):
                names.update(action.choices)
        self.assertTrue(self.NO_RESULT_DOCUMENT <= names, self.NO_RESULT_DOCUMENT)


if __name__ == "__main__":
    unittest.main()
