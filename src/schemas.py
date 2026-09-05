from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# REQUIREMENT-ALIGNED CONTROLLED VOCABULARIES
# ============================================================

class Intent(str, Enum):
    """
    FR-1.1
    Controlled vocabulary for the primary intent of an inbound reply.
    """

    DELIVERY_DISPUTE = "DELIVERY_DISPUTE"
    PAYMENT_PLAN_REQUEST = "PAYMENT_PLAN_REQUEST"
    ALREADY_PAID_CLAIM = "ALREADY_PAID_CLAIM"
    PROMISE_TO_PAY = "PROMISE_TO_PAY"
    AMOUNT_DISPUTE = "AMOUNT_DISPUTE"
    HOSTILE_OR_ADVERSARIAL = "HOSTILE_OR_ADVERSARIAL"
    UNCLEAR = "UNCLEAR"


class ActionType(str, Enum):
    """
    FR-4.1
    Controlled vocabulary for the next action selected by the ACA.
    """

    SEND_MESSAGE = "SEND_MESSAGE"
    RESEND_INVOICE = "RESEND_INVOICE"
    PROPOSE_PAYMENT_PLAN = "PROPOSE_PAYMENT_PLAN"
    LOG_DISPUTE_AND_HOLD = "LOG_DISPUTE_AND_HOLD"
    FLAG_FOR_HUMAN_CALL = "FLAG_FOR_HUMAN_CALL"
    ESCALATE = "ESCALATE"
    NO_ACTION_MONITOR = "NO_ACTION_MONITOR"


class Channel(str, Enum):
    """
    FR-4.4
    Controlled vocabulary for communication channel selection.
    """

    EMAIL = "EMAIL"
    SMS = "SMS"
    HUMAN_CALL_FLAG = "HUMAN_CALL_FLAG"


class RiskBand(str, Enum):
    """
    FR-3.3
    Policy rules operate on risk bands rather than raw model scores.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DebtClassification(str, Enum):
    """
    PR-1
    Debt classification determines which policy constraints apply.
    """

    CONSUMER = "CONSUMER"
    COMMERCIAL = "COMMERCIAL"


class ValidatorOutcome(str, Enum):
    """
    FR-5
    Result produced by the deterministic policy validator.
    """

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATE = "ESCALATE"


# ============================================================
# INTENT CLASSIFICATION OUTPUT
# ============================================================

class IntentClassification(BaseModel):
    """
    Structured result of the intent-classification stage.

    Supports:
    - FR-1.1 primary intent
    - FR-1.2 confidence
    - FR-1.4 secondary intents
    """

    primary_intent: Intent

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model confidence for the primary intent."
    )

    secondary_intents: list[Intent] = Field(
        default_factory=list,
        description="Additional intents detected in the same customer reply."
    )


# ============================================================
# RISK RESULT
# ============================================================

class RiskResult(BaseModel):
    """
    Structured output returned by the risk-scoring tool.

    FR-3 requires the risk score to come from a trained model,
    not from free-form LLM judgement.
    """

    score: float = Field(
        ge=0.0,
        le=1.0
    )

    band: RiskBand

    model_version: str

    contributing_factors: list[str] = Field(
        default_factory=list
    )


# ============================================================
# TOOL-CALL RECORD
# ============================================================

class ToolCallRecord(BaseModel):
    """
    FR-2.8
    Every tool call and result must be recorded and referenced.
    """

    tool_call_id: str

    tool_name: str

    arguments: dict

    result: Optional[dict] = None

    status: str


# ============================================================
# PROPOSED ACTION
# ============================================================

class ProposedAction(BaseModel):
    """
    Action proposed by the agent before deterministic validation.

    The language model proposes an action.
    It does NOT authorize execution.
    """

    action_type: ActionType

    target_channel: Optional[Channel] = None

    message_body: Optional[str] = None

    payment_plan_duration_days: Optional[int] = Field(
        default=None,
        ge=1,
        description="Requested payment-plan duration in days."
    )

    payment_plan_down_payment_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Required down payment expressed as a decimal."
    )

    rationale: str

    tool_call_ids: list[str] = Field(
        default_factory=list
    )

    risk_score: float = Field(
        ge=0.0,
        le=1.0
    )

    risk_band: RiskBand

    policy_version: str

# ============================================================
# POLICY VALIDATION RESULT
# ============================================================

class PolicyValidationResult(BaseModel):
    """
    Output of the deterministic policy validator.

    FR-5.3:
    hard-constraint violation causes rejection and escalation.
    """

    outcome: ValidatorOutcome

    violated_constraints: list[str] = Field(
        default_factory=list
    )

    explanation: str


# ============================================================
# FINAL AGENT ACTION
# ============================================================

class FinalAction(BaseModel):
    """
    Schema-validated final output of one ACA decision cycle.

    This is the primary output object for the capstone system.
    """

    account_id: int

    invoice_id: Optional[int] = None

    primary_intent: Intent

    secondary_intents: list[Intent] = Field(
        default_factory=list
    )

    intent_confidence: float = Field(
        ge=0.0,
        le=1.0
    )

    debt_classification: DebtClassification

    action_type: ActionType

    target_channel: Optional[Channel] = None

    message_body: Optional[str] = None

    rationale: str

    tool_call_ids: list[str] = Field(
        default_factory=list
    )

    risk_score: float = Field(
        ge=0.0,
        le=1.0
    )

    risk_band: RiskBand

    policy_version: str

    validator_outcome: ValidatorOutcome

    violated_constraints: list[str] = Field(
        default_factory=list
    )

    requires_human_review: bool = False