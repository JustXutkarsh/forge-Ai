import unittest

from forge.agent.tools import summarize
from forge.cli import _render_ask, _render_status


class CliPolishTests(unittest.TestCase):
    def test_summary_prioritizes_metadata(self):
        tickets = [
            {"ticket_id": "113", "category": "Login Issue", "resolution_notes": "Credentials reset and retry instructions provided.", "priority": "High", "status": "Closed", "issue_description": "Synthetic issue A"},
            {"ticket_id": "123", "category": "Login Issue", "resolution_notes": "Credentials reset and retry instructions provided.", "priority": "Medium", "status": "Closed", "issue_description": "Synthetic issue B"},
        ]
        output = summarize(tickets)
        self.assertIn("Recurring pattern: Login Issue", output)
        self.assertIn("Likely resolution: Credentials reset", output)
        self.assertNotIn("Synthetic issue B", output)

    def test_human_ask_renderer_includes_sources_and_confidence(self):
        output = _render_ask("Summarize login issues", {"answer": "Credential resets were common.", "tool_calls": ["search_data", "summarize"], "source_ticket_ids": ["113", "123"], "confidence": 1.0})
        self.assertIn("Question", output)
        self.assertIn("Summary", output)
        self.assertIn("• Ticket 113", output)
        self.assertIn("1.00", output)

    def test_status_renderer_marks_intentional_limit(self):
        output = _render_status({"database": "data/forge.db", "database_engine": "SQLite", "vector_store": "ChromaDB", "total_records": 200000, "embedded": 100900, "embedding_pending": 99100, "embedding_mode": "Development (intentional limit)", "embedding_failures": 0, "last_ingest": "2026-07-17T22:14:54Z", "freshness": "Up-to-date"})
        self.assertIn("Development (intentional limit)", output)
        self.assertIn("Pending", output)
        self.assertIn("Embedding Failures", output)


if __name__ == "__main__":
    unittest.main()
