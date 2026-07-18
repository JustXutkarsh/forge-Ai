import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from forge.pipeline.ingest import ingest_records
from forge.rag.embed import embed_pending, embed_ticket_ids


def ticket(ticket_id: str, description: str = "Login failure", status: str = "Open") -> dict[str, str]:
    return {
        "ticket_id": ticket_id,
        "issue_description": description,
        "resolution_notes": "Credentials reset",
        "category": "Login Issue",
        "product": "Portal",
        "priority": "High",
        "status": status,
        "ticket_created_date": "2024-01-01",
    }


class FakeStore:
    def __init__(self):
        self.ids = []

    def upsert(self, ids, documents, embeddings, metadatas):
        self.ids.extend(ids)


class FakeClient:
    class Embeddings:
        @staticmethod
        def create(model, input):
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])

    embeddings = Embeddings()


class EmbeddingScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "forge.db"

    def tearDown(self):
        self.temp.cleanup()

    def _embed(self, function, ids=None):
        store = FakeStore()
        with patch("forge.rag.embed._openai_client", return_value=FakeClient()), patch("forge.rag.embed.ChromaStore", return_value=store):
            count = function(self.db_path, ids) if ids is not None else function(self.db_path)
        return count, store.ids

    def test_new_and_retrieval_changed_records_are_targeted(self):
        first = ingest_records([ticket("1")], "test", self.db_path)
        self.assertEqual(first["embedding_ticket_ids"], ["1"])
        count, ids = self._embed(embed_ticket_ids, first["embedding_ticket_ids"])
        self.assertEqual((count, ids), (1, ["1"]))

        changed = ticket("1", description="Password reset still fails")
        result = ingest_records([changed], "test", self.db_path)
        self.assertEqual(result["embedding_ticket_ids"], ["1"])
        count, ids = self._embed(embed_ticket_ids, result["embedding_ticket_ids"])
        self.assertEqual((count, ids), (1, ["1"]))

    def test_metadata_only_and_unchanged_records_embed_nothing(self):
        ingest_records([ticket("1")], "test", self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE tickets SET embedding_status='embedded'")
        conn.commit()
        conn.close()

        metadata = ingest_records([ticket("1", status="Closed")], "test", self.db_path)
        unchanged = ingest_records([ticket("1", status="Closed")], "test", self.db_path)
        self.assertEqual(metadata["embedding_ticket_ids"], [])
        self.assertEqual(unchanged["embedding_ticket_ids"], [])
        self.assertEqual(self._embed(embed_ticket_ids, [])[0], 0)

    def test_embed_pending_still_processes_backlog(self):
        ingest_records([ticket("1"), ticket("2")], "test", self.db_path)
        count, ids = self._embed(embed_pending)
        self.assertEqual((count, sorted(ids)), (2, ["1", "2"]))


if __name__ == "__main__":
    unittest.main()
