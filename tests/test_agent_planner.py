import unittest
import sqlite3
from unittest.mock import patch

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

    def test_composite_claim_requires_all_conditions_before_counting(self):
        plan = plan_question("How many users requested refunds because aliens hacked their accounts?")
        self.assertEqual(plan.mode, "composite_claim")
        self.assertEqual(plan.tool_names, ["search_data"])
        refund_ticket = {
            "ticket_id": "refund-1",
            "category": "Refund Request",
            "issue_description": "Customer requested a refund",
            "resolution_notes": "Refund issued",
        }
        with patch("forge.agent.executor.search_data", return_value={"tickets": [refund_ticket], "confidence": 0.8}):
            output = _execute_plan(sqlite3.connect(":memory:"), plan)
        self.assertIn("no supporting evidence confirms aliens hacked their accounts", output["answer"])
        self.assertIn("No count is reported", output["answer"])
        self.assertNotIn("Count:", output["answer"])

    def test_comparison_retrieves_and_summarizes_each_topic(self):
        plan = plan_question("Compare login issues versus payment issues")
        self.assertEqual(plan.mode, "comparison")
        self.assertEqual(len(plan.topics), 2)
        queries = []

        def fake_search(conn, query, k):
            queries.append(query)
            return {
                "tickets": [{
                    "ticket_id": query.split()[0],
                    "category": "Login Issue" if "login" in query else "Payment Problem",
                    "issue_description": query,
                    "resolution_notes": "Resolved",
                }],
                "confidence": 0.8,
            }

        with patch("forge.agent.executor.search_data", side_effect=fake_search):
            output = _execute_plan(sqlite3.connect(":memory:"), plan)
        self.assertEqual(queries, ["login issues", "payment issues"])
        self.assertIn("Login Issues", output["answer"])
        self.assertIn("Payment Issues", output["answer"])
        self.assertEqual(len(output["source_ticket_ids"]), 2)

    def test_evidence_explanation_requires_context_and_explains_each_ticket(self):
        no_context = _execute_plan(sqlite3.connect(":memory:"), plan_question("Why was this evidence selected?"))
        self.assertEqual(
            no_context["answer"],
            "I can explain retrieved tickets, but I don't know which investigation you mean. Please specify the investigation topic.",
        )

        plan = plan_question("Why was this evidence selected for login issues?")
        context = {
            "retrieval_strategy": "semantic",
            "evidence": [{
                "ticket_id": "login-1",
                "score": 0.91,
                "summary": "Password reset restored access",
            }],
        }
        output = _execute_plan(sqlite3.connect(":memory:"), plan, context)
        self.assertIn("Ticket login-1", output["answer"])
        self.assertIn("selected by semantic retrieval", output["answer"])
        self.assertIn("similarity score: 0.910", output["answer"])

    def test_follow_up_ticket_explanation_is_classified_as_evidence_context(self):
        plan = plan_question("List the ticket IDs and explain why each one was selected.")
        self.assertEqual(plan.mode, "evidence_explanation")


if __name__ == "__main__":
    unittest.main()
