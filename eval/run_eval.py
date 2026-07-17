import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forge.analytics.queries import query_structured
from forge.analytics.schema import init_db


def run(db: str, cases_path: str) -> dict:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    passed = 0
    details = []
    for case in cases:
        result = query_structured(conn, case["operation"], case["field"], case.get("filters"), tuple(case["date_range"]) if case.get("date_range") else None)
        actual = result.get("count") if case["operation"] == "count" else (result.get("results") or [None])[0]
        expected = case.get("expected_count", case.get("expected_first"))
        ok = actual == expected
        passed += ok
        details.append({"case": case, "actual": actual, "passed": ok})
    conn.close()
    return {"structured_exact_match": passed / len(cases) if cases else 0, "passed": passed, "total": len(cases), "details": details}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/forge.db")
    parser.add_argument("--cases", default="eval/structured_eval_set.json")
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.cases), indent=2))
