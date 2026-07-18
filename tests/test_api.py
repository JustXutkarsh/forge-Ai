import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from forge.api.app import create_app
from forge.api.dependencies import SQLiteConnections
from forge.config import OpenAIConfigurationError
from forge.profiling import stage, note


class StubChroma:
    def count(self):
        return 2


class StubRuntime:
    def __init__(self, db_path: Path):
        self.database = SQLiteConnections(db_path)
        self.embedding_service = SimpleNamespace(dimension=768)
        self.chroma_store = StubChroma()

    @property
    def semantic_ready(self):
        return True

    def startup(self):
        connection = self.database.get()
        connection.execute("INSERT INTO tickets (ticket_id, category, issue_description, resolution_notes, record_hash, retrieval_hash, embedding_status, ingested_at) VALUES ('1', 'Login Issue', 'Cannot sign in', 'Password reset fixed the issue', 'r', 'h', 'embedded', 'now')")
        connection.execute("INSERT INTO tickets (ticket_id, category, issue_description, resolution_notes, record_hash, retrieval_hash, embedding_status, ingested_at) VALUES ('2', 'Payment Problem', 'Payment failed', 'Payment retried successfully', 'r', 'h', 'embedded', 'now')")
        connection.commit()

    def shutdown(self):
        self.database.close_all()

    def connection(self):
        return self.database.get()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = StubRuntime(Path(self.temp.name) / "forge.db")
        self.client_context = TestClient(create_app(self.runtime))
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp.cleanup()

    def test_root_health_and_stats(self):
        root = self.client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertTrue(root.json()["semantic_ready"])
        self.assertEqual(self.client.get("/docs").status_code, 200)
        self.assertEqual(self.client.get("/redoc").status_code, 200)
        health = self.client.post("/health/retrieval")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["collection_size"], 2)
        stats = self.client.get("/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["total_tickets"], 2)
        self.assertEqual(stats.json()["vector_dimension"], 768)

    def test_ask_delegates_to_engine_and_returns_contract(self):
        def fake_ask(conn, question):
            with stage("Embedding request"), stage("Retrieval"):
                note("Retrieval strategy=semantic evidence_ids=['1']")
            return {
                "answer": "Password resets resolved the login issue.",
                "confidence": 0.91,
                "tool_calls": ["search_data", "summarize"],
                "source_ticket_ids": ["1"],
                "tickets": [{"ticket_id": "1", "category": "Login Issue", "resolution_notes": "Password reset fixed the issue"}],
            }

        with patch("forge.api.routes.execute_ask", side_effect=fake_ask) as engine:
            response = self.client.post("/ask", json={"question": "Summarize login issues", "max_evidence": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["retrieval_strategy"], "semantic")
        self.assertEqual(response.json()["evidence"][0]["ticket_id"], "1")
        self.assertGreaterEqual(response.json()["timings"]["total_ms"], 0)
        engine.assert_called_once()

    def test_ask_forwards_explicit_investigation_context(self):
        context = {
            "retrieval_strategy": "semantic",
            "evidence": [{"ticket_id": "1", "score": 0.91, "summary": "Password reset fixed the issue"}],
        }

        def fake_ask(conn, question, investigation_context):
            self.assertEqual(question, "List the ticket IDs and explain why each one was selected.")
            self.assertEqual(investigation_context, context)
            with stage("Retrieval"):
                note("Retrieval strategy=semantic evidence_ids=['1']")
            return {
                "answer": "Ticket 1 was selected by semantic retrieval with similarity score 0.910.",
                "confidence": 0.91,
                "tool_calls": ["investigation_context"],
                "source_ticket_ids": ["1"],
                "tickets": [{
                    "ticket_id": "1",
                    "_retrieval_distance": 0.09,
                    "issue_description": "Password reset fixed the issue",
                }],
            }

        with patch("forge.api.routes.execute_ask", side_effect=fake_ask) as engine:
            response = self.client.post("/ask", json={"question": "List the ticket IDs and explain why each one was selected.", "investigation_context": context})
        self.assertEqual(response.status_code, 200)
        self.assertIn("similarity score", response.json()["answer"])
        engine.assert_called_once()

    def test_validation_and_configuration_errors_are_structured(self):
        invalid = self.client.post("/ask", json={"question": ""})
        self.assertEqual(invalid.status_code, 422)
        with patch("forge.api.routes.execute_ask", side_effect=OpenAIConfigurationError("missing key")):
            response = self.client.post("/ask", json={"question": "How many tickets?"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "openai_configuration")


if __name__ == "__main__":
    unittest.main()
