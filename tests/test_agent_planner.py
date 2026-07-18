import unittest
import sqlite3

from forge.agent.executor import _execute_plan
from forge.agent.planner import plan_question
from forge.analytics.schema import init_db


class PlannerRoutingTests(unittest.TestCase):
    def test_top_complaint_categories_uses_structured_group_by(self):
        plan = plan_question("What are the top complaint categories?")
        self.assertEqual(plan.tool_names, ["query_structured"])
        self.assertEqual(plan.steps[0].arguments["operation"], "group_by")
        self.assertEqual(plan.steps[0].arguments["field"], "category")

    def test_top_labels_uses_sql(self):
        self.assertEqual(plan_question("top 5 labels").tool_names, ["query_structured"])

    def test_top_authentication_issues_uses_rag(self):
        self.assertEqual(plan_question("top 5 authentication issues").tool_names, ["search_data"])

    def test_top_login_problems_uses_rag(self):
        self.assertEqual(plan_question("top 5 login problems").tool_names, ["search_data"])

    def test_structured_plan_has_confidence(self):
        conn = sqlite3.connect(":memory:")
        init_db(conn)
        try:
            output = _execute_plan(conn, plan_question("top 5 labels"))
            self.assertGreater(output["confidence"], 0.0)
        finally:
            conn.close()

    def test_payment_issue_count_uses_category_filter(self):
        plan = plan_question("How many payment issues occurred?")
        self.assertEqual(plan.tool_names, ["query_structured"])
        self.assertEqual(plan.steps[0].arguments["filters"], {"category": "Payment Problem"})

    def test_login_summary_requires_retrieval_then_summary(self):
        plan = plan_question("Summarize login issues.")
        self.assertEqual(plan.tool_names, ["search_data", "summarize"])
        self.assertEqual(plan.steps[1].depends_on, (0,))

    def test_weekly_report_is_multi_step(self):
        plan = plan_question("Generate weekly report")
        self.assertEqual(plan.tool_names, ["query_structured", "search_data", "summarize", "draft_report"])
        self.assertEqual(plan.steps[3].depends_on, (0, 2))

    def test_unsupported_question_still_requires_evidence_search(self):
        plan = plan_question("Who is the CEO?")
        self.assertEqual(plan.tool_names, ["search_data"])


if __name__ == "__main__":
    unittest.main()
