from demo.synthetic_cases import build_synthetic_cases
from src.synthetic_eval import summarize_synthetic


REQUIRED_INTENTS = {
    "DELIVERY_DISPUTE",
    "PAYMENT_PLAN_REQUEST",
    "ALREADY_PAID_CLAIM",
    "PROMISE_TO_PAY",
    "AMOUNT_DISPUTE",
    "HOSTILE_OR_ADVERSARIAL",
    "UNCLEAR",
}


def test_synthetic_set_covers_the_intent_taxonomy():
    cases = build_synthetic_cases()
    assert len(cases) >= 100
    assert {case["expected_intent"] for case in cases} == REQUIRED_INTENTS
    assert len({case["case_id"] for case in cases}) == len(cases)


def test_synthetic_summary_counts_a_policy_violation():
    summary = summarize_synthetic(
        [
            {
                "archetype": "ok",
                "decision_correct": True,
                "intent_correct": True,
                "action_correct": True,
                "status_correct": True,
                "expected_escalated": False,
                "actual_escalated": False,
                "escalation_correct": True,
                "policy_violation": False,
                "channel_expected": "EMAIL",
                "channel_correct": True,
                "expected_failure_handling": False,
                "failure_handled": True,
            },
            {
                "archetype": "blocked",
                "decision_correct": False,
                "intent_correct": True,
                "action_correct": False,
                "status_correct": False,
                "expected_escalated": True,
                "actual_escalated": False,
                "escalation_correct": False,
                "policy_violation": True,
                "channel_expected": None,
                "channel_correct": True,
                "expected_failure_handling": True,
                "failure_handled": False,
            },
        ]
    )
    assert summary["total_cases"] == 2
    assert summary["policy_violation_rate"] == 0.5
    assert summary["policy_violation_count"] == 1
