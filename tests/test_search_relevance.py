import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.agent.planner import plan_question
from forge.agent.tools import search_data, summarize
from forge.analytics.queries import query_structured
from forge.analytics.schema import init_db
from forge.pipeline.ingest import ingest_records
from forge.search.query_normalizer import expand_query


class SearchRelevanceTests(unittest.TestCase):
    def test_query_expansion_preserves_original_and_adds_login_terms(self):
        for query in ("login", "authentication", "sign in", "credentials"):
            expanded = expand_query(query)
            self.assertTrue(expanded.startswith(query))
            self.assertIn("login", expanded)
            self.assertIn("authentication", expanded)
            self.assertIn("credential", expanded)

    def test_query_expansion_covers_payment_and_performance_terms(self):
        for query, expected in (("payment", "billing"), ("billing", "refund"), ("refund", "payment"), ("performance", "slow"), ("slow", "lag"), ("lag", "freeze")):
            self.assertIn(expected, expand_query(query))

    def test_credential_retrieval_preserves_query_and_summary_uses_text_evidence(self):
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "forge.db"
        ingest_records([
            {"ticket_id": "1", "category": "Performance Issue", "issue_description": "Users cannot sign in with their credentials", "resolution_notes": "Password reset restored account access"},
            {"ticket_id": "2", "category": "Performance Issue", "issue_description": "Authentication fails during sign in", "resolution_notes": "Credentials were reset"},
        ], "test", db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            result = search_data(conn, "credential issues", k=5)
        self.assertEqual(result["query"], "credential issues")
        self.assertCountEqual(result["source_ticket_ids"], ["1", "2"])
        self.assertIn("Recurring pattern: Login Issue", summarize(result["tickets"]))
        self.assertNotIn("Performance Issue was the dominant", summarize(result["tickets"]))
        conn.close()
        temp.cleanup()

    def test_summary_reports_category_ties(self):
        tickets = [
            {"category": "Performance Issue", "issue_description": "Login credentials fail", "resolution_notes": "Password reset"},
            {"category": "Payment Problem", "issue_description": "Payment was declined", "resolution_notes": "Refund issued"},
        ]
        output = summarize(tickets)
        self.assertIn("Recurring patterns:", output)
        self.assertIn("Login Issue", output)
        self.assertIn("Payment Problem", output)

    def test_top_n_is_passed_to_sql(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        for index in range(10):
            conn.execute("INSERT INTO tickets (ticket_id,category,record_hash,retrieval_hash,embedding_status,ingested_at) VALUES (?,?,?,?,?,?)", (str(index), f"Category {index}", "r", "h", "embedded", "now"))
        conn.commit()
        result = query_structured(conn, "group_by", "category", limit=5)
        self.assertEqual(len(result["results"]), 5)
        plan = plan_question("Show top 5 labels")
        self.assertEqual(plan.steps[0].arguments["limit"], 5)
        conn.close()


if __name__ == "__main__":
    unittest.main()
