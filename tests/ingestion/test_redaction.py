from __future__ import annotations

import unittest

from l9_debt_intelligence.ingestion.redaction import (
    assess_redaction,
)


class RedactionTests(unittest.TestCase):
    def test_sensitive_key_is_detected(self) -> None:
        result = assess_redaction(
            {
                "redaction_status": "producer_redacted",
                "payload": {
                    "api_token": "value",
                },
            }
        )
        self.assertFalse(result.safe)
        self.assertEqual("sensitive_content", result.reason)

    def test_absolute_path_is_detected(self) -> None:
        result = assess_redaction(
            {
                "redaction_status": "producer_redacted",
                "payload": {
                    "message": "failed in /home/user/project/main.py",
                },
            }
        )
        self.assertFalse(result.safe)

    def test_safe_reference_is_allowed(self) -> None:
        result = assess_redaction(
            {
                "redaction_status": "producer_redacted",
                "payload": {
                    "artifact_reference": "artifact://run-100",
                },
            }
        )
        self.assertTrue(result.safe)

    def test_bare_git_object_id_is_detected(self) -> None:
        """A commit SHA beside a pseudonym is not pseudonymous."""
        result = assess_redaction(
            {
                "redaction_status": "producer_redacted",
                "payload": {
                    "repository_pseudonym": "repository_" + "a" * 64,
                    "revision": "edeef6dcc316ec79b2f672ec2c827083f4035656",
                },
            }
        )
        self.assertFalse(result.safe)
        self.assertEqual("sensitive_content", result.reason)
        self.assertIn("git-object-id:payload.revision", result.limitations)

    def test_a_git_object_id_outside_the_payload_is_detected(self) -> None:
        """L3-F7: only `payload` was inspected, so the envelope went unchecked.

        The raw snapshot id sat in `snapshot_or_run_id`, one level up from
        anything this function looked at.
        """
        result = assess_redaction(
            {
                "redaction_status": "producer_redacted",
                "snapshot_or_run_id": "edeef6dcc316ec79b2f672ec2c827083f4035656",
                "payload": {"repository_pseudonym": "repository_" + "a" * 64},
            }
        )
        self.assertFalse(result.safe)
        self.assertIn("git-object-id:snapshot_or_run_id", result.limitations)

    def test_a_sha256_digest_is_not_mistaken_for_an_object_id(self) -> None:
        """The rule must not fire on Intelligence's own redaction output.

        Every digest written by the redacting adapters is sha256 (64 hex). A
        rule that matched those would quarantine every correctly redacted
        event, which is worse than the leak it was added to catch.
        """
        result = assess_redaction(
            {
                "redaction_status": "intelligence_redacted",
                "snapshot_or_run_id": "e" * 64,
                "payload": {
                    "repository_pseudonym": "repository_" + "b" * 64,
                    "path": "path_" + "c" * 64,
                    "revision": "d" * 64,
                    "fingerprint": "f" * 64,
                },
            }
        )
        self.assertTrue(result.safe, result.limitations)

    def test_an_abbreviated_revision_is_not_matched(self) -> None:
        """Documented bound: this is a floor, not a proof of pseudonymity.

        Short hex tokens are too common to quarantine on, so a 7-12 character
        abbreviated id passes. Redaction is the adapter's job; this check is a
        backstop.
        """
        result = assess_redaction(
            {
                "redaction_status": "producer_redacted",
                "payload": {"revision": "edeef6d"},
            }
        )
        self.assertTrue(result.safe, result.limitations)


if __name__ == "__main__":
    unittest.main()
