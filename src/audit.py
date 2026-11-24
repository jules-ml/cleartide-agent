import json

from src.database import get_connection


class AuditImmutableError(RuntimeError):
    """A finalized decision record was submitted for rewrite."""
from src.policy import (
    load_policy,
    resolve_debt_classification,
)
from src.schemas import EscalationPacket


# ============================================================
# START DECISION
# ============================================================

def start_decision(
    account_id: int,
    invoice_id: int,
    reply_text: str,
    reasoning_mode: str,
) -> int:
    """
    Create the persistent decision record before reasoning
    begins.

    Returns the database decision_id.
    """

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO agent_actions (
            account_id,
            invoice_id,
            reply_text,
            reasoning_mode,
            revision_count,
            audit_status,
            cost
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            invoice_id,
            reply_text,
            reasoning_mode,
            0,
            "STARTED",
            0.0,
        ),
    )

    decision_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return decision_id


# ============================================================
# DIRECT RELATIONAL HISTORY FOR ESCALATION PACKET
# ============================================================

def _get_escalation_account_history(
    account_id: int,
) -> dict:
    """
    Build exact relational account history for a human-review
    packet.

    This is packet construction, not approximate retrieval.
    """

    conn = get_connection()

    account = conn.execute(
        """
        SELECT *
        FROM accounts
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()

    invoices = conn.execute(
        """
        SELECT *
        FROM invoices
        WHERE account_id = ?
        ORDER BY due_date DESC
        """,
        (account_id,),
    ).fetchall()

    disputes = conn.execute(
        """
        SELECT *
        FROM disputes
        WHERE account_id = ?
        ORDER BY created_at DESC
        """,
        (account_id,),
    ).fetchall()

    promises = conn.execute(
        """
        SELECT *
        FROM promises_to_pay
        WHERE account_id = ?
        ORDER BY created_at DESC
        """,
        (account_id,),
    ).fetchall()

    prior_escalations = conn.execute(
        """
        SELECT
            escalation_id,
            decision_id,
            intent,
            confidence,
            rejection_reason,
            human_disposition,
            status,
            created_at,
            resolved_at
        FROM escalations
        WHERE account_id = ?
        ORDER BY created_at DESC
        """,
        (account_id,),
    ).fetchall()

    conn.close()

    return {
        "account": (
            dict(account)
            if account
            else None
        ),

        "invoices": [
            dict(row)
            for row in invoices
        ],

        "prior_disputes": [
            dict(row)
            for row in disputes
        ],

        "prior_promises_to_pay": [
            dict(row)
            for row in promises
        ],

        "prior_escalations": [
            dict(row)
            for row in prior_escalations
        ],
    }


# ============================================================
# BUILD ESCALATION PACKET
# ============================================================

def build_escalation_packet(
    state: dict,
) -> EscalationPacket:
    """
    Build a complete human-review packet from graph state.
    """

    intent = state.get(
        "intent"
    )

    proposal = state.get(
        "proposed_action"
    )

    validation = state.get(
        "validation"
    )

    risk = state.get(
        "risk"
    )

    tool_results = []

    for key in (
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
):

        result = state.get(
            key
        )

        if result is not None:
            tool_results.append(
                result
            )

    if validation is not None:

        rejection_reason = (
            f"{validation.outcome.value}: "
            f"{validation.explanation}"
        )

    elif state.get(
        "forced_escalation_reason"
    ):

        rejection_reason = state[
            "forced_escalation_reason"
        ]

    else:

        rejection_reason = state.get(
            "final_reason"
        )

    if proposal is not None:

        proposed_action = (
            proposal.model_dump(
                mode="json"
            )
        )

        policy_version = (
            proposal.policy_version
        )

    else:

        proposed_action = None

        policy_version = str(
            load_policy()[
                "policy_version"
            ]
        )

    return EscalationPacket(
        decision_id=state[
            "decision_id"
        ],

        account_id=state[
            "account_id"
        ],

        invoice_id=state.get(
            "invoice_id"
        ),

        reply_text=state[
            "reply_text"
        ],

        primary_intent=(
            intent.primary_intent
            if intent
            else None
        ),

        intent_confidence=(
            intent.confidence
            if intent
            else None
        ),

        tool_results=(
            tool_results
        ),

        risk_score=(
            risk.score
            if risk
            else None
        ),

        risk_band=(
            risk.band
            if risk
            else None
        ),

        top_contributing_factors=(
            risk.contributing_factors
            if risk
            else []
        ),

        proposed_action=(
            proposed_action
        ),

        rejection_reason=(
            rejection_reason
        ),

        account_history=(
            _get_escalation_account_history(
                state["account_id"]
            )
        ),

        policy_version=(
            policy_version
        ),

        final_reason=state[
            "final_reason"
        ],
    )


# ============================================================
# SAVE ESCALATION
# ============================================================

def create_escalation_record(
    state: dict,
):
    """
    Persist a human escalation and its full packet.

    Returns:
        escalation_id, packet
    """

    packet = (
        build_escalation_packet(
            state
        )
    )

    proposal = state.get(
        "proposed_action"
    )

    validation = state.get(
        "validation"
    )

    risk = state.get(
        "risk"
    )

    intent = state.get(
        "intent"
    )

    proposed_action_json = (
        json.dumps(
            proposal.model_dump(
                mode="json"
            )
        )
        if proposal
        else None
    )

    rejection_reason = (
        packet.rejection_reason
    )

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO escalations (
            decision_id,
            account_id,
            invoice_id,
            reply_text,
            intent,
            confidence,
            proposed_action,
            rejection_reason,
            risk_score,
            risk_band,
            packet_json,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state["decision_id"],
            state["account_id"],
            state.get("invoice_id"),
            state["reply_text"],

            (
                intent.primary_intent.value
                if intent
                else None
            ),

            (
                intent.confidence
                if intent
                else None
            ),

            proposed_action_json,

            rejection_reason,

            (
                risk.score
                if risk
                else None
            ),

            (
                risk.band.value
                if risk
                else None
            ),

            json.dumps(
                packet.model_dump(
                    mode="json"
                ),
                default=str,
            ),

            "OPEN",
        ),
    )

    escalation_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return (
        escalation_id,
        packet,
    )


# ============================================================
# FINALIZE DECISION AUDIT
# ============================================================

def finalize_decision(
    state: dict,
):
    """
    Update the original agent_actions row with the complete
    decision result.
    """

    intent = state.get(
        "intent"
    )

    proposal = state.get(
        "proposed_action"
    )

    validation = state.get(
        "validation"
    )

    risk = state.get(
        "risk"
    )

    final_action = state.get(
        "final_action_type"
    )

    account_data = (
        state.get(
            "account_evidence",
            {},
        )
        .get(
            "data",
            {},
        )
        .get(
            "account",
            {},
        )
    )

    secondary_intents = (
        json.dumps(
            [
                item.value
                for item in (
                    intent.secondary_intents
                    if intent
                    else []
                )
            ]
        )
    )

    proposed_action_json = (
        json.dumps(
            proposal.model_dump(
                mode="json"
            )
        )
        if proposal
        else None
    )

    violated_constraints = (
        json.dumps(
            validation.violated_constraints
        )
        if validation
        else None
    )

    violated_fields = (
        json.dumps(
            validation.violated_fields
        )
        if validation
        else None
    )

    policy_version = (
        proposal.policy_version
        if proposal
        else str(
            load_policy()[
                "policy_version"
            ]
        )
    )

    conn = get_connection()

    existing_audit = conn.execute(
        """
        SELECT audit_status
        FROM agent_actions
        WHERE decision_id = ?
        """,
        (
            state["decision_id"],
        ),
    ).fetchone()

    if (
        existing_audit is not None
        and existing_audit["audit_status"] == "COMPLETED"
    ):
        conn.close()
        raise AuditImmutableError(
            "Decision "
            f"{state['decision_id']} is finalized. "
            "Completed audit records cannot be rewritten."
        )

    debt_classification = (
        account_data.get(
            "debt_type"
        )
        if account_data
        else None
    )

    # Unsupported-intent paths may not have called
    # get_account_history(), so recover the debt type directly
    # for the audit record when possible.
    if debt_classification is None:

        row = conn.execute(
            """
            SELECT debt_type
            FROM accounts
            WHERE account_id = ?
            """,
            (
                state[
                    "account_id"
                ],
            ),
        ).fetchone()

        if row:
            debt_classification = (
                row["debt_type"]
            )

    debt_classification = resolve_debt_classification(
        debt_classification
    ).value

    conn.execute(
        """
        UPDATE agent_actions

        SET
            primary_intent = ?,
            secondary_intents = ?,
            confidence = ?,
            debt_classification = ?,
            risk_score = ?,
            risk_band = ?,
            proposed_action = ?,
            final_action = ?,
            final_reason = ?,
            target_channel = ?,
            message_body = ?,
            rationale = ?,
            validator_outcome = ?,
            violated_constraint = ?,
            violated_fields = ?,
            policy_version = ?,
            model_version = ?,
            cost = ?,
            latency_ms = ?,
            reasoning_mode = ?,
            revision_count = ?,
            audit_status = ?

        WHERE decision_id = ?
        """,
        (
            (
                intent.primary_intent.value
                if intent
                else None
            ),

            secondary_intents,

            (
                intent.confidence
                if intent
                else None
            ),

            debt_classification,

            (
                risk.score
                if risk
                else None
            ),

            (
                risk.band.value
                if risk
                else None
            ),

            proposed_action_json,

            (
                final_action.value
                if final_action
                else None
            ),

            state.get(
                "final_reason"
            ),

            (
                proposal.target_channel.value
                if (
                    proposal
                    and proposal.target_channel
                )
                else None
            ),

            (
                proposal.message_body
                if proposal
                else None
            ),

            (
                proposal.rationale
                if proposal
                else None
            ),

            (
                validation.outcome.value
                if validation
                else None
            ),

            violated_constraints,

            violated_fields,

            policy_version,

            (
                risk.model_version
                if risk
                else None
            ),

            0.0,

            state.get(
                "latency_ms"
            ),

            state.get(
                "reasoning_mode"
            ),

            state.get(
                "revision_count",
                0,
            ),

            "COMPLETED",

            state[
                "decision_id"
            ],
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# AUDIT HELPERS FOR TESTING / INSPECTION
# ============================================================

def get_decision_record(
    decision_id: int,
):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM agent_actions
        WHERE decision_id = ?
        """,
        (decision_id,),
    ).fetchone()

    conn.close()

    return (
        dict(row)
        if row
        else None
    )


def get_escalation_packet(
    escalation_id: int,
):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT packet_json
        FROM escalations
        WHERE escalation_id = ?
        """,
        (escalation_id,),
    ).fetchone()

    conn.close()

    if (
        row is None
        or row["packet_json"] is None
    ):
        return None

    return json.loads(
        row["packet_json"]
    )


def attempt_audit_rewrite(
    decision_id: int,
    updates: dict,
) -> None:
    """
    Application path for changing a stored decision.

    Finalized records are evidence. This function refuses the
    rewrite and does not apply ``updates``.
    """

    del updates

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT audit_status
            FROM agent_actions
            WHERE decision_id = ?
            """,
            (decision_id,),
        ).fetchone()

        if row is None:
            raise AuditImmutableError(
                f"Decision {decision_id} does not exist."
            )

        if row["audit_status"] == "COMPLETED":
            raise AuditImmutableError(
                f"Decision {decision_id} is finalized. "
                "Completed audit records cannot be rewritten "
                "through the application."
            )

        raise AuditImmutableError(
            "In-progress audit records are updated only by "
            "the decision workflow."
        )

    finally:
        conn.close()


def _audit_timeline(
    decision: dict,
    tool_calls: list[dict],
    escalation: dict | None,
) -> list[dict]:
    steps = [
        {
            "step": "Decision started",
            "detail": decision.get("created_at") or "Record opened",
        }
    ]

    if decision.get("primary_intent"):
        steps.append(
            {
                "step": "Intent classified",
                "detail": (
                    f"{decision['primary_intent']} "
                    f"(confidence {decision.get('confidence')})"
                ),
            }
        )

    for tool in tool_calls:
        steps.append(
            {
                "step": "Evidence retrieved",
                "detail": (
                    f"{tool.get('tool_name')} "
                    f"[{tool.get('status')}]"
                ),
            }
        )

    if decision.get("proposed_action"):
        steps.append(
            {
                "step": "Action proposed",
                "detail": decision.get("proposed_action"),
            }
        )

    if decision.get("validator_outcome"):
        violated = decision.get("violated_constraint") or "[]"
        steps.append(
            {
                "step": "Policy validated",
                "detail": (
                    f"{decision['validator_outcome']}; "
                    f"constraints {violated}; "
                    f"fields {decision.get('violated_fields')}"
                ),
            }
        )

    if int(decision.get("revision_count") or 0) > 0:
        steps.append(
            {
                "step": "Safe revision attempted",
                "detail": (
                    f"revision_count="
                    f"{decision.get('revision_count')}"
                ),
            }
        )

    steps.append(
        {
            "step": "Decision finalized",
            "detail": (
                f"{decision.get('audit_status')}: "
                f"{decision.get('final_action')} — "
                f"{decision.get('final_reason')}"
            ),
        }
    )

    if escalation is not None:
        steps.append(
            {
                "step": "Human handoff",
                "detail": (
                    f"escalation {escalation.get('escalation_id')} "
                    f"status {escalation.get('status')}"
                ),
            }
        )

        if escalation.get("human_disposition"):
            steps.append(
                {
                    "step": "Human disposition recorded",
                    "detail": escalation.get("human_disposition"),
                }
            )

    for note in decision.get("_audit_notes") or []:
        steps.append(
            {
                "step": "Audit note appended",
                "detail": (
                    f"{note.get('event_type')}: {note.get('detail')}"
                ),
            }
        )

    return steps


def get_complete_audit_record(
    decision_id: int,
) -> dict | None:
    """
    One explainable record for a decision: the decision row,
    every tool call, any escalation, and a readable timeline.
    """

    decision = get_decision_record(decision_id)

    if decision is None:
        return None

    conn = get_connection()

    tool_rows = conn.execute(
        """
        SELECT *
        FROM tool_calls
        WHERE decision_id = ?
        ORDER BY tool_call_id
        """,
        (decision_id,),
    ).fetchall()

    escalation_row = conn.execute(
        """
        SELECT *
        FROM escalations
        WHERE decision_id = ?
        ORDER BY escalation_id DESC
        LIMIT 1
        """,
        (decision_id,),
    ).fetchone()

    note_rows = conn.execute(
        """
        SELECT note_id, decision_id, escalation_id, event_type, detail, created_at
        FROM audit_notes
        WHERE decision_id = ?
        ORDER BY note_id
        """,
        (decision_id,),
    ).fetchall()

    conn.close()

    tool_calls = [dict(row) for row in tool_rows]

    escalation = dict(escalation_row) if escalation_row else None
    notes = [dict(row) for row in note_rows]
    decision["_audit_notes"] = notes

    if escalation and escalation.get("packet_json"):
        try:
            escalation["packet"] = json.loads(escalation["packet_json"])
        except json.JSONDecodeError:
            escalation["packet"] = None

    required = (
        decision.get("audit_status") == "COMPLETED"
        and decision.get("primary_intent")
        and decision.get("final_action")
        and decision.get("policy_version")
        and decision.get("debt_classification")
    )

    return {
        "decision_id": decision_id,
        "decision": decision,
        "tool_calls": tool_calls,
        "audit_notes": notes,
        "escalation": escalation,
        "timeline": _audit_timeline(
            decision,
            tool_calls,
            escalation,
        ),
        "complete": bool(required),
    }