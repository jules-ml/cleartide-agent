"""Turn one ACA graph result into the record the demo displays."""

from src.audit import get_complete_audit_record


EVIDENCE_KEYS = (
    "delivery_evidence",
    "payment_evidence",
    "payment_history_evidence",
    "prior_promises_evidence",
    "prior_disputes_evidence",
    "prior_escalations_evidence",
    "prior_unsupported_already_paid_claims_evidence",
    "account_evidence",
    "recent_outbound_contacts_evidence",
    "risk_evidence",
)


def _enum(value):
    if value is None:
        return None
    return getattr(value, "value", value)


def _tool_summary(result) -> list[dict]:
    tools = []

    for key in EVIDENCE_KEYS:
        evidence = result.get(key)
        if not isinstance(evidence, dict) or not evidence.get("tool_name"):
            continue
        data = evidence.get("data") or {}
        tools.append(
            {
                "tool": evidence.get("tool_name"),
                "status": evidence.get("status"),
                "tool_call_id": evidence.get("tool_call_id"),
                "highlights": _highlights(evidence.get("tool_name"), data),
            }
        )

    return tools


def _highlights(tool_name, data) -> str:
    if tool_name == "verify_invoice_delivery":
        return f"was_delivered={data.get('was_delivered')}"
    if tool_name == "reconcile_payment_claim":
        return (
            f"verified={data.get('payment_claim_verified')} "
            f"posted={data.get('posted_payment_total')} "
            f"invoice={data.get('invoice_amount')}"
        )
    if tool_name == "get_risk_score":
        return f"band={data.get('risk_band')} score={data.get('score')}"
    if "count" in data:
        return f"count={data.get('count')}"
    return ""


def verdict_for(result) -> str:
    revision_count = int(result.get("revision_count") or 0)
    final_status = result.get("final_status")

    if final_status == "APPROVED" and revision_count > 0:
        return "SAFE REVISION"
    if final_status == "APPROVED":
        return "APPROVE"
    return "ESCALATE"


def present_decision(scenario: dict, result: dict) -> dict:
    intent = result.get("intent")
    proposal = result.get("proposed_action")
    validation = result.get("validation")
    risk = result.get("risk")
    audit = get_complete_audit_record(result["decision_id"])
    history = result.get("policy_history") or []

    constraints = []
    fields = []
    explanation = None

    if history:
        constraints = list(history[0].get("constraints") or [])
        fields = list(history[0].get("fields") or [])
        explanation = history[0].get("explanation")

    if validation is not None and validation.violated_constraints:
        constraints = list(validation.violated_constraints)
        fields = list(validation.violated_fields)
        explanation = validation.explanation
    elif validation is not None and explanation is None:
        explanation = validation.explanation

    final_action = _enum(result.get("final_action_type"))
    channel = _enum(getattr(proposal, "target_channel", None))
    verdict = verdict_for(result)
    executed = result.get("final_status") == "APPROVED"
    packet = result.get("escalation_packet")
    reviewer_brief = None
    if packet is not None:
        reviewer_brief = getattr(packet, "reviewer_brief", None)
        if reviewer_brief is None and isinstance(packet, dict):
            reviewer_brief = packet.get("reviewer_brief")

    view = {
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "group": scenario.get("group"),
        "story": scenario.get("story"),
        "account_id": scenario["account_id"],
        "invoice_id": scenario["invoice_id"],
        "reply_text": scenario["reply_text"],
        "injected_message_body": scenario.get("injected_message_body"),
        "decision_id": result.get("decision_id"),
        "intent": _enum(getattr(intent, "primary_intent", None)),
        "confidence": getattr(intent, "confidence", None),
        "secondary_intents": [
            _enum(item) for item in getattr(intent, "secondary_intents", []) or []
        ],
        "tools": _tool_summary(result),
        "risk_score": getattr(risk, "score", None),
        "risk_band": _enum(getattr(risk, "band", None)),
        "risk_factors": list(getattr(risk, "contributing_factors", []) or []),
        "recommended_action": _enum(getattr(proposal, "action_type", None)),
        "channel": channel,
        "message_draft": getattr(proposal, "message_body", None),
        "rationale": getattr(proposal, "rationale", None),
        "payment_plan_duration_days": getattr(
            proposal, "payment_plan_duration_days", None
        ),
        "payment_plan_down_payment_pct": getattr(
            proposal, "payment_plan_down_payment_pct", None
        ),
        "verdict": verdict,
        "validator_outcome": _enum(getattr(validation, "outcome", None)),
        "violated_constraints": constraints,
        "violated_fields": fields,
        "policy_explanation": explanation,
        "revision_count": int(result.get("revision_count") or 0),
        "revision_reason": result.get("revision_reason"),
        "final_status": result.get("final_status"),
        "final_action": final_action,
        "final_reason": result.get("final_reason"),
        "executed": executed,
        "reviewer_brief": reviewer_brief,
        "escalation_id": result.get("escalation_id"),
        "audit": _public_audit(audit),
    }

    view["mismatches"] = _mismatches(scenario, view)
    return view


def _public_audit(audit):
    if not audit:
        return None

    escalation = audit.get("escalation") or {}
    return {
        "complete": audit.get("complete"),
        "audit_status": (audit.get("decision") or {}).get("audit_status"),
        "policy_version": (audit.get("decision") or {}).get("policy_version"),
        "debt_classification": (audit.get("decision") or {}).get("debt_classification"),
        "tool_count": len(audit.get("tool_calls") or []),
        "timeline": audit.get("timeline") or [],
        "escalation_status": escalation.get("status"),
        "human_disposition": escalation.get("human_disposition"),
    }


def _mismatches(scenario, view) -> list[str]:
    checks = {
        "expected_intent": view["intent"],
        "expected_final_status": view["final_status"],
        "expected_final_action": view["final_action"],
        "expected_channel": view["channel"],
        "expected_verdict": view["verdict"],
    }
    mismatches = []

    for key, actual in checks.items():
        expected = scenario.get(key)
        if expected is not None and actual != expected:
            mismatches.append(f"{key} expected {expected} but was {actual}")

    constraint = scenario.get("expected_constraint")
    if constraint and constraint not in (view["violated_constraints"] or []):
        mismatches.append(
            f"expected constraint {constraint} in {view['violated_constraints']}"
        )

    field = scenario.get("expected_violated_field")
    if field and field not in (view["violated_fields"] or []):
        mismatches.append(f"expected violated field {field}")

    return mismatches
