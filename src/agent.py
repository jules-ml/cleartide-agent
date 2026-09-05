import time

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from src.audit import (
    create_escalation_record,
    finalize_decision,
    start_decision,
)

from src.policy import (
    load_policy,
    validate_action,
)

from src.schemas import (
    ActionType,
    AgentActionRecommendation,
    Channel,
    Intent,
    IntentClassification,
    ProposedAction,
    RiskResult,
    ValidatorOutcome,
)

from src.state import AgentState

from src.tool_guard import (
    ToolGuardState,
    execute_guarded_tool,
)

from src.tools import (
    get_account_history,
    get_risk_score,
    verify_invoice_delivery,
)


# ============================================================
# DEVELOPMENT MODE
# ============================================================

DEVELOPMENT_REASONING_MODE = (
    "DETERMINISTIC_MOCK"
)


# ============================================================
# MOCK INTENT CLASSIFIER
# ============================================================

def mock_classify_reply(
    reply_text: str,
) -> IntentClassification:
    """
    Zero-cost deterministic development stand-in for the
    future LLM classifier.
    """

    text = reply_text.lower()

    matched_intents: list[
        Intent
    ] = []

    hostile_terms = [
        "attorney",
        "lawyer",
        "lawsuit",
        "litigation",
        "sue you",
        "regulator",
        "bankruptcy",
    ]

    if any(
        term in text
        for term in hostile_terms
    ):
        matched_intents.append(
            Intent.HOSTILE_OR_ADVERSARIAL
        )

    amount_terms = [
        "wrong amount",
        "incorrect amount",
        "amount is wrong",
        "balance is wrong",
        "overcharged",
        "charge is wrong",
        "dispute the amount",
    ]

    if any(
        term in text
        for term in amount_terms
    ):
        matched_intents.append(
            Intent.AMOUNT_DISPUTE
        )

    already_paid_terms = [
        "already paid",
        "we paid",
        "i paid",
        "payment was sent",
        "payment already sent",
        "already sent payment",
    ]

    if any(
        term in text
        for term in already_paid_terms
    ):
        matched_intents.append(
            Intent.ALREADY_PAID_CLAIM
        )

    payment_plan_terms = [
        "payment plan",
        "split the payment",
        "split this payment",
        "split the balance",
        "installments",
        "monthly payments",
        "two payments",
        "three payments",
        "four payments",
        "extension to pay",
    ]

    if any(
        term in text
        for term in payment_plan_terms
    ):
        matched_intents.append(
            Intent.PAYMENT_PLAN_REQUEST
        )

    promise_terms = [
        "will pay",
        "pay friday",
        "pay monday",
        "pay tomorrow",
        "send payment friday",
        "send the payment",
        "payment next week",
    ]

    if any(
        term in text
        for term in promise_terms
    ):
        matched_intents.append(
            Intent.PROMISE_TO_PAY
        )

    delivery_terms = [
        "never received",
        "didn't receive",
        "did not receive",
        "never got",
        "didn't get",
        "did not get",
        "send it again",
        "resend invoice",
        "invoice wasn't delivered",
        "invoice was not delivered",
    ]

    if any(
        term in text
        for term in delivery_terms
    ):
        matched_intents.append(
            Intent.DELIVERY_DISPUTE
        )

    if not matched_intents:

        return IntentClassification(
            primary_intent=Intent.UNCLEAR,
            confidence=0.50,
            secondary_intents=[],
        )

    policy = load_policy()

    precedence = [
        Intent(value)
        for value
        in policy[
            "intent_precedence"
        ]
    ]

    primary_intent = next(
        intent
        for intent in precedence
        if intent in matched_intents
    )

    secondary_intents = [
        intent
        for intent in matched_intents
        if intent != primary_intent
    ]

    confidence = (
        0.90
        if secondary_intents
        else 0.95
    )

    return IntentClassification(
        primary_intent=primary_intent,
        confidence=confidence,
        secondary_intents=secondary_intents,
    )


# ============================================================
# MOCK ACTION RECOMMENDER
# ============================================================

def mock_recommend_delivery_action(
    state: AgentState,
) -> AgentActionRecommendation:
    """
    Zero-cost deterministic stand-in for the future
    LLM action recommender.
    """

    delivery_data = state[
        "delivery_evidence"
    ]["data"]

    was_delivered = (
        delivery_data.get(
            "was_delivered"
        )
    )

    latest_delivery_event = (
        delivery_data.get(
            "latest_delivery_event"
        )
        or {}
    )

    delivery_status = (
        latest_delivery_event.get(
            "delivery_status"
        )
    )

    failure_reason = (
        latest_delivery_event.get(
            "failure_reason"
        )
    )

    if was_delivered is False:

        rationale = (
            "Verified delivery evidence indicates "
            "that the invoice was not successfully "
            "delivered."
        )

        if delivery_status:

            rationale += (
                f" Delivery status: "
                f"{delivery_status}."
            )

        if failure_reason:

            rationale += (
                f" Failure reason: "
                f"{failure_reason}."
            )

        return AgentActionRecommendation(
            action_type=(
                ActionType.RESEND_INVOICE
            ),

            target_channel=(
                Channel.EMAIL
            ),

            message_body=(
                "Thank you for letting us know. "
                "Our records indicate that the "
                "previous invoice delivery was "
                "unsuccessful. We will resend "
                "the invoice by email."
            ),

            rationale=rationale,
        )

    if was_delivered is True:

        return AgentActionRecommendation(
            action_type=(
                ActionType.FLAG_FOR_HUMAN_CALL
            ),

            target_channel=(
                Channel.HUMAN_CALL_FLAG
            ),

            message_body=None,

            rationale=(
                "The customer reports a delivery "
                "problem, but the delivery record "
                "indicates successful delivery. "
                "Human review is appropriate."
            ),
        )

    return AgentActionRecommendation(
        action_type=(
            ActionType.ESCALATE
        ),

        target_channel=(
            Channel.HUMAN_CALL_FLAG
        ),

        message_body=None,

        rationale=(
            "Delivery status could not be "
            "determined safely from the "
            "available evidence."
        ),
    )


# ============================================================
# NODE 0
# INITIALIZE DECISION
# ============================================================

def initialize_decision_node(
    state: AgentState,
) -> dict:
    """
    Create a persistent decision row before reasoning begins.
    """

    started_at = (
        time.perf_counter()
    )

    decision_id = start_decision(
        account_id=state[
            "account_id"
        ],

        invoice_id=state[
            "invoice_id"
        ],

        reply_text=state[
            "reply_text"
        ],

        reasoning_mode=(
            DEVELOPMENT_REASONING_MODE
        ),
    )

    return {
        "decision_id":
            decision_id,

        "started_at":
            started_at,

        "reasoning_mode":
            DEVELOPMENT_REASONING_MODE,

        "tool_call_count":
            0,

        "tool_call_signatures":
            {},

        "revision_count":
            0,
    }


# ============================================================
# NODE 1
# CLASSIFY
# ============================================================

def classify_reply_node(
    state: AgentState,
) -> dict:

    classification = (
        mock_classify_reply(
            state["reply_text"]
        )
    )

    return {
        "intent":
            classification,
    }


# ============================================================
# ROUTE AFTER CLASSIFICATION
# ============================================================

def route_after_classification(
    state: AgentState,
) -> str:

    if (
        state[
            "intent"
        ].primary_intent
        == Intent.DELIVERY_DISPUTE
    ):
        return "delivery_dispute"

    return "unsupported_intent"


# ============================================================
# NODE 2
# GUARDED EVIDENCE RETRIEVAL
# ============================================================

def gather_delivery_evidence_node(
    state: AgentState,
) -> dict:
    """
    Gather required evidence while enforcing deterministic
    per-decision tool limits.
    """

    guard = ToolGuardState(
        decision_id=state[
            "decision_id"
        ],

        total_calls=state.get(
            "tool_call_count",
            0,
        ),

        signature_counts=dict(
            state.get(
                "tool_call_signatures",
                {},
            )
        ),
    )

    update = {}

    # --------------------------------------------------------
    # TOOL 1
    # VERIFY DELIVERY
    # --------------------------------------------------------

    delivery_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "verify_invoice_delivery"
            ),

            arguments={
                "invoice_id":
                    state[
                        "invoice_id"
                    ]
            },

            tool_function=(
                verify_invoice_delivery
            ),
        )
    )

    update[
        "delivery_evidence"
    ] = delivery_result

    if violation:

        update[
            "guard_violation_reason"
        ] = violation

        update[
            "forced_escalation_reason"
        ] = violation

        update[
            "tool_call_count"
        ] = guard.total_calls

        update[
            "tool_call_signatures"
        ] = dict(
            guard.signature_counts
        )

        return update

    if (
        delivery_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: "
            "verify_invoice_delivery "
            "did not return SUCCESS."
        )

        update[
            "tool_call_count"
        ] = guard.total_calls

        update[
            "tool_call_signatures"
        ] = dict(
            guard.signature_counts
        )

        return update

    # --------------------------------------------------------
    # TOOL 2
    # ACCOUNT HISTORY
    # --------------------------------------------------------

    account_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "get_account_history"
            ),

            arguments={
                "account_id":
                    state[
                        "account_id"
                    ]
            },

            tool_function=(
                get_account_history
            ),
        )
    )

    update[
        "account_evidence"
    ] = account_result

    if violation:

        update[
            "guard_violation_reason"
        ] = violation

        update[
            "forced_escalation_reason"
        ] = violation

        update[
            "tool_call_count"
        ] = guard.total_calls

        update[
            "tool_call_signatures"
        ] = dict(
            guard.signature_counts
        )

        return update

    if (
        account_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: "
            "get_account_history "
            "did not return SUCCESS."
        )

        update[
            "tool_call_count"
        ] = guard.total_calls

        update[
            "tool_call_signatures"
        ] = dict(
            guard.signature_counts
        )

        return update

    # --------------------------------------------------------
    # TOOL 3
    # RISK SCORE
    # --------------------------------------------------------

    risk_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "get_risk_score"
            ),

            arguments={
                "account_id":
                    state[
                        "account_id"
                    ],

                "invoice_id":
                    state[
                        "invoice_id"
                    ],
            },

            tool_function=(
                get_risk_score
            ),
        )
    )

    update[
        "risk_evidence"
    ] = risk_result

    if violation:

        update[
            "guard_violation_reason"
        ] = violation

        update[
            "forced_escalation_reason"
        ] = violation

        update[
            "tool_call_count"
        ] = guard.total_calls

        update[
            "tool_call_signatures"
        ] = dict(
            guard.signature_counts
        )

        return update

    if (
        risk_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: "
            "get_risk_score "
            "did not return SUCCESS."
        )

        update[
            "tool_call_count"
        ] = guard.total_calls

        update[
            "tool_call_signatures"
        ] = dict(
            guard.signature_counts
        )

        return update

    # --------------------------------------------------------
    # TRUSTED RISK RESULT
    # --------------------------------------------------------

    risk_data = (
        risk_result[
            "data"
        ]
    )

    trusted_risk = RiskResult(
        score=(
            risk_data[
                "score"
            ]
        ),

        band=(
            risk_data[
                "risk_band"
            ]
        ),

        model_version=(
            risk_data[
                "model_version"
            ]
        ),

        contributing_factors=(
            risk_data.get(
                "contributing_factors"
            )
            or []
        ),
    )

    update[
        "risk"
    ] = trusted_risk

    update[
        "tool_call_count"
    ] = guard.total_calls

    update[
        "tool_call_signatures"
    ] = dict(
        guard.signature_counts
    )

    return update


# ============================================================
# ROUTE AFTER EVIDENCE
# ============================================================

def route_after_evidence(
    state: AgentState,
) -> str:

    if state.get(
        "forced_escalation_reason"
    ):
        return "forced_escalation"

    return "propose_action"


# ============================================================
# NODE 3
# ACTION PROPOSAL
# ============================================================

def propose_action_node(
    state: AgentState,
) -> dict:

    recommendation = (
        mock_recommend_delivery_action(
            state
        )
    )

    policy = load_policy()

    risk = state[
        "risk"
    ]

    tool_call_ids = [
        state[
            "delivery_evidence"
        ][
            "tool_call_id"
        ],

        state[
            "account_evidence"
        ][
            "tool_call_id"
        ],

        state[
            "risk_evidence"
        ][
            "tool_call_id"
        ],
    ]

    proposal = ProposedAction(
        action_type=(
            recommendation.action_type
        ),

        target_channel=(
            recommendation.target_channel
        ),

        message_body=(
            recommendation.message_body
        ),

        rationale=(
            recommendation.rationale
        ),

        tool_call_ids=(
            tool_call_ids
        ),

        risk_score=(
            risk.score
        ),

        risk_band=(
            risk.band
        ),

        policy_version=str(
            policy[
                "policy_version"
            ]
        ),
    )

    return {
        "proposed_action":
            proposal,
    }


# ============================================================
# NODE 4
# POLICY VALIDATOR
# ============================================================

def validate_proposal_node(
    state: AgentState,
) -> dict:

    proposal = state[
        "proposed_action"
    ]

    account_data = state[
        "account_evidence"
    ][
        "data"
    ][
        "account"
    ]

    sms_consent = bool(
        account_data.get(
            "sms_consent",
            False,
        )
    )

    validation = validate_action(
        proposal,

        primary_intent=(
            state[
                "intent"
            ].primary_intent
        ),

        intent_confidence=(
            state[
                "intent"
            ].confidence
        ),

        reply_text=(
            state[
                "reply_text"
            ]
        ),

        sms_consent=(
            sms_consent
        ),

        channel_opted_out=False,
    )

    return {
        "validation":
            validation,
    }


# ============================================================
# ROUTE AFTER VALIDATION
# ============================================================

def route_after_validation(
    state: AgentState,
) -> str:
    """
    APPROVED:
        final action

    REJECTED:
        allow one revision if policy permits

    ESCALATE:
        no revision; human review
    """

    validation = state[
        "validation"
    ]

    if (
        validation.outcome
        == ValidatorOutcome.APPROVED
    ):
        return "approved"

    policy = load_policy()

    max_revisions = int(
        policy[
            "agent"
        ][
            "max_revision_attempts_after_rejection"
        ]
    )

    revision_count = state.get(
        "revision_count",
        0,
    )

    if (
        validation.outcome
        == ValidatorOutcome.REJECTED
        and revision_count
        < max_revisions
    ):
        return "revise"

    return "escalation"


# ============================================================
# NODE 5
# ONE REVISION ATTEMPT
# ============================================================

def revise_action_node(
    state: AgentState,
) -> dict:
    """
    Deterministically revise a rejected proposal only when a
    safe, explicit correction rule exists.

    Step 9 currently implements the SMS-consent correction:

        SMS rejected
            ->
        use EMAIL if email is permitted

    Anything else escalates.
    """

    proposal = state[
        "proposed_action"
    ]

    validation = state[
        "validation"
    ]

    new_revision_count = (
        state.get(
            "revision_count",
            0,
        )
        + 1
    )

    violations = set(
        validation.violated_constraints
    )

    account_data = state[
        "account_evidence"
    ][
        "data"
    ][
        "account"
    ]

    email_allowed = bool(
        account_data.get(
            "email_allowed",
            False,
        )
    )

    # --------------------------------------------------------
    # SAFE REVISION RULE
    # PR-4.1
    # --------------------------------------------------------

    if (
        "PR-4.1"
        in violations
        and proposal.target_channel
        == Channel.SMS
        and email_allowed
    ):

        revised_proposal = (
            proposal.model_copy(
                update={
                    "target_channel":
                        Channel.EMAIL,

                    "rationale":
                        (
                            proposal.rationale
                            + " Revision 1: SMS was "
                            + "not authorized, so the "
                            + "channel was changed to "
                            + "EMAIL."
                        ),
                }
            )
        )

        return {
            "proposed_action":
                revised_proposal,

            "revision_count":
                new_revision_count,

            "revision_reason":
                (
                    "PR-4.1 SMS rejection "
                    "corrected by switching "
                    "to permitted EMAIL."
                ),
        }

    # --------------------------------------------------------
    # NO SAFE AUTOMATIC REVISION EXISTS
    # --------------------------------------------------------

    return {
        "revision_count":
            new_revision_count,

        "forced_escalation_reason":
            (
                "Validator rejected the proposal, "
                "but no safe deterministic revision "
                "rule exists for the violated "
                "constraint(s): "
                + ", ".join(
                    validation.violated_constraints
                )
            ),
    }


# ============================================================
# ROUTE AFTER REVISION
# ============================================================

def route_after_revision(
    state: AgentState,
) -> str:

    if state.get(
        "forced_escalation_reason"
    ):
        return "forced_escalation"

    return "revalidate"


# ============================================================
# FINAL APPROVED
# ============================================================

def finalize_approved_node(
    state: AgentState,
) -> dict:

    proposal = state[
        "proposed_action"
    ]

    return {
        "final_status":
            "APPROVED",

        "final_action_type":
            proposal.action_type,

        "final_reason":
            (
                "The proposed action passed "
                "deterministic policy validation."
            ),
    }


# ============================================================
# FINAL POLICY ESCALATION
# ============================================================

def finalize_policy_escalation_node(
    state: AgentState,
) -> dict:

    validation = state[
        "validation"
    ]

    return {
        "final_status":
            "ESCALATE",

        "final_action_type":
            ActionType.ESCALATE,

        "final_reason":
            (
                f"Policy outcome: "
                f"{validation.outcome.value}. "
                f"{validation.explanation}"
            ),
    }


# ============================================================
# FINAL FORCED ESCALATION
# ============================================================

def forced_escalation_node(
    state: AgentState,
) -> dict:

    return {
        "final_status":
            "ESCALATE",

        "final_action_type":
            ActionType.ESCALATE,

        "final_reason":
            state[
                "forced_escalation_reason"
            ],
    }


# ============================================================
# UNSUPPORTED INTENT
# ============================================================

def unsupported_intent_node(
    state: AgentState,
) -> dict:

    intent = state[
        "intent"
    ].primary_intent.value

    return {
        "final_status":
            "ESCALATE",

        "final_action_type":
            ActionType.ESCALATE,

        "final_reason":
            (
                f"Intent {intent} is not yet "
                f"implemented in the Step 9 "
                f"vertical slice."
            ),
    }


# ============================================================
# PERSIST FINAL RESULT
# ============================================================

def persist_result_node(
    state: AgentState,
) -> dict:
    """
    Persist the final decision and, when necessary, create
    the human-review escalation packet.
    """

    latency_ms = (
        (
            time.perf_counter()
            - state[
                "started_at"
            ]
        )
        * 1000.0
    )

    update = {
        "latency_ms":
            latency_ms,
    }

    combined_state = {
        **state,
        **update,
    }

    if (
        state[
            "final_status"
        ]
        == "ESCALATE"
    ):

        escalation_id, packet = (
            create_escalation_record(
                combined_state
            )
        )

        update[
            "escalation_id"
        ] = escalation_id

        update[
            "escalation_packet"
        ] = packet

        combined_state = {
            **combined_state,
            **update,
        }

    finalize_decision(
        combined_state
    )

    return update


# ============================================================
# BUILD GRAPH
# ============================================================

def build_graph():

    builder = StateGraph(
        AgentState
    )

    # ========================================================
    # NODES
    # ========================================================

    builder.add_node(
        "initialize_decision",
        initialize_decision_node,
    )

    builder.add_node(
        "classify_reply",
        classify_reply_node,
    )

    builder.add_node(
        "gather_delivery_evidence",
        gather_delivery_evidence_node,
    )

    builder.add_node(
        "propose_action",
        propose_action_node,
    )

    builder.add_node(
        "validate_proposal",
        validate_proposal_node,
    )

    builder.add_node(
        "revise_action",
        revise_action_node,
    )

    builder.add_node(
        "finalize_approved",
        finalize_approved_node,
    )

    builder.add_node(
        "finalize_policy_escalation",
        finalize_policy_escalation_node,
    )

    builder.add_node(
        "forced_escalation",
        forced_escalation_node,
    )

    builder.add_node(
        "unsupported_intent",
        unsupported_intent_node,
    )

    builder.add_node(
        "persist_result",
        persist_result_node,
    )

    # ========================================================
    # START
    # ========================================================

    builder.add_edge(
        START,
        "initialize_decision",
    )

    builder.add_edge(
        "initialize_decision",
        "classify_reply",
    )

    # ========================================================
    # CLASSIFICATION ROUTE
    # ========================================================

    builder.add_conditional_edges(
        "classify_reply",

        route_after_classification,

        {
            "delivery_dispute":
                "gather_delivery_evidence",

            "unsupported_intent":
                "unsupported_intent",
        },
    )

    # ========================================================
    # EVIDENCE ROUTE
    # ========================================================

    builder.add_conditional_edges(
        "gather_delivery_evidence",

        route_after_evidence,

        {
            "propose_action":
                "propose_action",

            "forced_escalation":
                "forced_escalation",
        },
    )

    # ========================================================
    # PROPOSAL -> VALIDATOR
    # ========================================================

    builder.add_edge(
        "propose_action",
        "validate_proposal",
    )

    # ========================================================
    # VALIDATOR ROUTE
    # ========================================================

    builder.add_conditional_edges(
        "validate_proposal",

        route_after_validation,

        {
            "approved":
                "finalize_approved",

            "revise":
                "revise_action",

            "escalation":
                "finalize_policy_escalation",
        },
    )

    # ========================================================
    # REVISION ROUTE
    # ========================================================

    builder.add_conditional_edges(
        "revise_action",

        route_after_revision,

        {
            "revalidate":
                "validate_proposal",

            "forced_escalation":
                "forced_escalation",
        },
    )

    # ========================================================
    # ALL FINAL ROUTES GO THROUGH AUDIT PERSISTENCE
    # ========================================================

    builder.add_edge(
        "finalize_approved",
        "persist_result",
    )

    builder.add_edge(
        "finalize_policy_escalation",
        "persist_result",
    )

    builder.add_edge(
        "forced_escalation",
        "persist_result",
    )

    builder.add_edge(
        "unsupported_intent",
        "persist_result",
    )

    builder.add_edge(
        "persist_result",
        END,
    )

    return builder.compile()


graph = build_graph()


# ============================================================
# PUBLIC RUNNER
# ============================================================

def run_aca(
    account_id: int,
    invoice_id: int,
    reply_text: str,
):

    initial_state: AgentState = {
        "account_id":
            account_id,

        "invoice_id":
            invoice_id,

        "reply_text":
            reply_text,
    }

    return graph.invoke(
        initial_state
    )