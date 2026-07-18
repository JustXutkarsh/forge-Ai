"""Run the Forge evaluation dataset and print a terminal report."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forge.analytics.schema import init_db
from eval.evaluator import evaluate_dataset, load_dataset


def format_report(report: dict) -> str:
    """Format aggregate evaluation metrics for terminal users."""
    return "\n".join([
        "====================================",
        "FORGE EVALUATION REPORT",
        "====================================",
        f"Questions: {report['questions']}",
        f"Recall@5: {report['recall_at_5']:.2%}",
        f"Precision@5: {report['precision_at_5']:.2%}",
        f"Planner Accuracy: {report['planner_accuracy']:.2%}",
        f"Structured Query Accuracy: {report['structured_query_accuracy']:.2%}",
        f"Grounded Responses: {report['grounded_responses']:.2%}",
        f"Hallucination Rate: {report['hallucination_rate']:.2%}",
        f"Latency: {report['latency_ms']:.2f} ms",
        "",
        "====================================",
    ])


def run(db: str = "data/forge.db", dataset: str = "eval/dataset.json") -> dict:
    """Run evaluation against a SQLite database."""
    conn = sqlite3.connect(db)
    try:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        return evaluate_dataset(conn, load_dataset(dataset))
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Forge retrieval and agent quality.")
    parser.add_argument("--db", default="data/forge.db")
    parser.add_argument("--dataset", default="eval/dataset.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable evaluation output.")
    args = parser.parse_args()
    result = run(args.db, args.dataset)
    print(json.dumps(result, indent=2) if args.json else format_report(result))
