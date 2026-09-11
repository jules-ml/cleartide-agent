from typing import TypedDict

from src.schemas import (
    ActionType,
    DebtClassification,
    EscalationPacket,
    IntentClassification,
    PolicyValidationResult,
    ProposedAction,
    RiskResult,
)


class AgentState(TypedDict, total=False):
    """
    Shared state for one ACA decision cycle.
    """

    # ========================================================
    # INPUT
    # ========================================================

    account_id: int
    invoice_id: int
    reply_text: str

    # ========================================================
    # DECISION AUDIT
    # ========================================================

    decision_id: int
    started_at: float
    latency_ms: float
    reasoning_mode: str

     # ========================================================
    # CLASSIFICATION
    # ========================================================

    intent: IntentClassification

    debt_classification: DebtClassification

    # ========================================================
    # TOOL EVIDENCE
    # ========================================================

    delivery_evidence: dict

    payment_evidence: dict

    payment_history_evidence: dict

    prior_promises_evidence: dict

    prior_disputes_evidence: dict

    prior_escalations_evidence: dict

    account_evidence: dict

    risk_evidence: dict

    risk: RiskResult

    # ========================================================
    # TOOL LOOP GUARDS
    # ========================================================

    tool_call_count: int
    
    # ========================================================
    # PROPOSED DECISION
    # ========================================================

    proposed_action: ProposedAction

    # ========================================================
    # POLICY VALIDATION
    # ========================================================

    validation: PolicyValidationResult

    # ========================================================
    # REVISION CONTROL
    # ========================================================

    revision_count: int
    revision_reason: str

    # ========================================================
    # ESCALATION CONTROL
    # ========================================================

    forced_escalation_reason: str

    escalation_id: int

    escalation_packet: EscalationPacket

    # ========================================================
    # FINAL RESULT
    # ========================================================

    final_status: str

    final_action_type: ActionType

    final_reason: str