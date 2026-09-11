from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Optional

import yaml

from src.schemas import (
    ActionType,
    Channel,
    DebtClassification,
    Intent,
    MessageTone,
    PolicyValidationResult,
    ProposedAction,
    RiskBand,
    RiskResult,
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
        violated_fields=[],
        explanation=explanation,
    )


def rejected(
    constraint_id: str,
    explanation: str,
    violated_fields: Optional[list[str]] = None,
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
        violated_fields=violated_fields or [],
        explanation=explanation,
    )


def escalate(
    constraint_id: str,
    explanation: str,
    violated_fields: Optional[list[str]] = None,
) -> PolicyValidationResult:
    return PolicyValidationResult(
        outcome=ValidatorOutcome.ESCALATE,
        violated_constraints=[constraint_id],
        violated_fields=violated_fields or [],
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


def resolve_debt_classification(
    debt_type: Optional[str | DebtClassification],
) -> DebtClassification:
    """PR-1: normalize debt type and default ambiguity to CONSUMER."""

    if isinstance(debt_type, DebtClassification):
        return debt_type

    if isinstance(debt_type, str):
        normalized = debt_type.strip().upper()

        if normalized == DebtClassification.COMMERCIAL.value:
            return DebtClassification.COMMERCIAL

        if normalized == DebtClassification.CONSUMER.value:
            return DebtClassification.CONSUMER

    return DebtClassification.CONSUMER

def resolve_risk_result(
    risk_tool_result: dict,
    *,
    now_utc: Optional[datetime] = None,
) -> RiskResult:
    """Resolve a risk tool response under deterministic FR-3.4 policy."""

    policy = load_policy()
    risk_policy = policy["risk"]

    fallback_enabled = bool(
        policy["hard_constraints"][
            "missing_or_stale_risk_requires_highest_band"
        ]
    )

    fallback_band_name = str(
        risk_policy["unavailable_score_default_band"]
    )
    fallback_band = RiskBand(fallback_band_name)

    fallback_score = float(
        risk_policy["bands"][fallback_band_name]["minimum"]
    )

    def fallback(reason: str) -> RiskResult:
        if not fallback_enabled:
            raise ValueError(
                "FR-3.4 fallback is disabled by policy."
            )

        return RiskResult(
            score=fallback_score,
            band=fallback_band,
            model_version="POLICY_FALLBACK_FR_3_4",
            contributing_factors=[reason],
        )

    status = risk_tool_result.get("status")

    if status == "NO_RESULT":
        return fallback(
            "FR-3.4: risk score unavailable; highest configured risk band applied."
        )

    if status != "SUCCESS":
        raise ValueError(
            f"Unexpected risk-tool status for FR-3.4 resolver: {status}"
        )

    risk_data = risk_tool_result.get("data") or {}

    if not risk_data.get("risk_score_available", True):
        return fallback(
            "FR-3.4: risk score unavailable; highest configured risk band applied."
        )

    scored_at_text = risk_data.get("scored_at")

    if not scored_at_text:
        return fallback(
            "FR-3.4: risk score timestamp missing; highest configured risk band applied."
        )

    try:
        scored_at = datetime.strptime(
            scored_at_text,
            "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return fallback(
            "FR-3.4: risk score timestamp invalid; highest configured risk band applied."
        )

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    staleness_days = int(
        risk_policy["score_staleness_days"]
    )

    age_seconds = (now_utc - scored_at).total_seconds()

    if age_seconds > staleness_days * 86400:
        return fallback(
            "FR-3.4: risk score stale; highest configured risk band applied."
        )

    return RiskResult(
        score=float(risk_data["score"]),
        band=RiskBand(risk_data["risk_band"]),
        model_version=str(risk_data["model_version"]),
        contributing_factors=(
            risk_data.get("contributing_factors") or []
        ),
    )

def check_unclear_intent(
    primary_intent: Intent,
) -> Optional[PolicyValidationResult]:
    """Deterministically enforce FR-1.5: UNCLEAR always escalates."""

    if primary_intent == Intent.UNCLEAR:
        return escalate(
            "FR-1.5",
            "UNCLEAR intent cannot be acted on autonomously.",
            violated_fields=["primary_intent"],
        )

    return None

def check_sensitive_language(
    reply_text: str,
    policy: Optional[dict] = None,
) -> Optional[PolicyValidationResult]:
    """Deterministically enforce PR-5.3 sensitive-language escalation."""

    if policy is None:
        policy = load_policy()

    sensitive_terms = policy["escalation"]["legal_or_sensitive_terms"]
    normalized_reply = reply_text.lower()

    matched_terms = [
        term for term in sensitive_terms
        if term.lower() in normalized_reply
    ]

    if matched_terms:
        return escalate(
            "PR-5.3",
            "Reply contains mandatory-escalation language: "
            + ", ".join(matched_terms),
            violated_fields=["reply_text"],
        )

    return None

def is_within_consumer_quiet_hours(
    proposed_send_time: datetime,
    *,
    policy: dict,
) -> bool:
    """PR-2.1 / PR-2.4: evaluate configured consumer quiet hours."""

    if proposed_send_time.tzinfo is None:
        raise ValueError(
            "proposed_send_time must be timezone-aware."
        )

    quiet_hours = policy["contact"]["consumer_quiet_hours"]

    start = datetime.strptime(
        quiet_hours["start"],
        "%H:%M",
    ).time()

    end = datetime.strptime(
        quiet_hours["end"],
        "%H:%M",
    ).time()

    local_time = proposed_send_time.timetz().replace(tzinfo=None)

    if start < end:
        return start <= local_time < end

    return (
        local_time >= start
        or local_time < end
    )

def calculate_tenure_months(
    customer_since: str,
    *,
    as_of: datetime,
) -> int:
    """PR-5.5: calculate completed customer-tenure months."""

    start = datetime.fromisoformat(customer_since).date()
    current = as_of.date()

    months = (
        (current.year - start.year) * 12
        + current.month
        - start.month
    )

    if current.day < start.day:
        months -= 1

    return max(months, 0)


# ============================================================
# MAIN VALIDATOR
# ============================================================

def validate_action(
    proposal: ProposedAction,
    *,
    primary_intent: Intent,
    intent_confidence: float,
    reply_text: str,
    debt_classification: Optional[DebtClassification] = None,
    ledger_amount: Optional[float] = None,
    sms_consent: bool = False,
    channel_opted_out: bool = False,
    proposed_send_time: Optional[datetime] = None,
    recent_outbound_contact_count: Optional[int] = None,
    account_lifetime_value: Optional[float] = None,
    customer_since: Optional[str] = None,
    policy_evaluation_time: Optional[datetime] = None,
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

    # PR-1 — normalize debt classification before policy evaluation.
    debt_classification = resolve_debt_classification(
        debt_classification
    )

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
            violated_fields=["policy_version"],
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
            violated_fields=["autonomous_action_enabled"],
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
            violated_fields=["intent_confidence"],
        )

    # --------------------------------------------------------
    # FR-1.5 — UNCLEAR always escalates
    # --------------------------------------------------------

    unclear_result = check_unclear_intent(
        primary_intent
    )

    if unclear_result is not None:
        return unclear_result

    # --------------------------------------------------------
    # PR-5.3 — legal / sensitive language
    # --------------------------------------------------------

    sensitive_language_result = check_sensitive_language(
        reply_text,
        policy=policy,
    )

    if sensitive_language_result is not None:
        return sensitive_language_result

    # --------------------------------------------------------
    # PR-5.4 — disputed amount escalation threshold
    # --------------------------------------------------------

    if primary_intent == Intent.AMOUNT_DISPUTE:

        if ledger_amount is None:
            return escalate(
                "PR-5.4",
                "Trusted ledger amount is unavailable for the disputed invoice.",
                violated_fields=["ledger_amount"],
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
                violated_fields=["reply_text", "ledger_amount"],
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
                violated_fields=["disputed_amount"],
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
            violated_fields=["channel_opted_out"],
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
                violated_fields=["sms_consent"],
            )

    # --------------------------------------------------------
    # PR-2.1 / PR-2.4 — consumer quiet hours
    # --------------------------------------------------------

    if (
        debt_classification == DebtClassification.CONSUMER
        and proposal.target_channel == Channel.SMS
    ):

        if proposed_send_time is None:
            return escalate(
                "PR-2.4",
                "Consumer SMS requires an explicit proposed send time for quiet-hours evaluation.",
                violated_fields=["proposed_send_time"],
            )

        if proposed_send_time.tzinfo is None:
            return escalate(
                "PR-2.4",
                "Consumer SMS proposed send time must be timezone-aware.",
                violated_fields=["proposed_send_time"],
            )

        if is_within_consumer_quiet_hours(
            proposed_send_time,
            policy=policy,
        ):
            return rejected(
                "PR-2.1",
                "Consumer SMS is not permitted during configured quiet hours.",
                violated_fields=["proposed_send_time"],
            )

    # --------------------------------------------------------
    # PR-2.3 — rolling seven-day contact frequency
    # --------------------------------------------------------

    contact_actions = {
        ActionType.SEND_MESSAGE,
        ActionType.RESEND_INVOICE,
        ActionType.PROPOSE_PAYMENT_PLAN,
    }

    if (
        proposal.action_type in contact_actions
        and recent_outbound_contact_count is not None
    ):
        max_contacts = int(
            policy["contact"]["max_contacts_per_7_days"]
        )

        if recent_outbound_contact_count >= max_contacts:
            return rejected(
                "PR-2.3",
                (
                    "Rolling seven-day outbound contact limit "
                    f"of {max_contacts} has been reached."
                ),
                violated_fields=["recent_outbound_contact_count"],
            )

    # --------------------------------------------------------
    # PR-5.5 — firm tone for high-value/high-tenure accounts
    # --------------------------------------------------------

    if proposal.message_tone == MessageTone.FIRM:
        high_value_policy = policy["escalation"]["high_value_account"]

        lifetime_value_threshold = float(
            high_value_policy["lifetime_value_threshold"]
        )

        tenure_months_threshold = int(
            high_value_policy["tenure_months_threshold"]
        )

        missing_context_fields = [
            field_name
            for field_name, field_value in (
                ("account_lifetime_value", account_lifetime_value),
                ("customer_since", customer_since),
                ("policy_evaluation_time", policy_evaluation_time),
            )
            if field_value is None
        ]

        if missing_context_fields:
            return escalate(
                "PR-5.5",
                "Firm-tone proposal requires complete account value and tenure context.",
                violated_fields=missing_context_fields,
            )

        if policy_evaluation_time.tzinfo is None:
            return escalate(
                "PR-5.5",
                "Firm-tone tenure evaluation requires a timezone-aware evaluation time.",
                violated_fields=["policy_evaluation_time"],
            )

        try:
            lifetime_value = float(account_lifetime_value)
        except (TypeError, ValueError):
            return escalate(
                "PR-5.5",
                "Account lifetime value is invalid and requires human review.",
                violated_fields=["account_lifetime_value"],
            )

        try:
            tenure_months = calculate_tenure_months(
                customer_since,
                as_of=policy_evaluation_time,
            )
        except ValueError:
            return escalate(
                "PR-5.5",
                "Customer tenure data is invalid and requires human review.",
                violated_fields=["customer_since"],
            )

        threshold_fields = []

        if lifetime_value >= lifetime_value_threshold:
            threshold_fields.append("account_lifetime_value")

        if tenure_months >= tenure_months_threshold:
            threshold_fields.append("customer_since")

        if threshold_fields:
            return escalate(
                "PR-5.5",
                (
                    "Firm-tone communication for a high-value or "
                    "high-tenure account requires human review."
                ),
                violated_fields=threshold_fields,
            )

    # --------------------------------------------------------
    # PR-5.2 — payment-plan authority
    # --------------------------------------------------------

    if proposal.action_type == ActionType.PROPOSE_PAYMENT_PLAN:

        if proposal.payment_plan_duration_days is None:
            return rejected(
                "PR-5.2",
                "Payment-plan proposal is missing duration.",
                violated_fields=["payment_plan_duration_days"],
            )

        if proposal.payment_plan_down_payment_pct is None:
            return rejected(
                "PR-5.2",
                "Payment-plan proposal is missing down-payment percentage.",
                violated_fields=["payment_plan_down_payment_pct"],
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
                violated_fields=["risk_band"],
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
                violated_fields=["risk_band"],
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
                violated_fields=["payment_plan_duration_days"],
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
                violated_fields=["payment_plan_down_payment_pct"],
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