"""Isolated demo and synthetic accounts. These IDs are never the historical fixtures."""

from copy import deepcopy


def _account(**overrides):
    record = {
        "customer_name": "Demo Hauler Account",
        "industry": "Roll-off waste hauling",
        "debt_type": "COMMERCIAL",
        "account_status": "ACTIVE",
        "sms_consent": 1,
        "email_allowed": 1,
        "lifetime_value": 18000.0,
        "customer_since": "2024-03-01",
        "amount": 1800.0,
        "invoice_status": "OPEN",
        "issue_date": "2026-10-15",
        "due_date": "2026-11-15",
        "risk_score": 0.18,
        "risk_band": "LOW",
        "factors": ["demo fixture"],
        "communications": [],
        "payments": [],
        "promises": [],
        "delivery_status": None,
        "failure_reason": None,
        "opt_outs": [],
    }
    record.update(overrides)
    return record


def demo_accounts():
    """Accounts for the class scenarios and the synthetic set."""

    email_reply = [
        {"direction": "INBOUND", "channel": "EMAIL", "message": "Earlier email reply."},
        {"direction": "INBOUND", "channel": "EMAIL", "message": "Second email reply."},
    ]
    sms_reply = [
        {"direction": "INBOUND", "channel": "SMS", "message": "Earlier text reply."},
        {"direction": "INBOUND", "channel": "SMS", "message": "Second text reply."},
        {"direction": "INBOUND", "channel": "SMS", "message": "Third text reply."},
    ]

    accounts = [
        _account(
            account_id=8801001,
            invoice_id=8805001,
            customer_name="Northline Roll-Off",
            communications=email_reply,
        ),
        _account(
            account_id=8801002,
            invoice_id=8805002,
            customer_name="Coastal Container Service",
            amount=4200.0,
            risk_score=0.46,
            risk_band="MEDIUM",
            factors=["open invoice aging", "medium payment risk"],
            sms_consent=0,
            communications=email_reply,
        ),
        _account(
            account_id=8801003,
            invoice_id=8805003,
            customer_name="Harbor Dumpster Co.",
            communications=email_reply,
        ),
        _account(
            account_id=8801004,
            invoice_id=8805004,
            customer_name="Inland Hauling",
            amount=2400.0,
            communications=email_reply,
        ),
        _account(
            account_id=8801005,
            invoice_id=8805005,
            customer_name="Palm Site Services",
            debt_type="CONSUMER",
            sms_consent=1,
            communications=sms_reply,
        ),
        _account(
            account_id=8802001,
            invoice_id=8806001,
            customer_name="Synthetic Cooperative Payer",
            communications=email_reply,
        ),
        _account(
            account_id=8802002,
            invoice_id=8806002,
            customer_name="Synthetic Unclear Account",
        ),
        _account(
            account_id=8802003,
            invoice_id=8806003,
            customer_name="Synthetic Paid In Full",
            amount=1000.0,
            payments=[{"amount": 1000.0, "status": "posted"}],
        ),
        _account(
            account_id=8802004,
            invoice_id=8806004,
            customer_name="Synthetic Unverified Payment",
            amount=2400.0,
            communications=email_reply,
        ),
        _account(
            account_id=8802005,
            invoice_id=8806005,
            customer_name="Synthetic Partial Payer",
            amount=2000.0,
            payments=[{"amount": 500.0, "status": "posted"}],
            communications=email_reply,
        ),
        _account(
            account_id=8802006,
            invoice_id=8806006,
            customer_name="Synthetic Low-Risk Plan",
            communications=email_reply,
        ),
        _account(
            account_id=8802007,
            invoice_id=8806007,
            customer_name="Synthetic Medium-Risk Plan",
            amount=3600.0,
            risk_score=0.48,
            risk_band="MEDIUM",
            factors=["medium risk plan fixture"],
            communications=email_reply,
        ),
        _account(
            account_id=8802008,
            invoice_id=8806008,
            customer_name="Synthetic Broken Promise",
            promises=[{"amount": 400.0, "status": "broken"}],
            communications=email_reply,
        ),
        _account(
            account_id=8802009,
            invoice_id=8806009,
            customer_name="Synthetic High Risk",
            risk_score=0.72,
            risk_band="HIGH",
            factors=["high risk fixture"],
        ),
        _account(
            account_id=8802010,
            invoice_id=8806010,
            customer_name="Synthetic Amount Dispute",
            amount=800.0,
        ),
        _account(
            account_id=8802011,
            invoice_id=8806011,
            customer_name="Synthetic Delivery Failure",
            delivery_status="FAILED",
            failure_reason="Mailbox rejected message",
            communications=email_reply,
        ),
        _account(
            account_id=8802012,
            invoice_id=8806012,
            customer_name="Synthetic Hostile Account",
        ),
        _account(
            account_id=8802013,
            invoice_id=8806013,
            customer_name="Synthetic Email Opt-Out",
            sms_consent=0,
            opt_outs=["EMAIL"],
        ),
        _account(
            account_id=8802014,
            invoice_id=8806014,
            customer_name="Synthetic SMS Without Consent",
            sms_consent=0,
            communications=sms_reply,
        ),
        _account(
            account_id=8802015,
            invoice_id=8806015,
            customer_name="Synthetic SMS Responsive",
            communications=sms_reply + email_reply[:1],
        ),
        _account(
            account_id=8802016,
            invoice_id=8806016,
            customer_name="Synthetic Email Responsive",
            communications=email_reply + sms_reply[:1],
        ),
        _account(
            account_id=8802017,
            invoice_id=8806017,
            customer_name="Synthetic No Autonomous Channel",
            sms_consent=0,
            email_allowed=0,
        ),
    ]

    return deepcopy(accounts)


CLASS_SCENARIOS = [
    {
        "id": "autonomous_promise",
        "group": "presentation",
        "title": "1. Successful autonomous action",
        "story": (
            "A roll-off customer promises to pay Friday. "
            "Risk is low and promise history is clean, so the agent "
            "acknowledges the promise. Policy approves the email."
        ),
        "account_id": 8801001,
        "invoice_id": 8805001,
        "reply_text": "I'll pay the invoice on Friday.",
        "expected_intent": "PROMISE_TO_PAY",
        "expected_final_status": "APPROVED",
        "expected_final_action": "SEND_MESSAGE",
        "expected_channel": "EMAIL",
        "expected_verdict": "APPROVE",
    },
    {
        "id": "human_review_payment_plan",
        "group": "presentation",
        "title": "2. Mandatory human review",
        "story": (
            "The customer asks for payments. The agent retrieves history "
            "and proposes terms. Medium risk is outside autonomous "
            "payment-plan authority, so the case is handed to a person."
        ),
        "account_id": 8801002,
        "invoice_id": 8805002,
        "reply_text": "I can't pay everything today. Can I make payments?",
        "expected_intent": "PAYMENT_PLAN_REQUEST",
        "expected_final_status": "ESCALATE",
        "expected_final_action": "ESCALATE",
        "expected_constraint": "PR-5.2",
        "expected_verdict": "ESCALATE",
    },
    {
        "id": "blocked_policy_violation",
        "group": "presentation",
        "title": "3. Blocked policy violation",
        "story": (
            "The agent draft is replaced with unauthorized consequence "
            "language. The deterministic validator blocks it. The message "
            "is not sent."
        ),
        "account_id": 8801003,
        "invoice_id": 8805003,
        "reply_text": "I'll pay the invoice on Friday.",
        "injected_message_body": "Failure to pay may result in legal action.",
        "expected_intent": "PROMISE_TO_PAY",
        "expected_final_status": "ESCALATE",
        "expected_final_action": "ESCALATE",
        "expected_constraint": "PR-3",
        "expected_violated_field": "message_body",
        "expected_verdict": "ESCALATE",
    },
    {
        "id": "already_paid_evidence",
        "group": "evidence",
        "title": "4. Evidence before accusation",
        "story": (
            "The customer says the invoice was already paid. "
            "The ledger does not show a matching payment, so the agent "
            "asks for remittance details instead of denying the claim."
        ),
        "account_id": 8801004,
        "invoice_id": 8805004,
        "reply_text": "I already paid this last week.",
        "expected_intent": "ALREADY_PAID_CLAIM",
        "expected_final_status": "APPROVED",
        "expected_final_action": "SEND_MESSAGE",
        "expected_channel": "EMAIL",
        "expected_verdict": "APPROVE",
    },
    {
        "id": "sms_quiet_hours_revision",
        "group": "governance",
        "title": "5. Quiet hours, one safe revision",
        "story": (
            "Recent replies came by text and SMS consent is on file, "
            "so the agent prefers SMS. The proposed send time is inside "
            "consumer quiet hours. Policy rejects the text and revises "
            "once to email."
        ),
        "account_id": 8801005,
        "invoice_id": 8805005,
        "reply_text": "We will pay on Friday.",
        "proposed_send_time": "2026-11-20T22:30:00+00:00",
        "expected_intent": "PROMISE_TO_PAY",
        "expected_final_status": "APPROVED",
        "expected_final_action": "SEND_MESSAGE",
        "expected_channel": "EMAIL",
        "expected_verdict": "SAFE REVISION",
        "expected_constraint": "PR-2.1",
    },
]
