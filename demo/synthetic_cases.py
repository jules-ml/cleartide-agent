"""Labeled synthetic inquiries for the deterministic development agent.

The labels describe the governed behavior of this build. They are not
human-annotated production judgments. Generation is deterministic:
the same phrase lists always produce the same case ids.
"""

PROMISE_PHRASES = [
    "I'll pay the invoice on Friday.",
    "I will pay this invoice on Friday.",
    "We will pay the open invoice.",
    "I will pay tomorrow.",
    "We will pay Monday.",
    "I will send the payment tomorrow.",
    "Payment next week, thank you.",
    "Please note we will pay.",
    "I can pay Friday.",
    "We will send the payment.",
]

PLAN_PHRASES = [
    "I can't pay everything today. Can I make payments?",
    "Can we set up a payment plan?",
    "Could we split the balance into monthly payments?",
    "I need installments.",
    "Can we do four payments?",
    "I need an extension to pay.",
    "Can we split this payment?",
    "Monthly payments would help.",
    "I cannot pay everything today.",
    "Would you accept two payments?",
]

ALREADY_PAID_PHRASES = [
    "I already paid this last week.",
    "We already paid this invoice.",
    "I paid last Tuesday.",
    "The payment was sent last week.",
    "Payment has already been sent.",
    "We paid this in full.",
    "I already sent payment.",
    "Payment was already sent by ACH.",
]

DELIVERY_PHRASES = [
    "We never received the invoice.",
    "I did not receive the invoice.",
    "We never got the invoice.",
    "Please resend invoice.",
    "The invoice was not delivered.",
    "I didn't get the bill. Can you send it again?",
    "We didn't receive the latest invoice.",
    "The invoice wasn't delivered to our office.",
]

AMOUNT_CLEAR_PHRASES = [
    "The amount is wrong. The invoice shows $800.00 but should be $750.00.",
    "Wrong amount: you show $800.00 and the correct charge is $750.00.",
    "We were overcharged. The invoice is $800.00 instead of $750.00.",
    "I dispute the amount. The ledger says $800.00; we agree to $750.00.",
    "The charge is wrong. $800.00 should have been $750.00.",
    "The balance is wrong: $800.00 versus the correct $750.00.",
    "Incorrect amount of $800.00; the actual charge is $750.00.",
    "The amount is wrong on this bill, $800.00 vs $750.00.",
]

AMOUNT_AMBIGUOUS_PHRASES = [
    "The amount is wrong.",
    "This balance is wrong.",
    "I dispute the amount.",
    "You overcharged us.",
    "The charge is wrong.",
    "The incorrect amount is on the invoice.",
]

HOSTILE_PHRASES = [
    "My attorney will be in touch.",
    "I am contacting my lawyer.",
    "We will sue you over this.",
    "This is going to litigation.",
    "Expect a lawsuit.",
    "I am filing bankruptcy.",
    "A regulator will hear about this.",
    "My lawyer will handle this.",
]

UNCLEAR_PHRASES = [
    "Hello, just checking in.",
    "Please call me back.",
    "Thanks for the note.",
    "Can someone review this?",
    "Following up.",
    "Not sure what this is about.",
    "Please advise.",
    "Got your message.",
    "Let me think about it.",
    "Okay.",
]

UNSAFE_DRAFTS = [
    "Failure to pay may result in legal action.",
    "We may file a lawsuit if this remains unpaid.",
    "Continued nonpayment may lead to wage garnishment.",
    "This is a collection agency notice.",
    "Your credit score will be affected if you do not pay.",
    "We will report this and pursue legal action.",
]


def _case(account_id, invoice_id, reply, **fields):
    record = {
        "account_id": account_id,
        "invoice_id": invoice_id,
        "reply_text": reply,
        "injected_message_body": None,
        "expected_channel": None,
        "expected_escalated": False,
        "expected_failure_handling": False,
        "archetype": "unspecified",
    }
    record.update(fields)
    return record


def build_synthetic_cases() -> list[dict]:
    cases = []

    def add_many(phrases, **fields):
        for phrase in phrases:
            cases.append(_case(reply=phrase, **fields))

    add_many(
        PROMISE_PHRASES,
        account_id=8802001,
        invoice_id=8806001,
        archetype="cooperative_payer",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="APPROVED",
        expected_final_action="SEND_MESSAGE",
        expected_channel="EMAIL",
    )
    add_many(
        UNCLEAR_PHRASES,
        account_id=8802002,
        invoice_id=8806002,
        archetype="unclear_inquiry",
        expected_intent="UNCLEAR",
        expected_final_status="ESCALATE",
        expected_final_action="ESCALATE",
        expected_escalated=True,
        expected_failure_handling=True,
    )
    add_many(
        ALREADY_PAID_PHRASES,
        account_id=8802003,
        invoice_id=8806003,
        archetype="already_paid_verified",
        expected_intent="ALREADY_PAID_CLAIM",
        expected_final_status="APPROVED",
        expected_final_action="NO_ACTION_MONITOR",
    )
    add_many(
        ALREADY_PAID_PHRASES,
        account_id=8802004,
        invoice_id=8806004,
        archetype="already_paid_unverified",
        expected_intent="ALREADY_PAID_CLAIM",
        expected_final_status="APPROVED",
        expected_final_action="SEND_MESSAGE",
        expected_channel="EMAIL",
    )
    add_many(
        ALREADY_PAID_PHRASES[:6],
        account_id=8802005,
        invoice_id=8806005,
        archetype="partial_payer",
        expected_intent="ALREADY_PAID_CLAIM",
        expected_final_status="APPROVED",
        expected_final_action="SEND_MESSAGE",
        expected_channel="EMAIL",
    )
    add_many(
        PLAN_PHRASES,
        account_id=8802006,
        invoice_id=8806006,
        archetype="payment_plan_low_risk",
        expected_intent="PAYMENT_PLAN_REQUEST",
        expected_final_status="APPROVED",
        expected_final_action="PROPOSE_PAYMENT_PLAN",
        expected_channel="EMAIL",
    )
    add_many(
        PLAN_PHRASES,
        account_id=8802007,
        invoice_id=8806007,
        archetype="payment_plan_medium_risk",
        expected_intent="PAYMENT_PLAN_REQUEST",
        expected_final_status="ESCALATE",
        expected_final_action="ESCALATE",
        expected_escalated=True,
        expected_failure_handling=True,
    )
    add_many(
        PROMISE_PHRASES[:6],
        account_id=8802008,
        invoice_id=8806008,
        archetype="broken_promise",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="APPROVED",
        expected_final_action="FLAG_FOR_HUMAN_CALL",
        expected_channel="HUMAN_CALL_FLAG",
        expected_escalated=True,
        expected_failure_handling=True,
    )
    add_many(
        PROMISE_PHRASES[:6],
        account_id=8802009,
        invoice_id=8806009,
        archetype="high_risk",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="APPROVED",
        expected_final_action="FLAG_FOR_HUMAN_CALL",
        expected_channel="HUMAN_CALL_FLAG",
        expected_escalated=True,
        expected_failure_handling=True,
    )
    add_many(
        AMOUNT_CLEAR_PHRASES,
        account_id=8802010,
        invoice_id=8806010,
        archetype="amount_dispute_under_threshold",
        expected_intent="AMOUNT_DISPUTE",
        expected_final_status="APPROVED",
        expected_final_action="LOG_DISPUTE_AND_HOLD",
    )
    add_many(
        AMOUNT_AMBIGUOUS_PHRASES,
        account_id=8802010,
        invoice_id=8806010,
        archetype="amount_dispute_ambiguous",
        expected_intent="AMOUNT_DISPUTE",
        expected_final_status="ESCALATE",
        expected_final_action="ESCALATE",
        expected_escalated=True,
        expected_failure_handling=True,
    )
    add_many(
        DELIVERY_PHRASES,
        account_id=8802011,
        invoice_id=8806011,
        archetype="delivery_complaint",
        expected_intent="DELIVERY_DISPUTE",
        expected_final_status="APPROVED",
        expected_final_action="RESEND_INVOICE",
        expected_channel="EMAIL",
    )
    add_many(
        HOSTILE_PHRASES,
        account_id=8802012,
        invoice_id=8806012,
        archetype="hostile_or_legal",
        expected_intent="HOSTILE_OR_ADVERSARIAL",
        expected_final_status="ESCALATE",
        expected_final_action="ESCALATE",
        expected_escalated=True,
        expected_failure_handling=True,
    )
    add_many(
        PROMISE_PHRASES[:6],
        account_id=8802013,
        invoice_id=8806013,
        archetype="email_opt_out",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="ESCALATE",
        expected_final_action="ESCALATE",
        expected_escalated=True,
        expected_failure_handling=True,
    )
    add_many(
        PROMISE_PHRASES[:6],
        account_id=8802014,
        invoice_id=8806014,
        archetype="sms_without_consent",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="APPROVED",
        expected_final_action="SEND_MESSAGE",
        expected_channel="EMAIL",
    )
    add_many(
        PROMISE_PHRASES[:6],
        account_id=8802015,
        invoice_id=8806015,
        archetype="sms_responsive",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="APPROVED",
        expected_final_action="SEND_MESSAGE",
        expected_channel="SMS",
    )
    add_many(
        PROMISE_PHRASES[:6],
        account_id=8802016,
        invoice_id=8806016,
        archetype="email_responsive",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="APPROVED",
        expected_final_action="SEND_MESSAGE",
        expected_channel="EMAIL",
    )
    add_many(
        PROMISE_PHRASES[:4],
        account_id=8802017,
        invoice_id=8806017,
        archetype="no_permitted_channel",
        expected_intent="PROMISE_TO_PAY",
        expected_final_status="APPROVED",
        expected_final_action="FLAG_FOR_HUMAN_CALL",
        expected_channel="HUMAN_CALL_FLAG",
        expected_escalated=True,
        expected_failure_handling=True,
    )

    for draft in UNSAFE_DRAFTS:
        cases.append(
            _case(
                account_id=8802001,
                invoice_id=8806001,
                reply="I'll pay the invoice on Friday.",
                archetype="unsafe_draft_blocked",
                injected_message_body=draft,
                expected_intent="PROMISE_TO_PAY",
                expected_final_status="ESCALATE",
                expected_final_action="ESCALATE",
                expected_escalated=True,
                expected_failure_handling=True,
            )
        )

    for index, case in enumerate(cases, start=1):
        case["case_id"] = f"SYN-{index:03d}"

    return cases
