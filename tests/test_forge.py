import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from forge.analytics.queries import StructuredQueryError, query_structured
from forge.analytics.schema import init_db
from forge.pipeline.ingest import ingest_csv


HEADERS = [
    "ticket_id", "customer_name", "customer_email", "product", "category", "issue_description", "resolution_notes", "priority", "status", "channel", "region", "customer_age", "customer_gender", "subscription_type", "customer_tenure_months", "previous_tickets", "customer_satisfaction_score", "first_response_time_hours", "resolution_time_hours", "ticket_created_date", "ticket_resolved_date", "escalated", "sla_breached", "operating_system", "browser", "payment_method", "language", "preferred_contact_time", "issue_complexity_score", "customer_segment"
]


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp.name) / "tickets.csv"
        self.db_path = Path(self.temp.name) / "forge.db"
        row = {field: "1" for field in HEADERS}
        row.update(ticket_id="1", issue_description="Cannot log in", resolution_notes="Reset credentials", category="Login Issue", product="Web Portal", priority="High", status="Open", ticket_created_date="2024-01-01", ticket_resolved_date="2024-01-02", customer_satisfaction_score="4", first_response_time_hours="1.5", resolution_time_hours="3.0")
        with self.csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS); writer.writeheader(); writer.writerow(row)

    def tearDown(self):
        self.temp.cleanup()

    def test_incremental_ingestion_and_metadata_change(self):
        first = ingest_csv(self.csv_path, self.db_path); self.assertEqual(first["new"], 1); self.assertEqual(first["embedding_candidates"], 1)
        second = ingest_csv(self.csv_path, self.db_path); self.assertEqual(second["skipped"], 1); self.assertEqual(second["embedding_candidates"], 0)
        with self.csv_path.open() as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["status"] = "Closed"
        with self.csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS); writer.writeheader(); writer.writerows(rows)
        third = ingest_csv(self.csv_path, self.db_path); self.assertEqual(third["changed"], 1); self.assertEqual(third["embedding_candidates"], 0)

    def test_structured_query_is_exact_and_excludes_pii(self):
        ingest_csv(self.csv_path, self.db_path)
        conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row; init_db(conn)
        result = query_structured(conn, "group_by", "category")
        self.assertEqual(result["results"][0]["count"], 1)
        filtered = query_structured(conn, "filter", "category", {"category": "Login Issue"})
        self.assertNotIn("customer_email", filtered["results"][0])
        with self.assertRaises(StructuredQueryError): query_structured(conn, "group_by", "customer_email")


if __name__ == "__main__":
    unittest.main()
