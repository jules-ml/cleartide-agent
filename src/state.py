from typing import TypedDict

from src.schemas import (
    ActionType,
    IntentClassification,
    PolicyValidationResult,
    ProposedAction,
    RiskResult,
)


class AgentState(TypedDict, total=False):
    """
    Shared state for one ACA decision cycle.

    LangGraph nodes read from this state and return only
    the fields they modify.
    """

    # ========================================================
    # INPUT
    # ========================================================

    account_id: int
    invoice_id: int
    reply_text: str

    # ========================================================
    # INTENT CLASSIFICATION
    # ========================================================

    intent: IntentClassification

    # ========================================================
    # TOOL EVIDENCE
    # ========================================================

    delivery_evidence: dict
    account_evidence: dict
    risk_evidence: dict

    # Parsed trusted risk result.
    risk: RiskResult

    # ========================================================
    # DECISION
    # ========================================================

    proposed_action: ProposedAction

    # ========================================================
    # POLICY
    # ========================================================

    validation: PolicyValidationResult

    # ========================================================
    # CONTROL / ESCALATION
    # ========================================================

    forced_escalation_reason: str

    # ========================================================
    # FINAL RESULT
    # ========================================================

    final_status: str
    final_action_type: ActionType
    final_reason: str