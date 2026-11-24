"""Plain-language review brief for an escalated decision.

The structured packet still holds tool results for the audit. This brief
is the part a reviewer reads. Codes stay in the brief only next to a
fixed plain-English gloss. These checks are proxies for human readability,
not a substitute for a person reading the packet.
"""

import re

from src.readability import REVIEWER_GRADE_LIMIT, flesch_kincaid_grade


RULE_PATTERN = re.compile(r"\b(?:PR|FR|GV|DR)-\d+(?:\.\d+)?\b")

SECTION_HEADINGS = (
    "What the customer said",
    "What the agent found",
    "What the agent recommends",
    "Why the agent stopped",
    "What you need to decide",
)

# Each value is the sentence that must appear beside the code.
GLOSS = {
    "DELIVERY_DISPUTE": "The customer says the invoice did not arrive.",
    "PAYMENT_PLAN_REQUEST": "The customer asked to pay over time.",
    "ALREADY_PAID_CLAIM": "The customer says this invoice was already paid.",
    "PROMISE_TO_PAY": "The customer said they will pay.",
    "AMOUNT_DISPUTE": "The customer says the amount is wrong.",
    "HOSTILE_OR_ADVERSARIAL": "The customer used legal or hostile language.",
    "UNCLEAR": "The reply is not clear enough to act on.",
    "SEND_MESSAGE": "The agent wanted to send a message.",
    "RESEND_INVOICE": "The agent wanted to send the invoice again.",
    "PROPOSE_PAYMENT_PLAN": "The agent wanted to offer a payment plan.",
    "LOG_DISPUTE_AND_HOLD": "The agent wanted to record a dispute and pause.",
    "FLAG_FOR_HUMAN_CALL": "The agent wanted a person to call the customer.",
    "ESCALATE": "The agent wanted a person to take the case.",
    "NO_ACTION_MONITOR": "The agent wanted to take no collection step.",
    "EMAIL": "That channel is email.",
    "SMS": "That channel is a text message.",
    "HUMAN_CALL_FLAG": "That channel means a person should call.",
    "LOW": "That risk level is low.",
    "MEDIUM": "That risk level is medium.",
    "HIGH": "That risk level is high.",
    "CRITICAL": "That risk level is critical.",
    "APPROVED": "That result would have allowed the step.",
    "REJECTED": "That result blocked the step.",
    "FR-1.5": "An unclear reply always goes to a person.",
    "FR-2.7": "A missing record stops the case.",
    "FR-7.4": "A third unpaid claim that we cannot find must go to a person.",
    "PR-2.1": "A consumer text is blocked during quiet hours.",
    "PR-2.3": "Too many messages were already sent this week.",
    "PR-2.4": "A consumer text needs a send time before it can go out.",
    "PR-3": "The draft threatens a step the company has not allowed.",
    "PR-4.1": "A text needs a recorded yes before it can be sent.",
    "PR-4.3": "The customer opted out of this channel.",
    "PR-5.2": "This risk level cannot get a payment plan from the agent alone.",
    "PR-5.3": "Legal or sensitive language goes to a person.",
    "PR-5.4": "The disputed amount is too large, or it is not clear.",
    "PR-5.5": "A firm note to a valued customer goes to a person.",
}

_GENERIC_RULE = "This stop rule needs a person before any message is sent."

_TOOL_LABELS = (
    ("delivery_evidence", "invoice delivery"),
    ("payment_evidence", "the payment ledger"),
    ("payment_history_evidence", "past payments"),
    ("prior_promises_evidence", "past promises"),
    ("prior_disputes_evidence", "past disputes"),
    ("prior_escalations_evidence", "past reviews"),
    ("prior_unsupported_already_paid_claims_evidence", "past unpaid claims"),
    ("account_evidence", "the account"),
    ("recent_outbound_contacts_evidence", "recent messages"),
    ("risk_evidence", "the risk score"),
)


def gloss_for(token: str) -> str:
    return GLOSS.get(token, _GENERIC_RULE)


def assess_reviewer_brief(brief: dict) -> dict:
    """Objective proxy checks for one human-facing brief."""

    text = (brief or {}).get("plain_text") or ""
    problems = []

    for heading in SECTION_HEADINGS:
        if heading not in text:
            problems.append(f"missing section: {heading}")

    sections = (brief or {}).get("sections") or []
    bodies = {item.get("heading"): (item.get("body") or "").strip() for item in sections}
    for heading in SECTION_HEADINGS:
        if len(bodies.get(heading, "")) < 12:
            problems.append(f"empty section: {heading}")

    if any(char in text for char in "{}[]"):
        problems.append("json punctuation in the brief")
    if "Traceback" in text or 'File "' in text:
        problems.append("stack trace in the brief")
    if re.search(r"\bnull\b", text, flags=re.IGNORECASE):
        problems.append("null token in the brief")

    shown = set(RULE_PATTERN.findall(text))
    for token in GLOSS:
        if re.search(rf"\b{re.escape(token)}\b", text):
            shown.add(token)

    for token in sorted(shown):
        if gloss_for(token) not in text:
            problems.append(f"no plain explanation for {token}")

    grade = flesch_kincaid_grade(text)
    if grade > REVIEWER_GRADE_LIMIT:
        problems.append(
            f"grade {grade} is above the limit of {REVIEWER_GRADE_LIMIT}"
        )

    return {
        "ok": not problems,
        "problems": problems,
        "grade": grade,
        "grade_limit": REVIEWER_GRADE_LIMIT,
        "codes": sorted(shown),
    }


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _codes_in_order(values: list[str]) -> list[str]:
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _constraint_ids(state: dict) -> list[str]:
    found = []
    validation = state.get("validation")
    if validation is not None:
        found.extend(validation.violated_constraints or [])
    for event in state.get("policy_history") or []:
        found.extend(event.get("constraints") or [])
    for source in (
        state.get("final_reason") or "",
        state.get("forced_escalation_reason") or "",
    ):
        found.extend(RULE_PATTERN.findall(source))
    return _codes_in_order(found)


def build_reviewer_brief(state: dict) -> dict:
    """Build the five plain-language sections for a reviewer."""

    intent = state.get("intent")
    proposal = state.get("proposed_action")
    risk = state.get("risk")
    reply = (state.get("reply_text") or "").strip()

    said = f'The customer wrote: "{reply}"'

    checked = [
        label
        for key, label in _TOOL_LABELS
        if state.get(key)
    ]
    found_parts = []
    if checked:
        found_parts.append(f"The agent checked {_join(checked)}.")
    else:
        found_parts.append(
            "The agent did not look up records. The reply itself was enough to stop."
        )
    if risk is not None:
        band = str(risk.band.value).lower()
        found_parts.append(f"The risk level on file is {band}.")
    else:
        found_parts.append("No risk score was used.")
    found = " ".join(found_parts)

    intent_code = intent.primary_intent.value if intent is not None else None
    recommend_parts = []
    if intent_code:
        recommend_parts.append(
            f"The intent code is {intent_code}. {gloss_for(intent_code)}"
        )
    if proposal is None:
        recommend_parts.append("The agent did not recommend a customer message.")
    else:
        action = proposal.action_type.value
        recommend_parts.append(
            f"The action code is {action}. {gloss_for(action)}"
        )
        if proposal.payment_plan_duration_days:
            percent = int(round((proposal.payment_plan_down_payment_pct or 0) * 100))
            recommend_parts.append(
                f"The plan would last {proposal.payment_plan_duration_days} days. "
                f"The first payment would be {percent} percent."
            )
        if proposal.message_body:
            recommend_parts.append(
                f'The draft said: "{proposal.message_body.strip()}"'
            )
        else:
            recommend_parts.append("There is no customer draft.")
    recommends = " ".join(recommend_parts)

    why_parts = ["The agent stopped before a message was sent."]
    for code in _constraint_ids(state):
        why_parts.append(f"The rule code is {code}. {gloss_for(code)}")
    if len(why_parts) == 1:
        why_parts.append("No single rule code was stored. A person still needs to decide.")
    why = " ".join(why_parts)

    decide = (
        "Choose one outcome. Approve a next step, reject it, change it, or mark the case resolved. "
        "Record that choice. The agent will not contact the customer until you do."
    )

    sections = [
        {"heading": "What the customer said", "body": said},
        {"heading": "What the agent found", "body": found},
        {"heading": "What the agent recommends", "body": recommends},
        {"heading": "Why the agent stopped", "body": why},
        {"heading": "What you need to decide", "body": decide},
    ]
    plain = "\n".join(f"{item['heading']}\n{item['body']}" for item in sections)
    grade = flesch_kincaid_grade(plain)

    return {
        "sections": sections,
        "plain_text": plain,
        "grade": grade,
        "grade_limit": REVIEWER_GRADE_LIMIT,
        "grade_note": (
            "Flesch-Kincaid grade of the agent-written sentences. "
            "Quotes are excluded. This is a proxy for a human reading, not a human rating."
        ),
    }
