from pathlib import Path
import re
from typing import Optional

import yaml

from src.schemas import (
    ActionType,
    Channel,
    Intent,
    PolicyValidationResult,
    ProposedAction,
    RiskBand,
    ValidatorOutcome,
)


# ============================================================
# PATHS
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT_DIR / "config" / "policy.yaml"


# ============================================================
# POLICY LOADING
# ============================================================

def load_policy() -> dict:
    """
    Load the external ACA policy specification.

    PR-6.1:
    Bounds and constraint parameters live outside application code.

    PR-6.2:
    Changing a policy bound should not require changing Python.
    """

    with open(POLICY_PATH, "r", encoding="utf-8") as file:
        policy = yaml.safe_load(file)

    if not policy:
        raise ValueError("Policy file is empty or unreadable.")

    if "policy_version" not in policy:
        raise ValueError("Policy file does not contain policy_version.")

    return policy


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def approved(explanation: str) -> PolicyValidationResult:
    return PolicyValidationResult(
        outcome=ValidatorOutcome.APPROVED,
        violated_constraints=[],
        explanation=explanation,
    )


def rejected(
    constraint_id: str,
    explanation: str,
) -> PolicyValidationResult:
    """
    FR-5.3:
    Hard-constraint violation causes rejection.

    FR-5.4:
    Rejection records the violated constraint.
    """

    return PolicyValidationResult(
        outcome=ValidatorOutcome.REJECTED,
        violated_constraints=[constraint_id],
        explanation=explanation,
    )


def escalate(
    constraint_id: str,
    explanation: str,
) -> PolicyValidationResult:
    return PolicyValidationResult(
        outcome=ValidatorOutcome.ESCALATE,
        violated_constraints=[constraint_id],
        explanation=explanation,
    )


def determine_disputed_amount(
    reply_text: str,
    ledger_amount: float,
) -> Optional[float]:
    """
    Deterministically derive the disputed amount from explicit
    dollar values in the customer reply and the trusted ledger.

    Conservative behavior:
        - requires explicit $ amounts in the reply
        - requires one value to match the ledger amount
        - requires exactly one distinct alternative amount
        - ambiguous or incomplete input returns None
    """

    matches = re.findall(
        r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        reply_text,
    )

    amounts = []

    for match in matches:
        try:
            amount = float(
                match.replace(",", "")
            )
        except ValueError:
            continue

        amounts.append(amount)

    unique_amounts = []

    for amount in amounts:
        if not any(
            abs(amount - existing) < 0.01
            for existing in unique_amounts
        ):
            unique_amounts.append(amount)

    ledger_matches = [
        amount
        for amount in unique_amounts
        if abs(amount - ledger_amount) < 0.01
    ]

    alternatives = [
        amount
        for amount in unique_amounts
        if abs(amount - ledger_amount) >= 0.01
    ]

    if len(ledger_matches) != 1:
        return None

    if len(alternatives) != 1:
        return None

    disputed_amount = abs(
        ledger_amount - alternatives[0]
    )

    if disputed_amount <= 0:
        return None

    return round(disputed_amount, 2)


# ============================================================
# MAIN VALIDATOR
# ============================================================

def validate_action(
    proposal: ProposedAction,
    *,
    primary_intent: Intent,
    intent_confidence: float,
    reply_text: str,
    ledger_amount: Optional[float] = None,
    sms_consent: bool = False,
    channel_opted_out: bool = False,
) -> PolicyValidationResult:
    """
    Deterministically validate an agent-proposed action.

    IMPORTANT:
    This function does not call an LLM.

    It evaluates the proposed action against the external YAML
    policy and returns APPROVED, REJECTED, or ESCALATE.

    This function is intentionally independently executable and
    unit-testable to satisfy FR-5.6.
    """

    policy = load_policy()

    # --------------------------------------------------------
    # PR-6.3 — policy version consistency
    # --------------------------------------------------------

    active_policy_version = str(policy["policy_version"])

    if proposal.policy_version != active_policy_version:
        return escalate(
            "PR-6.3",
            (
                f"Proposal used policy version "
                f"{proposal.policy_version}, but active policy "
                f"version is {active_policy_version}."
            ),
        )

    # --------------------------------------------------------
    # GV-5 — global autonomy kill switch
    # --------------------------------------------------------

    autonomous_enabled = policy["agent"][
        "autonomous_action_enabled"
    ]

    if not autonomous_enabled:
        return escalate(
            "GV-5",
            "Autonomous action is disabled by the global policy switch.",
        )

    # --------------------------------------------------------
    # FR-1.3 — low classification confidence
    # --------------------------------------------------------

    confidence_threshold = float(
        policy["agent"]["classification_confidence_threshold"]
    )

    if intent_confidence < confidence_threshold:
        return escalate(
            "FR-1.3",
            (
                f"Intent confidence {intent_confidence:.2f} is below "
                f"the required threshold of "
                f"{confidence_threshold:.2f}."
            ),
        )

    # --------------------------------------------------------
    # FR-1.5 — UNCLEAR always escalates
    # --------------------------------------------------------

    if primary_intent == Intent.UNCLEAR:
        return escalate(
            "FR-1.5",
            "UNCLEAR intent cannot be acted on autonomously.",
        )

    # --------------------------------------------------------
    # PR-5.3 — legal / sensitive language
    # --------------------------------------------------------

    sensitive_terms = policy["escalation"][
        "legal_or_sensitive_terms"
    ]

    normalized_reply = reply_text.lower()

    matched_terms = [
        term
        for term in sensitive_terms
        if term.lower() in normalized_reply
    ]

    if matched_terms:
        return escalate(
            "PR-5.3",
            (
                "Reply contains mandatory-escalation language: "
                + ", ".join(matched_terms)
            ),
        )

    # --------------------------------------------------------
    # PR-5.4 — disputed amount escalation threshold
    # --------------------------------------------------------

    if primary_intent == Intent.AMOUNT_DISPUTE:

        if ledger_amount is None:
            return escalate(
                "PR-5.4",
                "Trusted ledger amount is unavailable for the disputed invoice.",
            )

        disputed_amount = determine_disputed_amount(
            reply_text,
            ledger_amount,
        )

        if disputed_amount is None:
            return escalate(
                "PR-5.4",
                (
                    "The disputed amount could not be determined "
                    "unambiguously from the reply and trusted ledger."
                ),
            )

        disputed_amount_threshold = float(
            policy["escalation"]["disputed_amount_threshold"]
        )

        if disputed_amount > disputed_amount_threshold:
            return escalate(
                "PR-5.4",
                (
                    f"Disputed amount ${disputed_amount:,.2f} exceeds "
                    f"the ${disputed_amount_threshold:,.2f} "
                    "mandatory-escalation threshold."
                ),
            )

    # --------------------------------------------------------
    # PR-4.2 / PR-4.3 — channel opt-out
    # --------------------------------------------------------

    if channel_opted_out:
        return escalate(
            "PR-4.3",
            (
                "Customer has opted out of the proposed communication "
                "channel; human review is required."
            ),
        )

    # --------------------------------------------------------
    # PR-4.1 — SMS affirmative consent
    # --------------------------------------------------------

    if proposal.target_channel == Channel.SMS:
        sms_requires_consent = policy["contact"][
            "sms_requires_affirmative_consent"
        ]

        if sms_requires_consent and not sms_consent:
            return rejected(
                "PR-4.1",
                "SMS cannot be used without recorded affirmative consent.",
            )

    # --------------------------------------------------------
    # PR-5.2 — payment-plan authority
    # --------------------------------------------------------

    if proposal.action_type == ActionType.PROPOSE_PAYMENT_PLAN:

        if proposal.payment_plan_duration_days is None:
            return rejected(
                "PR-5.2",
                "Payment-plan proposal is missing duration.",
            )

        if proposal.payment_plan_down_payment_pct is None:
            return rejected(
                "PR-5.2",
                "Payment-plan proposal is missing down-payment percentage.",
            )

        risk_band_name = proposal.risk_band.value

        plan_policy = policy["payment_plans"].get(
            risk_band_name
        )

        if plan_policy is None:
            return escalate(
                "PR-5.2",
                (
                    f"No payment-plan policy exists for risk band "
                    f"{risk_band_name}."
                ),
            )

        autonomous_allowed = bool(
            plan_policy["autonomous_allowed"]
        )

        if not autonomous_allowed:
            return escalate(
                "PR-5.2",
                (
                    f"Autonomous payment plans are not permitted for "
                    f"{risk_band_name} risk accounts."
                ),
            )

        maximum_duration = int(
            plan_policy["max_duration_days"]
        )

        minimum_down_payment = float(
            plan_policy["minimum_down_payment_pct"]
        )

        if proposal.payment_plan_duration_days > maximum_duration:
            return rejected(
                "PR-5.2",
                (
                    f"Requested duration of "
                    f"{proposal.payment_plan_duration_days} days exceeds "
                    f"the {maximum_duration}-day maximum for "
                    f"{risk_band_name} risk."
                ),
            )

        if (
            proposal.payment_plan_down_payment_pct
            < minimum_down_payment
        ):
            return rejected(
                "PR-5.2",
                (
                    f"Down payment of "
                    f"{proposal.payment_plan_down_payment_pct:.0%} is "
                    f"below the required "
                    f"{minimum_down_payment:.0%} minimum for "
                    f"{risk_band_name} risk."
                ),
            )

    # --------------------------------------------------------
    # PR-5.1 and PR-5.6
    #
    # Discounts, waivers, write-offs, and service holds are not
    # part of ActionType at all. That is intentional:
    # schema-level exclusion prevents the LLM from selecting them
    # as valid actions.
    # --------------------------------------------------------

    # --------------------------------------------------------
    # If every deterministic check passes...
    # --------------------------------------------------------

    return approved(
        "Proposal satisfies the currently implemented deterministic policy checks."
    )


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    sample = ProposedAction(
        action_type=ActionType.PROPOSE_PAYMENT_PLAN,
        target_channel=Channel.EMAIL,
        payment_plan_duration_days=30,
        payment_plan_down_payment_pct=0.25,
        rationale="Low-risk customer requested a short payment plan.",
        tool_call_ids=["TC-001", "TC-002"],
        risk_score=0.20,
        risk_band=RiskBand.LOW,
        policy_version="0.1-dev",
    )

    result = validate_action(
        sample,
        primary_intent=Intent.PAYMENT_PLAN_REQUEST,
        intent_confidence=0.94,
        reply_text="Can we split this into two payments?",
    )

    print(result.model_dump_json(indent=2))