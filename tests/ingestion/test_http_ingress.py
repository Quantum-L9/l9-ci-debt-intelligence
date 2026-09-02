"""The HTTP ingress speaks the producer transport's existing vocabulary.

`HTTPSFeedbackTransport` in `Quantum-L9/l9-ci-debt-resolver` already classifies
every response it can receive: `{200, 201, 202, 204, 409}` are success, `409`
specifically is a duplicate acknowledgement, `{408, 425, 429, 500, 502, 503,
504}` are retryable and bounded by its durable outbox, and everything else is
permanent and dead-lettered. These tests hold this side of that contract, so a
status this ingress returns is never one the producer would misread -- an auth
failure or a contract rejection must not be retried forever, and a storage
outage must not be dead-lettered.

The request fixture is the real producer artifact: the same bytes
`JSONFileFeedbackTransport` wrote, posted with the headers
`HTTPSFeedbackTransport` sends.
"""

from __future__ import annotations

import io
import json
import tempfile
import tokenize
import unittest
from pathlib import Path
from typing import Any

from l9_debt_intelligence.ingestion.http_ingress import (
    DEFAULT_PATH,
    FeedbackIngress,
    IngressResponse,
)
from l9_debt_intelligence.ingestion.resolver_feedback import ResolverFeedbackAdapter
from l9_debt_intelligence.ingestion.service import IngestionService

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".l9/producer-compatibility.json"
EVENT_SCHEMA = ROOT / "schemas/intelligence/corpus-event.schema.json"
FIXTURE = ROOT / "tests/fixtures/producers/valid-resolver-feedback.json"

TOKEN = "test-ingress-token"

# The producer's transport classification, restated here so a change on either
# side of the wire has to be deliberate.
PRODUCER_SUCCESS = {200, 201, 202, 204, 409}
PRODUCER_RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


def native_event() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return document


def canonical_body(document: dict[str, Any]) -> bytes:
    """Exactly how `HTTPSFeedbackTransport` encodes its request body."""
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def producer_headers(document: dict[str, Any], *, token: str = TOKEN) -> dict[str, str]:
    """Exactly the headers `HTTPSFeedbackTransport` sends."""
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": str(document["idempotency_key"]),
        "User-Agent": "l9-ci-debt-resolver-feedback/1",
    }


class IngressTestCase(unittest.TestCase):
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
        document: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        path: str = DEFAULT_PATH,
        method: str = "POST",
    ) -> IngressResponse:
        return self.ingress.handle(
            method=method,
            path=path,
            headers=producer_headers(document) if headers is None else headers,
            body=canonical_body(document) if body is None else body,
        )


class HappyPathTests(IngressTestCase):
    def test_a_producer_post_is_accepted_with_201(self) -> None:
        response = self.post(native_event())
        self.assertEqual(201, response.status)
        self.assertEqual("accepted", response.document["status"])
        self.assertIn(response.status, PRODUCER_SUCCESS)

    def test_an_identical_repost_is_409_duplicate(self) -> None:
        """The producer reads 409 as a successful duplicate acknowledgement."""
        first = self.post(native_event())
        second = self.post(native_event())
        self.assertEqual(201, first.status)
        self.assertEqual(409, second.status)
        self.assertEqual("duplicate", second.document["status"])
        self.assertEqual(first.document["record_id"], second.document["record_id"])
        self.assertIn(second.status, PRODUCER_SUCCESS)

    def test_the_response_body_is_the_ingestion_result(self) -> None:
        response = self.post(native_event())
        document = json.loads(response.body())
        self.assertEqual("l9.ingestion-result/v1", document["schema_version"])
        self.assertTrue(response.body().endswith(b"\n"))

    def test_the_ingress_carries_no_payload_back_to_the_producer(self) -> None:
        response = self.post(native_event())
        self.assertNotIn("payload", response.document)


class AuthenticationTests(IngressTestCase):
    def test_a_missing_authorization_header_is_401(self) -> None:
        headers = producer_headers(native_event())
        del headers["Authorization"]
        response = self.post(native_event(), headers=headers)
        self.assertEqual(401, response.status)

    def test_a_wrong_token_is_401(self) -> None:
        response = self.post(
            native_event(),
            headers=producer_headers(native_event(), token="wrong-token"),
        )
        self.assertEqual(401, response.status)

    def test_a_non_bearer_scheme_is_401(self) -> None:
        headers = producer_headers(native_event())
        headers["Authorization"] = f"Basic {TOKEN}"
        response = self.post(native_event(), headers=headers)
        self.assertEqual(401, response.status)

    def test_authentication_failure_is_not_retryable_for_the_producer(self) -> None:
        """A bad credential retried on a bounded outbox burns the budget."""
        response = self.post(
            native_event(),
            headers=producer_headers(native_event(), token="wrong-token"),
        )
        self.assertNotIn(response.status, PRODUCER_RETRYABLE)
        self.assertNotIn(response.status, PRODUCER_SUCCESS)

    def test_an_unauthenticated_request_writes_nothing(self) -> None:
        headers = producer_headers(native_event())
        del headers["Authorization"]
        self.post(native_event(), headers=headers)
        self.assertEqual([], sorted(p.name for p in self.storage_root.rglob("*.json")))

    def test_a_blank_token_cannot_configure_the_ingress(self) -> None:
        with self.assertRaises(ValueError):
            FeedbackIngress(
                service=IngestionService(
                    event_schema=EVENT_SCHEMA,
                    compatibility_registry=REGISTRY,
                    storage_root=self.storage_root,
                ),
                adapter=ResolverFeedbackAdapter(),
                bearer_token="",
            )


class RoutingTests(IngressTestCase):
    def test_an_unknown_path_is_404(self) -> None:
        response = self.post(native_event(), path="/api/v1/other")
        self.assertEqual(404, response.status)

    def test_a_query_string_does_not_defeat_path_matching(self) -> None:
        response = self.post(native_event(), path=f"{DEFAULT_PATH}?trace=1")
        self.assertEqual(201, response.status)

    def test_a_get_is_405(self) -> None:
        response = self.post(native_event(), method="GET")
        self.assertEqual(405, response.status)


class BoundsAndContractTests(IngressTestCase):
    def test_an_oversized_body_is_413(self) -> None:
        ingress = FeedbackIngress(
            service=IngestionService(
                event_schema=EVENT_SCHEMA,
                compatibility_registry=REGISTRY,
                storage_root=self.storage_root,
            ),
            adapter=ResolverFeedbackAdapter(),
            bearer_token=TOKEN,
            max_body_bytes=64,
        )
        document = native_event()
        response = ingress.handle(
            method="POST",
            path=DEFAULT_PATH,
            headers=producer_headers(document),
            body=canonical_body(document),
        )
        self.assertEqual(413, response.status)

    def test_too_large_is_permanent_not_retryable(self) -> None:
        """Retrying an oversized body cannot ever succeed."""
        self.assertNotIn(413, PRODUCER_RETRYABLE)

    def test_a_non_json_body_is_422(self) -> None:
        response = self.post(native_event(), body=b"not json at all")
        self.assertEqual(422, response.status)

    def test_a_json_array_body_is_422(self) -> None:
        response = self.post(native_event(), body=b"[]")
        self.assertEqual(422, response.status)

    def test_a_missing_idempotency_key_is_422(self) -> None:
        headers = producer_headers(native_event())
        del headers["Idempotency-Key"]
        response = self.post(native_event(), headers=headers)
        self.assertEqual(422, response.status)

    def test_a_mismatched_idempotency_key_is_422(self) -> None:
        """The header must describe the document that carries it."""
        headers = producer_headers(native_event())
        headers["Idempotency-Key"] = "feedback_idempotency_" + "0" * 64
        response = self.post(native_event(), headers=headers)
        self.assertEqual(422, response.status)

    def test_an_unsupported_contract_version_is_422(self) -> None:
        future = native_event()
        future["schema_version"] = "l9.intelligence-feedback-event/v2"
        response = self.post(future)
        self.assertEqual(422, response.status)

    def test_a_contract_rejection_is_permanent_for_the_producer(self) -> None:
        """422 must dead-letter, not spin the outbox against a bad document."""
        response = self.post(native_event(), body=b"not json at all")
        self.assertNotIn(response.status, PRODUCER_RETRYABLE)
        self.assertNotIn(response.status, PRODUCER_SUCCESS)

    def test_a_quarantined_event_is_422_and_stores_no_record(self) -> None:
        leaking = native_event()
        leaking["limitations"] = ["truncated at /home/runner/work/repo/build.log"]
        response = self.post(leaking)
        self.assertEqual(422, response.status)
        self.assertEqual("quarantined", response.document["status"])
        self.assertIsNone(response.document["record_id"])

    def test_headers_are_matched_case_insensitively(self) -> None:
        document = native_event()
        response = self.post(
            document,
            headers={
                "authorization": f"Bearer {TOKEN}",
                "idempotency-key": str(document["idempotency_key"]),
            },
        )
        self.assertEqual(201, response.status)


class StorageFailureTests(IngressTestCase):
    def test_a_storage_outage_is_503_and_retryable(self) -> None:
        """The producer's outbox already bounds this; we add no second retry."""

        class FailingService(IngestionService):
            def ingest(self, event: dict[str, Any]) -> Any:
                raise OSError("storage unavailable")

        ingress = FeedbackIngress(
            service=FailingService(
                event_schema=EVENT_SCHEMA,
                compatibility_registry=REGISTRY,
                storage_root=self.storage_root,
            ),
            adapter=ResolverFeedbackAdapter(),
            bearer_token=TOKEN,
        )
        document = native_event()
        response = ingress.handle(
            method="POST",
            path=DEFAULT_PATH,
            headers=producer_headers(document),
            body=canonical_body(document),
        )
        self.assertEqual(503, response.status)
        self.assertIn(response.status, PRODUCER_RETRYABLE)


class NoRetryLogicTests(unittest.TestCase):
    def test_the_ingress_implements_no_retry_or_backoff(self) -> None:
        """Retry belongs to the producer's durable outbox, not to this layer.

        Scans executable code only. The module's own docstring *describes* the
        producer's backoff and `Retry-After` handling, and prose about a
        mechanism is the opposite of implementing one -- matching it would make
        this test fire on its own explanation.
        """
        source = (
            ROOT / "src/l9_debt_intelligence/ingestion/http_ingress.py"
        ).read_text(encoding="utf-8")
        code = "".join(
            token.string
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type not in {tokenize.COMMENT, tokenize.STRING}
        )
        for name in ("sleep", "backoff", "retry", "attempt", "queue"):
            with self.subTest(name=name):
                self.assertNotIn(name, code.lower())


if __name__ == "__main__":
    unittest.main()
