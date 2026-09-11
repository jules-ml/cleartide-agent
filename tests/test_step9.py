from datetime import datetime, timedelta, timezone

from src.agent import (
    revise_action_node,
    validate_proposal_node,
    route_after_validation,
    run_aca,
)

from src.audit import (
    get_decision_record,
    get_escalation_packet,
    start_decision,
)

from src.database import (
    get_connection,
)

from src.policy import (
    load_policy,
)

from src.schemas import (
    ActionType,
    Channel,
    DebtClassification,
    Intent,
    IntentClassification,
    PolicyValidationResult,
    ProposedAction,
    RiskBand,
    ValidatorOutcome,
)

from src.tool_guard import (
    ToolGuardState,
    execute_guarded_tool,
)

from src.tools import (
    get_account_history,
)


# ============================================================
# HELPERS
# ============================================================

def cleanup_test_decision(
    decision_id,
):
    """
    Remove audit rows created only by guard unit tests.
    """

    conn = get_connection()

    conn.execute(
        """
        DELETE FROM tool_calls
        WHERE decision_id = ?
        """,
        (decision_id,),
    )

    conn.execute(
        """
        DELETE FROM escalations
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
# TEST 1
# DECISION RECORD + TOOL LINKAGE
# ============================================================

def test_decision_and_tool_calls_are_linked():

    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text=(
            "We never received invoice 5001. "
            "Can you send it again?"
        ),
    )

    decision_id = result[
        "decision_id"
    ]

    record = get_decision_record(
        decision_id
    )

    assert record is not None

    assert (
        record[
            "audit_status"
        ]
        == "COMPLETED"
    )

    assert (
        record[
            "final_action"
        ]
        == "RESEND_INVOICE"
    )

    assert (
        record[
            "reasoning_mode"
        ]
        == "DETERMINISTIC_MOCK"
    )

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM tool_calls
        WHERE decision_id = ?
        """,
        (decision_id,),
    ).fetchall()

    conn.close()

    assert len(rows) == 3

    assert all(
        row[
            "decision_id"
        ]
        == decision_id
        for row in rows
    )


# ============================================================
# TEST 2
# ESCALATION PACKET PERSISTENCE
# ============================================================

def test_unsupported_intent_creates_escalation_packet():

    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text=(
            "Can we split the balance "
            "into four monthly payments?"
        ),
    )

    assert (
        result[
            "final_status"
        ]
        == "ESCALATE"
    )

    escalation_id = result.get(
        "escalation_id"
    )

    assert escalation_id is not None

    packet = get_escalation_packet(
        escalation_id
    )

    assert packet is not None

    assert (
        packet[
            "decision_id"
        ]
        == result[
            "decision_id"
        ]
    )

    assert (
        packet[
            "primary_intent"
        ]
        == "PAYMENT_PLAN_REQUEST"
    )

    assert (
        "account_history"
        in packet
    )


# ============================================================
# TEST 3
# THIRD IDENTICAL TOOL CALL BLOCKED
# ============================================================

def test_duplicate_tool_guard_blocks_third_call():

    decision_id = start_decision(
        account_id=1001,
        invoice_id=5001,
        reply_text="guard test",
        reasoning_mode="TEST",
    )

    try:

        guard = ToolGuardState(
            decision_id=decision_id
        )

        result_1, violation_1 = (
            execute_guarded_tool(
                guard=guard,
                tool_name="get_account_history",
                arguments={
                    "account_id": 1001
                },
                tool_function=(
                    get_account_history
                ),
            )
        )

        result_2, violation_2 = (
            execute_guarded_tool(
                guard=guard,
                tool_name="get_account_history",
                arguments={
                    "account_id": 1001
                },
                tool_function=(
                    get_account_history
                ),
            )
        )

        result_3, violation_3 = (
            execute_guarded_tool(
                guard=guard,
                tool_name="get_account_history",
                arguments={
                    "account_id": 1001
                },
                tool_function=(
                    get_account_history
                ),
            )
        )

        assert (
            result_1[
                "status"
            ]
            == "SUCCESS"
        )

        assert violation_1 is None

        assert (
            result_2[
                "status"
            ]
            == "SUCCESS"
        )

        assert violation_2 is None

        assert (
            result_3[
                "status"
            ]
            == "BLOCKED_BY_GUARD"
        )

        assert (
            "FR-2.6"
            in violation_3
        )

    finally:

        cleanup_test_decision(
            decision_id
        )


# ============================================================
# TEST 4
# TOTAL TOOL LIMIT
# ============================================================

def test_total_tool_limit_blocks_next_call():

    decision_id = start_decision(
        account_id=1001,
        invoice_id=5001,
        reply_text="total guard test",
        reasoning_mode="TEST",
    )

    try:

        policy = load_policy()

        max_calls = int(
            policy[
                "agent"
            ][
                "max_tool_calls_per_decision"
            ]
        )

        guard = ToolGuardState(
            decision_id=decision_id,
            total_calls=max_calls,
        )

        result, violation = (
            execute_guarded_tool(
                guard=guard,
                tool_name="get_account_history",
                arguments={
                    "account_id": 1001
                },
                tool_function=(
                    get_account_history
                ),
            )
        )

        assert (
            result[
                "status"
            ]
            == "BLOCKED_BY_GUARD"
        )

        assert (
            "FR-2.5"
            in violation
        )

    finally:

        cleanup_test_decision(
            decision_id
        )


# ============================================================
# TEST 5
# SAFE SINGLE REVISION
# ============================================================

def test_sms_rejection_can_be_revised_to_email():

    proposal = ProposedAction(
        action_type=(
            ActionType.SEND_MESSAGE
        ),

        target_channel=(
            Channel.SMS
        ),

        message_body=(
            "Test message"
        ),

        rationale=(
            "Test rationale"
        ),

        tool_call_ids=[
            "TC-TEST"
        ],

        risk_score=0.20,

        risk_band=(
            RiskBand.LOW
        ),

        policy_version=(
            "0.1-dev"
        ),
    )

    validation = (
        PolicyValidationResult(
            outcome=(
                ValidatorOutcome.REJECTED
            ),

            violated_constraints=[
                "PR-4.1"
            ],

            explanation=(
                "SMS consent missing."
            ),
        )
    )

    state = {
        "proposed_action":
            proposal,

        "validation":
            validation,

        "revision_count":
            0,

        "account_evidence":
            {
                "data":
                    {
                        "account":
                            {
                                "email_allowed":
                                    1
                            }
                    }
            },
    }

    update = revise_action_node(
        state
    )

    assert (
        update[
            "revision_count"
        ]
        == 1
    )

    assert (
        update[
            "proposed_action"
        ].target_channel
        == Channel.EMAIL
    )


def test_quiet_hours_sms_rejection_can_be_revised_to_email():

    proposal = ProposedAction(
        action_type=(
            ActionType.SEND_MESSAGE
        ),

        target_channel=(
            Channel.SMS
        ),

        message_body=(
            "Test message"
        ),

        rationale=(
            "Test rationale"
        ),

        tool_call_ids=[
            "TC-TEST"
        ],

        risk_score=0.20,

        risk_band=(
            RiskBand.LOW
        ),

        policy_version=(
            "0.1-dev"
        ),
    )

    validation = (
        PolicyValidationResult(
            outcome=(
                ValidatorOutcome.REJECTED
            ),

            violated_constraints=[
                "PR-2.1"
            ],

            explanation=(
                "Consumer SMS falls within quiet hours."
            ),
        )
    )

    state = {
        "proposed_action":
            proposal,

        "validation":
            validation,

        "revision_count":
            0,

        "account_evidence":
            {
                "data":
                    {
                        "account":
                            {
                                "email_allowed":
                                    1
                            }
                    }
            },
    }

    update = revise_action_node(
        state
    )

    assert (
        update[
            "revision_count"
        ]
        == 1
    )

    assert (
        update[
            "proposed_action"
        ].target_channel
        == Channel.EMAIL
    )


# ============================================================
# TEST 6
# REVISION LIMIT ENFORCED
# ============================================================

def test_rejected_action_cannot_exceed_revision_limit():

    validation = (
        PolicyValidationResult(
            outcome=(
                ValidatorOutcome.REJECTED
            ),

            violated_constraints=[
                "PR-4.1"
            ],

            explanation=(
                "Rejected."
            ),
        )
    )

    state_before_revision = {
        "validation":
            validation,

        "revision_count":
            0,
    }

    assert (
        route_after_validation(
            state_before_revision
        )
        == "revise"
    )

    state_after_revision = {
        "validation":
            validation,

        "revision_count":
            1,
    }

    assert (
        route_after_validation(
            state_after_revision
        )
        == "escalation"
    )

# ============================================================
# STEP 21
# PR-2.4 proposed send-time context reaches policy validation.
# ============================================================

def test_validator_node_forwards_proposed_send_time():
    proposal = ProposedAction(
        action_type=ActionType.SEND_MESSAGE,
        target_channel=Channel.SMS,
        rationale="Test quiet-hours forwarding.",
        tool_call_ids=["TC-TEST"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )

    state = {
        "invoice_id": 5001,
        "reply_text": "I'll pay Friday.",
        "intent": IntentClassification(
            primary_intent=Intent.PROMISE_TO_PAY,
            confidence=0.95,
        ),
        "debt_classification": DebtClassification.CONSUMER,
        "proposed_action": proposal,
        "proposed_send_time": datetime(
            2026,
            9,
            11,
            21,
            0,
            tzinfo=timezone(timedelta(hours=-4)),
        ),
        "account_evidence": {
            "data": {
                "account": {
                    "sms_consent": 1,
                },
                "invoices": [
                    {
                        "invoice_id": 5001,
                        "amount": 100.0,
                    }
                ],
            }
        },
    }

    update = validate_proposal_node(state)

    assert update["validation"].outcome == ValidatorOutcome.REJECTED
    assert "PR-2.1" in update["validation"].violated_constraints
