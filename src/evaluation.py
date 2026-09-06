import json
from datetime import datetime, timezone
from pathlib import Path

from src.agent import (
    DEVELOPMENT_REASONING_MODE,
    run_aca,
)
from src.database import get_connection


# ============================================================
# PATHS
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

GOLDEN_CASES_PATH = (
    ROOT_DIR
    / "evals"
    / "golden_cases.json"
)

LATEST_RESULTS_PATH = (
    ROOT_DIR
    / "evals"
    / "latest_results.json"
)


# ============================================================
# GOLDEN CASE LOADING
# ============================================================

def load_golden_cases(
    active_only: bool = True,
) -> list[dict]:
    """
    Load development golden cases.

    active_only=True:
        evaluate only currently implemented regression cases.

    active_only=False:
        load the entire future-facing seed set.
    """

    with open(
        GOLDEN_CASES_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        cases = json.load(
            file
        )

    if active_only:

        cases = [
            case
            for case in cases
            if case.get(
                "active",
                False,
            )
        ]

    return cases


# ============================================================
# TOOL TRAJECTORY RETRIEVAL
# ============================================================

def get_tool_trajectory(
    decision_id: int,
) -> list[dict]:
    """
    Return every persisted tool call for one decision.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            tool_call_id,
            decision_id,
            tool_name,
            arguments_json,
            result_json,
            status,
            created_at

        FROM tool_calls

        WHERE decision_id = ?

        ORDER BY tool_call_id
        """,
        (decision_id,),
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# CLEANUP FOR AUTOMATED TESTS
# ============================================================

def cleanup_decision(
    decision_id: int,
):
    """
    Delete evaluation audit records when a regression test
    explicitly requests cleanup.

    Manual evaluation runs are normally preserved.
    """

    conn = get_connection()

    conn.execute(
        """
        DELETE FROM escalations
        WHERE decision_id = ?
        """,
        (decision_id,),
    )

    conn.execute(
        """
        DELETE FROM tool_calls
        WHERE decision_id = ?
        """,
        (decision_id,),
    )

    conn.execute(
        """
        DELETE FROM agent_actions
        WHERE decision_id = ?
        """,
        (decision_id,),
    )

    conn.commit()
    conn.close()


# ============================================================
# SINGLE CASE EVALUATION
# ============================================================

def evaluate_case(
    case: dict,
    cleanup: bool = False,
) -> dict:
    """
    Execute and score one golden case.

    Scores:
        intent correctness
        final-status correctness
        action correctness
        required-tool compliance
        unexpected-tool use
        minimum sufficient tool count
        hard-policy safety
    """

    result = None

    try:

        result = run_aca(
            account_id=case[
                "account_id"
            ],

            invoice_id=case[
                "invoice_id"
            ],

            reply_text=case[
                "reply_text"
            ],
        )

        decision_id = result[
            "decision_id"
        ]

        trajectory = (
            get_tool_trajectory(
                decision_id
            )
        )

        actual_tools = [
            row["tool_name"]
            for row in trajectory
            if row["status"]
            != "BLOCKED_BY_GUARD"
        ]

        expected_intent = (
            case.get(
                "expected_intent"
            )
        )

        expected_status = (
            case.get(
                "expected_final_status"
            )
        )

        expected_action = (
            case.get(
                "expected_final_action"
            )
        )

        required_tools = (
            case.get(
                "required_tools"
            )
            or []
        )

        allowed_tools = case.get(
            "allowed_tools"
        )

        actual_intent = (
            result[
                "intent"
            ].primary_intent.value
        )

        actual_status = result[
            "final_status"
        ]

        actual_action = (
            result[
                "final_action_type"
            ].value
        )

        # ====================================================
        # DECISION CORRECTNESS
        # ====================================================

        intent_correct = (
            expected_intent is None
            or actual_intent
            == expected_intent
        )

        status_correct = (
            expected_status is None
            or actual_status
            == expected_status
        )

        action_correct = (
            expected_action is None
            or actual_action
            == expected_action
        )

        # ====================================================
        # REQUIRED TOOL COMPLIANCE
        # ====================================================

        required_tools_met = all(
            tool_name
            in actual_tools
            for tool_name
            in required_tools
        )

        missing_required_tools = [
            tool_name
            for tool_name
            in required_tools
            if tool_name
            not in actual_tools
        ]

        # ====================================================
        # TOOL PRECISION
        # ====================================================

        if allowed_tools is None:

            unexpected_tools = []

            no_unexpected_tools = True

        else:

            unexpected_tools = [
                tool_name
                for tool_name in actual_tools
                if tool_name
                not in allowed_tools
            ]

            no_unexpected_tools = (
                len(
                    unexpected_tools
                )
                == 0
            )

        # ====================================================
        # MINIMUM SUFFICIENT TRAJECTORY
        # ====================================================

        minimum_tool_count = len(
            required_tools
        )

        minimum_sufficient = (
            len(actual_tools)
            == minimum_tool_count
            if allowed_tools
            == required_tools
            else len(actual_tools)
            >= minimum_tool_count
        )

        # ====================================================
        # POLICY SAFETY
        #
        # An APPROVED final action must have an APPROVED
        # validator outcome with zero violated constraints.
        # ====================================================

        validation = result.get(
            "validation"
        )

        if (
            actual_status
            == "APPROVED"
        ):

            policy_safe = (
                validation is not None
                and validation.outcome.value
                == "APPROVED"
                and len(
                    validation.violated_constraints
                )
                == 0
            )

        else:

            policy_safe = True

        # ====================================================
        # COMPLETE CASE PASS
        # ====================================================

        passed = all(
            [
                intent_correct,
                status_correct,
                action_correct,
                required_tools_met,
                no_unexpected_tools,
                minimum_sufficient,
                policy_safe,
            ]
        )

        return {
            "case_id":
                case["case_id"],

            "decision_id":
                decision_id,

            "label_status":
                case.get(
                    "label_status"
                ),

            "human_reviewed":
                case.get(
                    "human_reviewed",
                    False,
                ),

            "expected_intent":
                expected_intent,

            "actual_intent":
                actual_intent,

            "intent_correct":
                intent_correct,

            "expected_final_status":
                expected_status,

            "actual_final_status":
                actual_status,

            "status_correct":
                status_correct,

            "expected_final_action":
                expected_action,

            "actual_final_action":
                actual_action,

            "action_correct":
                action_correct,

            "required_tools":
                required_tools,

            "actual_tools":
                actual_tools,

            "missing_required_tools":
                missing_required_tools,

            "required_tools_met":
                required_tools_met,

            "unexpected_tools":
                unexpected_tools,

            "no_unexpected_tools":
                no_unexpected_tools,

            "minimum_tool_count":
                minimum_tool_count,

            "actual_tool_count":
                len(
                    actual_tools
                ),

            "minimum_sufficient":
                minimum_sufficient,

            "policy_safe":
                policy_safe,

            "passed":
                passed,
        }

    finally:

        if (
            cleanup
            and result is not None
            and result.get(
                "decision_id"
            )
            is not None
        ):

            cleanup_decision(
                result[
                    "decision_id"
                ]
            )


# ============================================================
# SUITE EVALUATION
# ============================================================

def evaluate_suite(
    cases: list[dict],
    cleanup: bool = False,
):
    """
    Evaluate a collection of golden cases.
    """

    results = [
        evaluate_case(
            case,
            cleanup=cleanup,
        )
        for case in cases
    ]

    summary = summarize_results(
        results
    )

    return (
        results,
        summary,
    )


# ============================================================
# SUMMARY METRICS
# ============================================================

def summarize_results(
    results: list[dict],
) -> dict:
    """
    Produce current Tier 1-3 starter metrics.
    """

    total = len(
        results
    )

    if total == 0:

        return {
            "total_cases": 0,
        }

    intent_accuracy = (
        sum(
            1
            for result in results
            if result[
                "intent_correct"
            ]
        )
        / total
    )

    # --------------------------------------------------------
    # Only calculate action accuracy where an action label
    # actually exists.
    # --------------------------------------------------------

    action_labeled = [
        result
        for result in results
        if result[
            "expected_final_action"
        ]
        is not None
    ]

    if action_labeled:

        action_accuracy = (
            sum(
                1
                for result
                in action_labeled
                if result[
                    "action_correct"
                ]
            )
            / len(
                action_labeled
            )
        )

    else:

        action_accuracy = None

    # --------------------------------------------------------
    # Status accuracy
    # --------------------------------------------------------

    status_labeled = [
        result
        for result in results
        if result[
            "expected_final_status"
        ]
        is not None
    ]

    if status_labeled:

        status_accuracy = (
            sum(
                1
                for result
                in status_labeled
                if result[
                    "status_correct"
                ]
            )
            / len(
                status_labeled
            )
        )

    else:

        status_accuracy = None

    required_tool_compliance = (
        sum(
            1
            for result in results
            if result[
                "required_tools_met"
            ]
        )
        / total
    )

    tool_precision_rate = (
        sum(
            1
            for result in results
            if result[
                "no_unexpected_tools"
            ]
        )
        / total
    )

    minimum_sufficient_rate = (
        sum(
            1
            for result in results
            if result[
                "minimum_sufficient"
            ]
        )
        / total
    )

    policy_safety_rate = (
        sum(
            1
            for result in results
            if result[
                "policy_safe"
            ]
        )
        / total
    )

    hard_policy_violations = sum(
        1
        for result in results
        if not result[
            "policy_safe"
        ]
    )

    overall_pass_rate = (
        sum(
            1
            for result in results
            if result[
                "passed"
            ]
        )
        / total
    )

    return {
        "total_cases":
            total,

        "intent_accuracy":
            intent_accuracy,

        "action_accuracy":
            action_accuracy,

        "status_accuracy":
            status_accuracy,

        "required_tool_compliance":
            required_tool_compliance,

        "tool_precision_rate":
            tool_precision_rate,

        "minimum_sufficient_rate":
            minimum_sufficient_rate,

        "policy_safety_rate":
            policy_safety_rate,

        "hard_policy_violations":
            hard_policy_violations,

        "overall_pass_rate":
            overall_pass_rate,
    }


# ============================================================
# WRITE RESULTS
# ============================================================

def write_results(
    results: list[dict],
    summary: dict,
    path: Path = LATEST_RESULTS_PATH,
):
    """
    Write a machine-readable development evaluation report.
    """

    payload = {
        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "reasoning_mode":
            DEVELOPMENT_REASONING_MODE,

        "summary":
            summary,

        "results":
            results,
    }

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            indent=2,
        )

    return path