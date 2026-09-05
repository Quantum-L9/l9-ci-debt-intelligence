from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from l9_debt_intelligence.ingestion.storage import (
    FilesystemCorpusStore,
    StorageError,
)
from l9_debt_intelligence.ingestion.verify import (
    LedgerVerificationError,
    verify_store,
)


class StorageImmutabilityTests(unittest.TestCase):
    def test_record_cannot_be_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FilesystemCorpusStore(Path(directory))
            first = {
                "record_id": "cr_" + ("a" * 64),
                "value": 1,
            }
            second = {
                "record_id": "cr_" + ("a" * 64),
                "value": 2,
            }
            store.write_record(first)
            with self.assertRaises(StorageError):
                store.write_record(second)


if __name__ == "__main__":
    unittest.main()


class ObservationStoreVerification(unittest.TestCase):
    """Derived observations are a store artifact, so store verification covers them.

    `build_snapshot` verifies the store and then reads the observations, so a
    verification that ignored them would declare the store valid and hand the
    snapshot builder unverified input.
    """

    def _store(self, root: Path) -> FilesystemCorpusStore:
        store = FilesystemCorpusStore(root)
        store.initialize()
        return store

    def _record(self, record_id: str) -> dict[str, Any]:
        return {
            "schema_version": "l9.corpus-record/v1",
            "record_id": record_id,
            "source_event_id": "evt_1",
            "producer_id": "Quantum-L9/l9-ci-sdk",
            "event_class": "static_finding",
            "lifecycle_state": "NORMALIZED",
            "redaction_status": "intelligence_redacted",
            "payload_reference": {
                "producer_contract": "l9.finding-bundle/v1",
                "sdk_schema_references": [],
                "content_hash": "a" * 64,
            },
            "limitations": [],
            "superseded_by": None,
        }

    def test_observations_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self._store(root)
            record_id = "cr_" + "1" * 64
            store.write_record(self._record(record_id))
            store.write_observations(
                record_id,
                [
                    {
                        "schema_version": "l9.learning-observation/v1",
                        "record_id": record_id,
                        "producer_id": "Quantum-L9/l9-ci-sdk",
                        "event_class": "static_finding",
                        "producer_contract": "l9.finding-bundle/v1",
                        "occurrence_scope": "repository_" + "a" * 64,
                        "recurrence_fingerprint": "b" * 64,
                    }
                ],
            )
            self.assertEqual(verify_store(root)["observation_count"], 1)

    def test_orphaned_observations_fail_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self._store(root)
            store.write_observations("cr_" + "2" * 64, [])
            with self.assertRaises(LedgerVerificationError):
                verify_store(root)

    def test_an_observation_naming_another_record_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self._store(root)
            record_id = "cr_" + "3" * 64
            store.write_record(self._record(record_id))
            store.write_observations(
                record_id,
                [
                    {
                        "schema_version": "l9.learning-observation/v1",
                        "record_id": "cr_" + "4" * 64,
                        "producer_id": "Quantum-L9/l9-ci-sdk",
                        "event_class": "static_finding",
                        "producer_contract": "l9.finding-bundle/v1",
                        "occurrence_scope": "repository_" + "a" * 64,
                        "recurrence_fingerprint": "b" * 64,
                    }
                ],
            )
            with self.assertRaises(LedgerVerificationError):
                verify_store(root)
