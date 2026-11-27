"""Run the class scenarios and shape the dashboard payload."""

from datetime import datetime

from src.agent import run_aca
from src.policy import load_policy

from demo.fixtures import CLASS_SCENARIOS
from demo.present import present_decision


def run_scenario(scenario: dict) -> dict:
    send_time = scenario.get("proposed_send_time")
    if isinstance(send_time, str):
        send_time = datetime.fromisoformat(send_time)
    result = run_aca(
        account_id=scenario["account_id"],
        invoice_id=scenario["invoice_id"],
        reply_text=scenario["reply_text"],
        proposed_send_time=send_time,
        injected_message_body=scenario.get("injected_message_body"),
    )
    view = present_decision(scenario, result)
    view["policy_card"] = policy_card(view.get("violated_constraints") or [])
    return view


def run_class_scenarios() -> list[dict]:
    return [run_scenario(scenario) for scenario in CLASS_SCENARIOS]


def scenario_by_id(scenario_id: str) -> dict:
    for scenario in CLASS_SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    raise KeyError(scenario_id)


def policy_card(constraints: list[str]) -> dict | None:
    """Quote the external policy that the fired rule reads."""

    if not constraints:
        policy = load_policy()
        return {
            "constraint": None,
            "source_file": "config/policy.yaml",
            "enforced_by": "src/policy.py",
            "policy_version": policy["policy_version"],
            "statement": (
                "No hard constraint fired. "
                "validate_action returned APPROVED for policy version "
                f"{policy['policy_version']}."
            ),
            "excerpt": {
                "policy_version": policy["policy_version"],
                "agent.autonomous_action_enabled": policy["agent"][
                    "autonomous_action_enabled"
                ],
            },
        }

    policy = load_policy()
    constraint = constraints[0]
    excerpt = {"policy_version": policy["policy_version"]}
    statement = "See config/policy.yaml."

    if constraint == "PR-3":
        excerpt["hard_constraints.unauthorized_consequence_language_allowed"] = (
            policy["hard_constraints"]["unauthorized_consequence_language_allowed"]
        )
        excerpt["truthfulness.unauthorized_consequence_terms"] = policy[
            "truthfulness"
        ]["unauthorized_consequence_terms"]
        statement = (
            "PR-3 is enforced in src/policy.py. "
            "Customer-facing consequence language is blocked when "
            "hard_constraints.unauthorized_consequence_language_allowed is false. "
            "The term list lives in config/policy.yaml under truthfulness."
        )
    elif constraint == "PR-5.2":
        excerpt["payment_plans"] = policy["payment_plans"]
        statement = (
            "PR-5.2 is enforced in src/policy.py. "
            "A proposed payment plan is escalated when payment_plans.<band>"
            ".autonomous_allowed is false. The band limits live in "
            "config/policy.yaml, not in the recommender."
        )
    elif constraint == "PR-4.1":
        excerpt["contact.sms_requires_affirmative_consent"] = policy["contact"][
            "sms_requires_affirmative_consent"
        ]
        excerpt["hard_constraints.sms_without_consent_allowed"] = policy[
            "hard_constraints"
        ]["sms_without_consent_allowed"]
        statement = (
            "PR-4.1 is enforced in src/policy.py. "
            "SMS is rejected unless the account record has affirmative consent. "
            "The switch is contact.sms_requires_affirmative_consent in "
            "config/policy.yaml. One safe revision to email is allowed."
        )
    elif constraint == "PR-4.3":
        excerpt["contact.honor_channel_opt_out"] = policy["contact"][
            "honor_channel_opt_out"
        ]
        excerpt["contact.opt_out_requires_escalation"] = policy["contact"][
            "opt_out_requires_escalation"
        ]
        statement = (
            "PR-4.3 is enforced in src/policy.py. "
            "A stored channel opt-out escalates instead of sending."
        )
    elif constraint == "PR-2.1":
        excerpt["contact.consumer_quiet_hours"] = policy["contact"][
            "consumer_quiet_hours"
        ]
        statement = (
            "PR-2.1 is enforced in src/policy.py using the quiet-hour window "
            "in config/policy.yaml. Email is exempt."
        )

    return {
        "constraint": constraint,
        "source_file": "config/policy.yaml",
        "enforced_by": "src/policy.py",
        "policy_version": policy["policy_version"],
        "statement": statement,
        "excerpt": excerpt,
    }
