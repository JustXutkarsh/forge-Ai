import sqlite3
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from eval.evaluator import EvaluationAnswerer, evaluate_dataset, load_dataset
from eval.metrics import precision_at_k, recall_at_k
from eval.run_eval import format_report
from forge.analytics.schema import init_db


class EvaluationTests(unittest.TestCase):
    def test_dataset_has_required_coverage(self):
        cases = load_dataset(Path("eval/dataset.json"))
        self.assertGreaterEqual(len(cases), 45)
        self.assertTrue({case["type"] for case in cases} >= {"structured", "semantic", "summary", "anomaly", "unsupported"})

    def test_retrieval_metrics_at_five(self):
        self.assertEqual(recall_at_k(["1", "2", "3"], ["1", "4"]), 0.5)
        self.assertEqual(precision_at_k(["1", "2", "3"], ["1", "4"]), 1 / 3)

    def test_evaluator_aggregates_grounded_results(self):
        cases = [
            {"id": "structured", "type": "structured", "question": "How many tickets are there?", "expected_tools": ["query_structured"], "expected_operation": "count", "expected_field": "ticket_id"},
            {"id": "semantic", "type": "semantic", "question": "Find login failures.", "expected_tools": ["search_data"], "gold_filter": {"category": "Login Issue"}},
            {"id": "unsupported", "type": "unsupported", "question": "Who is the CEO?", "expected_tools": ["search_data"], "unsupported": True},
        ]
        answers = {
            "How many tickets are there?": {"tool_calls": ["query_structured"], "structured": {"count": 2}, "answer": "Count: 2."},
            "Find login failures.": {"tool_calls": ["search_data"], "source_ticket_ids": ["1", "999"], "evidence": [{"ticket_id": "1"}], "answer": "Login failures were found."},
            "Who is the CEO?": {"tool_calls": ["search_data"], "source_ticket_ids": [], "answer": "No supporting evidence found in indexed data."},
        }

        def answer_fn(_conn, question):
            return answers[question]

        fixture = sqlite3.connect(":memory:")
        fixture.row_factory = sqlite3.Row
        init_db(fixture)
        fixture.execute("INSERT INTO tickets (ticket_id,category,issue_description,record_hash,retrieval_hash,embedding_status,ingested_at) VALUES ('1','Login Issue','Login fails','','','embedded','now')")
        fixture.execute("INSERT INTO tickets (ticket_id,category,issue_description,record_hash,retrieval_hash,embedding_status,ingested_at) VALUES ('2','Login Issue','Cannot log in','','','embedded','now')")
        fixture.commit()
        report = evaluate_dataset(fixture, cases, answer_fn)
        self.assertEqual(report["questions"], 3)
        self.assertEqual(report["planner_accuracy"], 1.0)
        self.assertEqual(report["structured_query_accuracy"], 1.0)
        self.assertEqual(report["recall_at_5"], 0.5)
        self.assertEqual(report["precision_at_5"], 0.5)
        self.assertEqual(report["hallucination_rate"], 0.0)
        self.assertNotIn("details", report)
        fixture.close()

    def test_evaluation_answerer_reuses_chroma_store(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            answerer = EvaluationAnswerer()
        answerer._embedding_client = object()
        with patch("eval.evaluator.ChromaStore", return_value=object()) as chroma:
            first = answerer._store()
            second = answerer._store()
        self.assertIs(first, second)
        chroma.assert_called_once()
        answerer.close()

    def test_terminal_report_contains_required_metrics(self):
        output = format_report({"questions": 50, "recall_at_5": 0.8, "precision_at_5": 0.7, "planner_accuracy": 0.9, "structured_query_accuracy": 0.95, "grounded_responses": 1.0, "hallucination_rate": 0.0, "latency_ms": 12.5})
        self.assertIn("FORGE EVALUATION REPORT", output)
        self.assertIn("Recall@5:", output)
        self.assertIn("Hallucination Rate:", output)
        self.assertIn("Latency:", output)


if __name__ == "__main__":
    unittest.main()
