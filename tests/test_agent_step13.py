from src.agent import (
    mock_classify_reply,
    run_aca,
)

from src.schemas import (
    ActionType,
    Intent,
    ValidatorOutcome,
)


def test_promise_to_pay_classification():
    """
    A clear future payment commitment should classify
    as PROMISE_TO_PAY.
    """

    classification = mock_classify_reply(
        "We will pay on Friday."
    )

    assert (
        classification.primary_intent
        == Intent.PROMISE_TO_PAY
    )

    assert classification.confidence >= 0.75


def test_promise_to_pay_with_prior_broken_promise():
    """
    The ACA must retrieve prior promise memory and trusted
    risk before deciding what to do with a new promise.

    The development fixture contains a prior BROKEN promise,
    so the agent should flag the account for human follow-up.
    """

    result = run_aca(
        1001,
        5001,
        "We will pay on Friday.",
    )

    # --------------------------------------------------------
    # INTENT
    # --------------------------------------------------------

    assert (
        result["intent"].primary_intent
        == Intent.PROMISE_TO_PAY
    )

    # --------------------------------------------------------
    # REQUIRED MEMORY
    # --------------------------------------------------------

    promise_evidence = result[
        "prior_promises_evidence"
    ]

    assert (
        promise_evidence["status"]
        == "SUCCESS"
    )

    promises = promise_evidence[
        "data"
    ][
        "promises"
    ]

    assert len(promises) >= 1

    assert any(
        str(
            promise.get(
                "status",
                "",
            )
        ).upper()
        == "BROKEN"

        for promise in promises
    )

    # --------------------------------------------------------
    # ACCOUNT + RISK EVIDENCE
    # --------------------------------------------------------

    assert (
        result[
            "account_evidence"
        ][
            "status"
        ]
        == "SUCCESS"
    )

    assert (
        result[
            "risk_evidence"
        ][
            "status"
        ]
        == "SUCCESS"
    )

    assert (
        result[
            "risk"
        ].band.value
        == "MEDIUM"
    )

    # --------------------------------------------------------
    # AGENT RECOMMENDATION
    # --------------------------------------------------------

    assert (
        result[
            "proposed_action"
        ].action_type
        == ActionType.FLAG_FOR_HUMAN_CALL
    )

    # --------------------------------------------------------
    # DETERMINISTIC VALIDATOR
    # --------------------------------------------------------

    assert (
        result[
            "validation"
        ].outcome
        == ValidatorOutcome.APPROVED
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    assert (
        result[
            "final_status"
        ]
        == "APPROVED"
    )

    assert (
        result[
            "final_action_type"
        ]
        == ActionType.FLAG_FOR_HUMAN_CALL
    )