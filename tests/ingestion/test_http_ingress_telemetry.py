"""The ingress accepts the LSP's spooled telemetry, not only the Resolver's.

`TelemetryTransport` in `Quantum-L9/l9-ci-debt-lsp` flushes its spool as
`application/x-ndjson`: one canonical `l9.telemetry-event/v1` document per line,
with a bearer token and no per-line header. Before this suite existed, that
batch reached an ingress that parsed the whole body as a single JSON object and
answered 422 -- a permanent rejection for the producer, which would have
dead-lettered every telemetry batch on first delivery and left the corpus
blind to the only surface that can report a prevented failure.

These tests hold the batch contract from the producer's side: accepted,
replayed, mixed, and malformed.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from l9_debt_intelligence.ingestion.http_ingress import (
    DEFAULT_PATH,
    FeedbackIngress,
    IngressResponse,
)
from l9_debt_intelligence.ingestion.lsp_telemetry import LspTelemetryAdapter
from l9_debt_intelligence.ingestion.resolver_feedback import ResolverFeedbackAdapter
from l9_debt_intelligence.ingestion.service import IngestionService

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".l9/producer-compatibility.json"
EVENT_SCHEMA = ROOT / "schemas/intelligence/corpus-event.schema.json"
TOKEN = "test-ingress-token"

#: The producer's own transport reads at most 1 MiB of a response.
PRODUCER_SUCCESS = {200, 201, 202, 204, 409}
PRODUCER_RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


def telemetry_event(
    *,
    event_id: str = "lsp_evt_0001",
    event_type: str = "diagnostic_shown",
    sequence: int = 0,
    outcome: str | None = None,
    disposition: str | None = None,
) -> dict[str, Any]:
    """One event exactly as `TelemetryEvent.as_dict()` emits it."""
    return {
        "schema_version": "l9.telemetry-event/v1",
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": "2026-11-24T12:00:00Z",
        "installation_id": "lsp_inst_0123456789abcdef",
        "session_id": "lsp_sess_0123456789abcdef",
        "sequence": sequence,
        "client_name": "vscode",
        "client_version": "1.0.0",
        "lsp_version": "1.0.0",
        "rule_pack_id": "defense-pack-2026-11-20",
        "rule_pack_version": "1.0.0",
        "corpus_snapshot": "snapshot-0007",
        "canonical_rule_id": "L9-CI-0001",
        "provider_rule_id": "semgrep.python.lang.security.audit.eval",
        "finding_id": "finding_0001",
        "analysis_request_id": "analysis_0001",
        "action_id": None,
        "template_id": None,
        "outcome": outcome,
        "disposition": disposition,
        "latency_bucket": "lt_50ms",
        "limitations": [],
    }


def ndjson(documents: list[dict[str, Any]]) -> bytes:
    """Exactly how `TelemetryTransport.deliver_once` encodes its request body."""
    return (
        b"\n".join(
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            for document in documents
        )
        + b"\n"
    )


def batch_headers(*, token: str = TOKEN) -> dict[str, str]:
    """Exactly the headers `TelemetryTransport` sends."""
    return {
        "Content-Type": "application/x-ndjson",
        "Authorization": f"Bearer {token}",
        "User-Agent": "l9-ci-debt-lsp-telemetry/1",
    }


class TelemetryIngressTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage_root = Path(self.directory.name)
        self.ingress = FeedbackIngress(
            service=IngestionService(
                event_schema=EVENT_SCHEMA,
                compatibility_registry=REGISTRY,
                storage_root=self.storage_root,
            ),
            adapter=ResolverFeedbackAdapter(),
            bearer_token=TOKEN,
        )

    def post(
        self,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        path: str = DEFAULT_PATH,
    ) -> IngressResponse:
        return self.ingress.handle(
            method="POST",
            path=path,
            headers=batch_headers() if headers is None else headers,
            body=body,
        )


class BatchAcceptanceTests(TelemetryIngressTestCase):
    def test_a_three_event_batch_is_accepted_with_201(self) -> None:
        documents = [
            telemetry_event(event_id=f"lsp_evt_{n:04d}", sequence=n) for n in range(3)
        ]
        response = self.post(ndjson(documents))
        self.assertEqual(201, response.status)
        self.assertIn(response.status, PRODUCER_SUCCESS)
        self.assertEqual(3, response.document["accepted"])
        self.assertEqual(0, response.document["rejected"])
        self.assertEqual("l9.ingestion-batch-result/v1", response.document["schema_version"])

    def test_a_replayed_batch_is_acknowledged_as_duplicates(self) -> None:
        """Replay must not be a permanent failure: the spool retries batches."""
        documents = [telemetry_event()]
        first = self.post(ndjson(documents))
        second = self.post(ndjson(documents))
        self.assertEqual(201, first.status)
        self.assertEqual(200, second.status)
        self.assertEqual(1, second.document["duplicate"])
        self.assertEqual(0, second.document["accepted"])

    def test_a_false_positive_is_classified_as_its_own_corpus_class(self) -> None:
        document = telemetry_event(
            event_id="lsp_evt_fp",
            event_type="false_positive_disposition",
            disposition="false_positive",
        )
        response = self.post(ndjson([document]))
        self.assertEqual(201, response.status)
        record = json.loads(
            next((self.storage_root / "records").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("false_positive_disposition", record["event_class"])

    def test_the_payload_survives_projection_whole(self) -> None:
        document = telemetry_event(event_id="lsp_evt_payload")
        envelope = LspTelemetryAdapter().project(document)
        # The producer document is carried whole: rule identity, pack version
        # and the installation pseudonym are what downstream learning keys on.
        self.assertEqual(document, envelope["payload"])
        self.assertEqual("editor_diagnostic_outcome", envelope["event_class"])
        self.assertEqual("Quantum-L9/l9-ci-debt-lsp", envelope["producer_id"])
        self.assertEqual("l9.telemetry-event/v1", envelope["producer_contract"])


class BatchRejectionTests(TelemetryIngressTestCase):
    def test_a_malformed_line_is_a_permanent_rejection(self) -> None:
        body = ndjson([telemetry_event()]) + b'{"schema_version": "l9.telemetry-event/v1"\n'
        response = self.post(body)
        self.assertEqual(422, response.status)
        self.assertNotIn(response.status, PRODUCER_RETRYABLE)

    def test_an_unknown_contract_in_a_batch_rejects_the_batch(self) -> None:
        foreign = telemetry_event(event_id="lsp_evt_foreign")
        foreign["schema_version"] = "l9.editor-outcome-event/v1"
        response = self.post(ndjson([telemetry_event(), foreign]))
        self.assertEqual(422, response.status)
        self.assertEqual("partial", response.document["status"])
        self.assertEqual(1, response.document["rejected"])

    def test_a_missing_required_field_rejects_that_document(self) -> None:
        document = telemetry_event(event_id="lsp_evt_missing")
        del document["installation_id"]
        response = self.post(ndjson([document]))
        self.assertEqual(422, response.status)
        self.assertEqual(1, response.document["rejected"])

    def test_an_empty_batch_is_rejected(self) -> None:
        response = self.post(b"\n\n")
        self.assertEqual(422, response.status)

    def test_authentication_is_still_required(self) -> None:
        response = self.post(
            ndjson([telemetry_event()]),
            headers={"Content-Type": "application/x-ndjson"},
        )
        self.assertEqual(401, response.status)


class SingleDocumentRoutingTests(TelemetryIngressTestCase):
    def test_one_telemetry_document_as_json_routes_by_schema_version(self) -> None:
        """A producer that sends one event with application/json still lands."""
        body = json.dumps(telemetry_event(event_id="lsp_evt_single")).encode("utf-8")
        response = self.post(
            body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}",
            },
        )
        self.assertEqual(201, response.status)
        self.assertEqual("accepted", response.document["status"])

    def test_the_resolver_path_still_requires_its_idempotency_header(self) -> None:
        """The resolver contract is unchanged: no key, no admission."""
        fixture = ROOT / "tests/fixtures/producers/valid-resolver-feedback.json"
        document = json.loads(fixture.read_text(encoding="utf-8"))
        body = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        response = self.post(
            body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}",
            },
        )
        self.assertEqual(422, response.status)
        self.assertEqual("rejected", response.document["status"])


if __name__ == "__main__":
    unittest.main()
