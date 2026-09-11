from datetime import datetime, timedelta, timezone

from src.policy import validate_action
from src.schemas import (
    ActionType,
    Channel,
    DebtClassification,
    Intent,
    ProposedAction,
    RiskBand,
    ValidatorOutcome,
)


def make_low_risk_plan(
    duration_days=30,
    down_payment_pct=0.25,
):
    return ProposedAction(
        action_type=ActionType.PROPOSE_PAYMENT_PLAN,
        target_channel=Channel.EMAIL,
        payment_plan_duration_days=duration_days,
        payment_plan_down_payment_pct=down_payment_pct,
        rationale="Customer requested a payment arrangement.",
        tool_call_ids=["TC-001", "TC-002"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )


# ============================================================
# FR-5.6
# Validator works independently of the agent.
# ============================================================

def test_valid_low_risk_payment_plan_is_approved():
    proposal = make_low_risk_plan()

    result = validate_action(
        proposal,
        primary_intent=Intent.PAYMENT_PLAN_REQUEST,
        intent_confidence=0.95,
        reply_text="Can we split this into two payments?",
    )

    assert result.outcome == ValidatorOutcome.APPROVED


# ============================================================
# PR-5.2
# Excessive payment-plan duration must be rejected.
# ============================================================

def test_payment_plan_too_long_is_rejected():
    proposal = make_low_risk_plan(
        duration_days=90,
        down_payment_pct=0.25,
    )

    result = validate_action(
        proposal,
        primary_intent=Intent.PAYMENT_PLAN_REQUEST,
        intent_confidence=0.95,
        reply_text="Can I have 90 days to pay this?",
    )

    assert result.outcome == ValidatorOutcome.REJECTED
    assert "PR-5.2" in result.violated_constraints


# ============================================================
# FR-1.3
# Low-confidence classification must escalate.
# ============================================================

def test_low_confidence_escalates():
    proposal = make_low_risk_plan()

    result = validate_action(
        proposal,
        primary_intent=Intent.PAYMENT_PLAN_REQUEST,
        intent_confidence=0.50,
        reply_text="I don't know, maybe we can work something out.",
    )

    assert result.outcome == ValidatorOutcome.ESCALATE
    assert "FR-1.3" in result.violated_constraints


# ============================================================
# FR-1.5
# UNCLEAR always escalates.
# ============================================================

def test_unclear_intent_escalates():
    proposal = make_low_risk_plan()

    result = validate_action(
        proposal,
        primary_intent=Intent.UNCLEAR,
        intent_confidence=0.95,
        reply_text="What?",
    )

    assert result.outcome == ValidatorOutcome.ESCALATE
    assert "FR-1.5" in result.violated_constraints


# ============================================================
# PR-4.1
# SMS without affirmative consent must not proceed.
# ============================================================

def test_sms_without_consent_is_rejected():
    proposal = ProposedAction(
        action_type=ActionType.SEND_MESSAGE,
        target_channel=Channel.SMS,
        rationale="Send customer a reminder.",
        tool_call_ids=["TC-001"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )

    result = validate_action(
        proposal,
        primary_intent=Intent.PROMISE_TO_PAY,
        intent_confidence=0.90,
        reply_text="I'll send the payment Friday.",
        sms_consent=False,
    )

    assert result.outcome == ValidatorOutcome.REJECTED
    assert "PR-4.1" in result.violated_constraints


# ============================================================
# PR-5.3
# Legal language requires escalation.
# ============================================================

def test_attorney_reference_escalates():
    proposal = ProposedAction(
        action_type=ActionType.SEND_MESSAGE,
        target_channel=Channel.EMAIL,
        rationale="Respond to customer.",
        tool_call_ids=["TC-001"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )

    result = validate_action(
        proposal,
        primary_intent=Intent.HOSTILE_OR_ADVERSARIAL,
        intent_confidence=0.98,
        reply_text="My attorney will be contacting you.",
    )

    assert result.outcome == ValidatorOutcome.ESCALATE
    assert "PR-5.3" in result.violated_constraints


# ============================================================
# GV-5
# Kill switch is tested later by policy fixture/config override.
# ============================================================

# ============================================================
# PR-2.1 / PR-2.4
# Consumer SMS quiet-hours enforcement.
# ============================================================

def make_sms_message():
    return ProposedAction(
        action_type=ActionType.SEND_MESSAGE,
        target_channel=Channel.SMS,
        rationale="Send customer a reminder.",
        tool_call_ids=["TC-001"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )


def test_consumer_sms_at_quiet_hours_start_is_rejected():
    result = validate_action(
        make_sms_message(),
        primary_intent=Intent.PROMISE_TO_PAY,
        intent_confidence=0.95,
        reply_text="I will pay Friday.",
        debt_classification=DebtClassification.CONSUMER,
        sms_consent=True,
        proposed_send_time=datetime(
            2026,
            9,
            11,
            21,
            0,
            tzinfo=timezone(timedelta(hours=-4)),
        ),
    )

    assert result.outcome == ValidatorOutcome.REJECTED
    assert "PR-2.1" in result.violated_constraints


def test_consumer_sms_at_quiet_hours_end_is_approved():
    result = validate_action(
        make_sms_message(),
        primary_intent=Intent.PROMISE_TO_PAY,
        intent_confidence=0.95,
        reply_text="I will pay Friday.",
        debt_classification=DebtClassification.CONSUMER,
        sms_consent=True,
        proposed_send_time=datetime(
            2026,
            9,
            12,
            8,
            0,
            tzinfo=timezone(timedelta(hours=-4)),
        ),
    )

    assert result.outcome == ValidatorOutcome.APPROVED


def test_consumer_sms_without_send_time_escalates():
    result = validate_action(
        make_sms_message(),
        primary_intent=Intent.PROMISE_TO_PAY,
        intent_confidence=0.95,
        reply_text="I will pay Friday.",
        debt_classification=DebtClassification.CONSUMER,
        sms_consent=True,
    )

    assert result.outcome == ValidatorOutcome.ESCALATE
    assert "PR-2.4" in result.violated_constraints


def test_consumer_email_is_exempt_from_quiet_hours():
    proposal = ProposedAction(
        action_type=ActionType.SEND_MESSAGE,
        target_channel=Channel.EMAIL,
        rationale="Send customer a reminder.",
        tool_call_ids=["TC-001"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )

    result = validate_action(
        proposal,
        primary_intent=Intent.PROMISE_TO_PAY,
        intent_confidence=0.95,
        reply_text="I will pay Friday.",
        debt_classification=DebtClassification.CONSUMER,
        proposed_send_time=datetime(
            2026,
            9,
            11,
            22,
            0,
            tzinfo=timezone(timedelta(hours=-4)),
        ),
    )

    assert result.outcome == ValidatorOutcome.APPROVED

# ============================================================
# PR-2.3
# Rolling seven-day outbound contact-frequency limit.
# ============================================================

def test_fourth_contact_with_three_prior_contacts_is_approved():
    proposal = ProposedAction(
        action_type=ActionType.SEND_MESSAGE,
        target_channel=Channel.EMAIL,
        rationale="Send customer a reminder.",
        tool_call_ids=["TC-001"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )

    result = validate_action(
        proposal,
        primary_intent=Intent.PROMISE_TO_PAY,
        intent_confidence=0.95,
        reply_text="I will pay Friday.",
        debt_classification=DebtClassification.CONSUMER,
        recent_outbound_contact_count=3,
    )

    assert result.outcome == ValidatorOutcome.APPROVED


def test_fifth_contact_with_four_prior_contacts_is_rejected():
    proposal = ProposedAction(
        action_type=ActionType.SEND_MESSAGE,
        target_channel=Channel.EMAIL,
        rationale="Send customer a reminder.",
        tool_call_ids=["TC-001"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )

    result = validate_action(
        proposal,
        primary_intent=Intent.PROMISE_TO_PAY,
        intent_confidence=0.95,
        reply_text="I will pay Friday.",
        debt_classification=DebtClassification.CONSUMER,
        recent_outbound_contact_count=4,
    )

    assert result.outcome == ValidatorOutcome.REJECTED
    assert "PR-2.3" in result.violated_constraints
