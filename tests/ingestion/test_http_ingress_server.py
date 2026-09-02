from __future__ import annotations

import tempfile
import unittest
from http.server import HTTPServer
from pathlib import Path

from l9_debt_intelligence.ingestion.http_ingress import FeedbackIngress, build_server
from l9_debt_intelligence.ingestion.resolver_feedback import ResolverFeedbackAdapter
from l9_debt_intelligence.ingestion.service import IngestionService

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".l9/producer-compatibility.json"
EVENT_SCHEMA = ROOT / "schemas/intelligence/corpus-event.schema.json"
TOKEN = "test-ingress-token"


class ServerSerializationTests(unittest.TestCase):
    def test_server_serializes_requests_for_single_writer_corpus_store(self) -> None:
        """HTTP concurrency must not outrun the filesystem store's invariants."""
        with tempfile.TemporaryDirectory() as directory:
            ingress = FeedbackIngress(
                service=IngestionService(
                    event_schema=EVENT_SCHEMA,
                    compatibility_registry=REGISTRY,
                    storage_root=Path(directory),
                ),
                adapter=ResolverFeedbackAdapter(),
                bearer_token=TOKEN,
            )
            server = build_server(
                ingress=ingress,
                host="127.0.0.1",
                port=0,
            )
            try:
                self.assertIs(type(server), HTTPServer)
            finally:
                server.server_close()


if __name__ == "__main__":
    unittest.main()
