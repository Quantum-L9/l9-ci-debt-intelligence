"""A thin HTTP ingress for the Resolver's already-designed HTTPS transport.

`HTTPSFeedbackTransport` in `Quantum-L9/l9-ci-debt-resolver` posts a canonical
`l9.intelligence-feedback-event/v1` document with a bearer token and an
`Idempotency-Key` header, and already classifies the response: `409` is a
successful duplicate acknowledgement, `408/425/429/5xx` are retryable and
bounded by its durable outbox, and everything else is permanent and
dead-lettered. This module answers in exactly that vocabulary and does nothing
else -- no retry, no backoff, no queue. A second retry mechanism here would
fight the producer's outbox rather than serve it.

The layer owns no learning logic. It authenticates, bounds the body, checks the
idempotency header against the document that carries it, and hands the result
to `ResolverFeedbackAdapter` and `IngestionService`. Every admission decision
after that point belongs to the existing ingestion path.

Deliberately built on the standard library: a web framework would be a new
runtime dependency, and this surface is far too small to justify one. The
authoritative dependency set is declared in `pyproject.toml`; this module adds
nothing to it. There is no in-process TLS either -- the resolver requires an
`https://` endpoint, so this server is designed to sit behind TLS termination.

The server is deliberately single-request. `FilesystemCorpusStore` is a
single-writer filesystem store: sequence allocation, record admission, index
replacement, and ledger append are one ingestion transaction but are not
protected by a cross-thread lock. Serializing requests at this boundary keeps
those invariants true without moving HTTP concurrency concerns into the corpus
store. The resolver's durable outbox already provides bounded retry and absorbs
backpressure.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from l9_debt_intelligence.contracts.errors import ContractError

from .resolver_feedback import ResolverFeedbackAdapter, ResolverFeedbackError
from .service import IngestionService

DEFAULT_PATH = "/api/v1/events"

# The producer's own transport reads at most 1 MiB of any response, and a
# feedback event is a few kilobytes. This bound exists to refuse abuse, not to
# constrain legitimate producer growth.
DEFAULT_MAX_BODY_BYTES = 1024 * 1024

# Dispositions the ingestion service can return, mapped to the status codes the
# producer's transport already understands.
_DISPOSITION_STATUS = {
    "accepted": 201,
    "duplicate": 409,
    "quarantined": 422,
}


@dataclass(frozen=True)
class IngressResponse:
    status: int
    document: dict[str, Any]

    def body(self) -> bytes:
        return (
            json.dumps(
                self.document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")


def _error(status: int, reason: str) -> IngressResponse:
    return IngressResponse(
        status=status,
        document={
            "schema_version": "l9.ingestion-ingress-error/v1",
            "status": "rejected",
            "reason": reason,
        },
    )


class FeedbackIngress:
    """Request handling as a pure function, so it is testable without sockets."""

    def __init__(
        self,
        *,
        service: IngestionService,
        adapter: ResolverFeedbackAdapter,
        bearer_token: str,
        path: str = DEFAULT_PATH,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        if not bearer_token:
            raise ValueError("ingress bearer token is required")
        self._service = service
        self._adapter = adapter
        self._bearer_token = bearer_token
        self._path = path
        self._max_body_bytes = max_body_bytes

    @property
    def max_body_bytes(self) -> int:
        return self._max_body_bytes

    def _authorized(self, headers: Mapping[str, str]) -> bool:
        supplied = headers.get("authorization") or headers.get("Authorization") or ""
        scheme, _, token = supplied.partition(" ")
        if scheme.lower() != "bearer":
            return False
        return hmac.compare_digest(token.strip(), self._bearer_token)

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        for key, value in headers.items():
            if key.lower() == name.lower():
                return value
        return None

    def handle(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> IngressResponse:
        if path.split("?", 1)[0] != self._path:
            return _error(404, "unknown endpoint")
        if method.upper() != "POST":
            return _error(405, "method not allowed")
        if not self._authorized(headers):
            return _error(401, "bearer authentication failed")
        if len(body) > self._max_body_bytes:
            return _error(413, "payload too large")
        try:
            native = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _error(422, "body is not valid UTF-8 JSON")
        if not isinstance(native, dict):
            return _error(422, "body is not a JSON object")

        # The producer sends the event's own idempotency key in the header. If
        # the two disagree, the request is not the document it claims to be.
        supplied_key = self._header(headers, "Idempotency-Key")
        if supplied_key is None:
            return _error(422, "Idempotency-Key header is required")
        if supplied_key != native.get("idempotency_key"):
            return _error(422, "Idempotency-Key does not match the event")

        try:
            envelope = self._adapter.project(native)
        except ResolverFeedbackError as error:
            return _error(422, str(error))
        except ContractError as error:
            return _error(422, str(error))

        try:
            result = self._service.ingest(envelope)
        except OSError:
            # Storage is unavailable. 503 is retryable for the producer, whose
            # outbox already bounds the retry; do not add a second one here.
            return _error(503, "ingestion storage is temporarily unavailable")

        return IngressResponse(
            status=_DISPOSITION_STATUS.get(result.status, 422),
            document=result.as_dict(),
        )


class _Handler(BaseHTTPRequestHandler):
    server_version = "l9-intelligence-ingress/1"
    ingress: FeedbackIngress

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        declared = self.headers.get("Content-Length", "0")
        try:
            length = int(declared)
        except ValueError:
            length = -1
        if length < 0:
            self._respond(_error(422, "invalid Content-Length"))
            return
        if length > self.ingress.max_body_bytes:
            # Refuse before reading, so an oversized body is never buffered.
            self._respond(_error(413, "payload too large"))
            return
        body = self.rfile.read(length)
        self._respond(
            self.ingress.handle(
                method="POST",
                path=self.path,
                headers=dict(self.headers.items()),
                body=body,
            )
        )

    def _respond(self, response: IngressResponse) -> None:
        payload = response.body()
        self.send_response(response.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default stderr access log.

        It records request lines verbatim, which is a redaction surface this
        repository does not accept by default.
        """
        return


def build_server(
    *,
    ingress: FeedbackIngress,
    host: str,
    port: int,
) -> HTTPServer:
    """Build a single-request server around the single-writer corpus store."""
    handler = type("BoundHandler", (_Handler,), {"ingress": ingress})
    return HTTPServer((host, port), handler)
