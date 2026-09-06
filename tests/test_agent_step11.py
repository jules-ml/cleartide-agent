from src.agent import (
    mock_recommend_already_paid_action,
    run_aca,
)

from src.evaluation import (
    cleanup_decision,
)

from src.schemas import (
    ActionType,
    Channel,
    Intent,
)


# ============================================================
# TEST 1
# CURRENT PARTIALLY-PAID FIXTURE
# ============================================================

def test_already_paid_claim_uses_ledger_evidence():

    result = None

    try:

        result = run_aca(
            account_id=1001,
            invoice_id=5001,
            reply_text=(
                "We already paid invoice 5001."
            ),
        )

        assert (
            result[
                "intent"
            ].primary_intent
            == Intent.ALREADY_PAID_CLAIM
        )

        assert (
            result[
                "payment_evidence"
            ][
                "tool_name"
            ]
            == "reconcile_payment_claim"
        )

        assert (
            result[
                "payment_evidence"
            ][
                "status"
            ]
            == "SUCCESS"
        )

        assert (
            result[
                "payment_evidence"
            ][
                "data"
            ][
                "payment_claim_verified"
            ]
            is False
        )

        assert (
            result[
                "payment_evidence"
            ][
                "data"
            ][
                "posted_payment_total"
            ]
            < result[
                "payment_evidence"
            ][
                "data"
            ][
                "invoice_amount"
            ]
        )

        assert (
            result[
                "proposed_action"
            ].action_type
            == ActionType.SEND_MESSAGE
        )

        assert (
            result[
                "proposed_action"
            ].target_channel
            == Channel.EMAIL
        )

        tool_names = {
            result[
                "payment_evidence"
            ][
                "tool_name"
            ],

            result[
                "account_evidence"
            ][
                "tool_name"
            ],

            result[
                "risk_evidence"
            ][
                "tool_name"
            ],
        }

        assert (
            "reconcile_payment_claim"
            in tool_names
        )

        assert (
            "get_risk_score"
            in tool_names
        )

        assert (
            result[
                "final_status"
            ]
            == "APPROVED"
        )

    finally:

        if (
            result is not None
            and result.get(
                "decision_id"
            )
        ):

            cleanup_decision(
                result[
                    "decision_id"
                ]
            )


# ============================================================
# TEST 2
# VERIFIED FULL PAYMENT
# ============================================================

def test_verified_payment_causes_no_collection_action():

    state = {
        "payment_evidence": {
            "status": "SUCCESS",

            "data": {
                "invoice_amount":
                    8750.00,

                "posted_payment_total":
                    8750.00,

                "fully_paid":
                    True,

                "payment_claim_verified":
                    True,
            },
        },

        "account_evidence": {
            "status": "SUCCESS",

            "data": {
                "account": {
                    "email_allowed":
                        1
                }
            },
        },
    }

    recommendation = (
        mock_recommend_already_paid_action(
            state
        )
    )

    assert (
        recommendation.action_type
        == ActionType.NO_ACTION_MONITOR
    )

    assert (
        recommendation.target_channel
        is None
    )


# ============================================================
# TEST 3
# UNVERIFIED CLAIM + EMAIL DISALLOWED
# ============================================================

def test_unverified_payment_without_email_flags_human():

    state = {
        "payment_evidence": {
            "status": "SUCCESS",

            "data": {
                "invoice_amount":
                    8750.00,

                "posted_payment_total":
                    1000.00,

                "fully_paid":
                    False,

                "payment_claim_verified":
                    False,
            },
        },

        "account_evidence": {
            "status": "SUCCESS",

            "data": {
                "account": {
                    "email_allowed":
                        0
                }
            },
        },
    }

    recommendation = (
        mock_recommend_already_paid_action(
            state
        )
    )

    assert (
        recommendation.action_type
        == ActionType.FLAG_FOR_HUMAN_CALL
    )

    assert (
        recommendation.target_channel
        == Channel.HUMAN_CALL_FLAG
    )