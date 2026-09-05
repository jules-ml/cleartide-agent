import json

from dataclasses import dataclass, field
from typing import Callable

from src.policy import load_policy
from src.tools import (
    record_blocked_tool_call,
    record_tool_error,
)


@dataclass
class ToolGuardState:
    """
    Deterministic per-decision tool usage state.
    """

    decision_id: int

    total_calls: int = 0

    signature_counts: dict[str, int] = field(
        default_factory=dict
    )


def make_tool_signature(
    tool_name: str,
    arguments: dict,
) -> str:
    """
    Produce a deterministic signature for:

        tool name + exact arguments

    Example:

        get_risk_score:
        {"account_id":1001,"invoice_id":5001}
    """

    normalized_arguments = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return (
        f"{tool_name}:"
        f"{normalized_arguments}"
    )


def execute_guarded_tool(
    guard: ToolGuardState,
    tool_name: str,
    arguments: dict,
    tool_function: Callable,
):
    """
    Execute one evidence tool subject to deterministic
    per-decision usage limits.

    Returns:

        result, violation_reason

    violation_reason is None when execution is allowed.
    """

    policy = load_policy()

    max_total_calls = int(
        policy["agent"][
            "max_tool_calls_per_decision"
        ]
    )

    max_identical_calls = int(
        policy["agent"][
            "max_identical_tool_calls"
        ]
    )

    signature = make_tool_signature(
        tool_name,
        arguments,
    )

    identical_count = (
        guard.signature_counts.get(
            signature,
            0,
        )
    )

    # ========================================================
    # FR-2.5
    # TOTAL TOOL LIMIT
    # ========================================================

    if (
        guard.total_calls
        >= max_total_calls
    ):

        reason = (
            "FR-2.5: maximum tool calls per "
            f"decision ({max_total_calls}) "
            "would be exceeded."
        )

        result = record_blocked_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            decision_id=guard.decision_id,
        )

        return result, reason

    # ========================================================
    # FR-2.6
    # IDENTICAL TOOL + ARGUMENT LIMIT
    # ========================================================

    if (
        identical_count
        >= max_identical_calls
    ):

        reason = (
            "FR-2.6: identical tool call "
            f"{tool_name} with the same "
            f"arguments has already occurred "
            f"{max_identical_calls} times."
        )

        result = record_blocked_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            decision_id=guard.decision_id,
        )

        return result, reason

    # ========================================================
    # EXECUTION
    # ========================================================

    try:

        result = tool_function(
            decision_id=guard.decision_id,
            **arguments,
        )

    except Exception as exc:

        # An actual execution attempt occurred.
        guard.total_calls += 1

        guard.signature_counts[
            signature
        ] = identical_count + 1

        error_message = (
            f"{type(exc).__name__}: {exc}"
        )

        result = record_tool_error(
            tool_name=tool_name,
            arguments=arguments,
            error_message=error_message,
            decision_id=guard.decision_id,
        )

        reason = (
            "FR-2.7: required tool "
            f"{tool_name} raised an error."
        )

        return result, reason

    # ========================================================
    # SUCCESSFUL ATTEMPT COUNTING
    # ========================================================

    guard.total_calls += 1

    guard.signature_counts[
        signature
    ] = identical_count + 1

    return result, None