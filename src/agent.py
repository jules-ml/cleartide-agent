from langgraph.graph import END, START, StateGraph

from src.policy import load_policy, validate_action
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
from src.tools import (
    get_account_history,
    get_risk_score,
    verify_invoice_delivery,
)


# ============================================================
# DEVELOPMENT MODE
# ============================================================

DEVELOPMENT_REASONING_MODE = "DETERMINISTIC_MOCK"


# ============================================================
# MOCK INTENT CLASSIFIER
# ============================================================

def mock_classify_reply(
    reply_text: str,
) -> IntentClassification:
    """
    Zero-cost deterministic stand-in for the future
    LLM intent classifier.

    IMPORTANT:
    This is development scaffolding, not the final classifier.

    It uses simple keyword rules so that we can test the
    LangGraph architecture without making paid API calls.
    """

    text = reply_text.lower()

    matched_intents: list[Intent] = []

    # --------------------------------------------------------
    # HOSTILE / ADVERSARIAL
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # AMOUNT DISPUTE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ALREADY PAID
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # PAYMENT PLAN
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # PROMISE TO PAY
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # DELIVERY DISPUTE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # NO MATCH = UNCLEAR
    # --------------------------------------------------------

    if not matched_intents:
        return IntentClassification(
            primary_intent=Intent.UNCLEAR,
            confidence=0.50,
            secondary_intents=[],
        )

    # --------------------------------------------------------
    # APPLY POLICY PRECEDENCE
    #
    # The precedence itself remains externalized in YAML.
    # --------------------------------------------------------

    policy = load_policy()

    precedence = [
        Intent(value)
        for value
        in policy["intent_precedence"]
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
    LLM action reasoner.

    It reasons only over already-retrieved evidence.

    Later, this function can be replaced by an LLM-backed
    recommender without changing the rest of the graph.
    """

    delivery_data = state[
        "delivery_evidence"
    ]["data"]

    was_delivered = delivery_data.get(
        "was_delivered"
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

    # --------------------------------------------------------
    # FAILED / NOT DELIVERED
    # --------------------------------------------------------

    if was_delivered is False:

        rationale = (
            "Verified delivery evidence indicates that the "
            "invoice was not successfully delivered."
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
            action_type=ActionType.RESEND_INVOICE,
            target_channel=Channel.EMAIL,
            message_body=(
                "Thank you for letting us know. "
                "Our records indicate that the previous invoice "
                "delivery was unsuccessful. We will resend the "
                "invoice by email."
            ),
            rationale=rationale,
        )

    # --------------------------------------------------------
    # DELIVERY RECORD SAYS SUCCESS
    #
    # Customer claim conflicts with existing evidence.
    # Conservatively flag for a human rather than improvising.
    # --------------------------------------------------------

    if was_delivered is True:

        return AgentActionRecommendation(
            action_type=ActionType.FLAG_FOR_HUMAN_CALL,
            target_channel=Channel.HUMAN_CALL_FLAG,
            message_body=None,
            rationale=(
                "The customer reports a delivery problem, but "
                "the delivery record indicates successful "
                "delivery. Human review is appropriate because "
                "the claim conflicts with available evidence."
            ),
        )

    # --------------------------------------------------------
    # UNKNOWN DELIVERY STATE
    # --------------------------------------------------------

    return AgentActionRecommendation(
        action_type=ActionType.ESCALATE,
        target_channel=Channel.HUMAN_CALL_FLAG,
        message_body=None,
        rationale=(
            "Delivery status could not be determined safely "
            "from the available evidence."
        ),
    )


# ============================================================
# NODE 1
# CLASSIFY REPLY
# ============================================================

def classify_reply_node(
    state: AgentState,
) -> dict:
    """
    Classify the inbound reply.

    Step 8 uses the deterministic development classifier.
    """

    classification = mock_classify_reply(
        state["reply_text"]
    )

    return {
        "intent": classification,
    }


# ============================================================
# ROUTE AFTER CLASSIFICATION
# ============================================================

def route_after_classification(
    state: AgentState,
) -> str:
    """
    Step 8 implements one complete vertical slice:
    DELIVERY_DISPUTE.

    All other intents safely escalate until their own
    branches are implemented.
    """

    classification = state["intent"]

    if (
        classification.primary_intent
        == Intent.DELIVERY_DISPUTE
    ):
        return "delivery_dispute"

    return "unsupported_intent"


# ============================================================
# NODE 2
# GATHER VERIFIED EVIDENCE
# ============================================================

def gather_delivery_evidence_node(
    state: AgentState,
) -> dict:
    """
    Retrieve deterministic evidence from the simulated
    Cleartide system of record.

    This is real application behavior, not mocked data access.
    """

    account_id = state["account_id"]
    invoice_id = state["invoice_id"]

    delivery_result = (
        verify_invoice_delivery(
            invoice_id
        )
    )

    account_result = (
        get_account_history(
            account_id
        )
    )

    risk_result = (
        get_risk_score(
            account_id,
            invoice_id,
        )
    )

    update = {
        "delivery_evidence":
            delivery_result,

        "account_evidence":
            account_result,

        "risk_evidence":
            risk_result,
    }

    # --------------------------------------------------------
    # REQUIRED TOOL FAILURES
    #
    # FR-2.7:
    # required tool error / no result -> escalation
    # --------------------------------------------------------

    failures = []

    if (
        delivery_result["status"]
        != "SUCCESS"
    ):
        failures.append(
            "verify_invoice_delivery "
            "did not return SUCCESS"
        )

    if (
        account_result["status"]
        != "SUCCESS"
    ):
        failures.append(
            "get_account_history "
            "did not return SUCCESS"
        )

    if (
        risk_result["status"]
        != "SUCCESS"
    ):
        failures.append(
            "get_risk_score "
            "did not return SUCCESS"
        )

    if failures:

        update[
            "forced_escalation_reason"
        ] = "; ".join(
            failures
        )

        return update

    # --------------------------------------------------------
    # TRUSTED RISK
    #
    # Risk comes from the tool result.
    # It is never generated by the mock recommender.
    # --------------------------------------------------------

    risk_data = risk_result[
        "data"
    ]

    trusted_risk = RiskResult(
        score=risk_data["score"],
        band=risk_data["risk_band"],
        model_version=(
            risk_data["model_version"]
        ),
        contributing_factors=(
            risk_data.get(
                "contributing_factors"
            )
            or []
        ),
    )

    update["risk"] = trusted_risk

    return update


# ============================================================
# ROUTE AFTER EVIDENCE
# ============================================================

def route_after_evidence(
    state: AgentState,
) -> str:
    """
    If required evidence failed, do not continue autonomous
    reasoning.
    """

    if state.get(
        "forced_escalation_reason"
    ):
        return "forced_escalation"

    return "propose_action"


# ============================================================
# NODE 3
# PROPOSE ACTION
# ============================================================

def propose_action_node(
    state: AgentState,
) -> dict:
    """
    Produce an action recommendation.

    Step 8 uses the deterministic mock recommender.

    IMPORTANT:
    trusted fields are still attached by application code.
    """

    recommendation = (
        mock_recommend_delivery_action(
            state
        )
    )

    policy = load_policy()

    risk = state["risk"]

    # --------------------------------------------------------
    # TRUST BOUNDARY
    #
    # Recommendation chooses:
    #   action
    #   channel
    #   message
    #   rationale
    #
    # Application code supplies:
    #   real tool IDs
    #   real risk score
    #   real risk band
    #   active policy version
    # --------------------------------------------------------

    tool_call_ids = [
        state[
            "delivery_evidence"
        ]["tool_call_id"],

        state[
            "account_evidence"
        ]["tool_call_id"],

        state[
            "risk_evidence"
        ]["tool_call_id"],
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
        tool_call_ids=tool_call_ids,
        risk_score=risk.score,
        risk_band=risk.band,
        policy_version=str(
            policy["policy_version"]
        ),
    )

    return {
        "proposed_action":
            proposal,
    }


# ============================================================
# NODE 4
# DETERMINISTIC POLICY VALIDATOR
# ============================================================

def validate_proposal_node(
    state: AgentState,
) -> dict:
    """
    Pass the recommendation through the real Step 6
    deterministic validator.
    """

    proposal = state[
        "proposed_action"
    ]

    account_data = state[
        "account_evidence"
    ]["data"]["account"]

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

        # Explicit channel opt-out records are not yet
        # implemented in the development fixture.
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
    Only an APPROVED proposal may continue as an autonomous
    final action.

    Rejected or escalation outcomes fail closed.
    """

    validation = state[
        "validation"
    ]

    if (
        validation.outcome
        == ValidatorOutcome.APPROVED
    ):
        return "approved"

    return "escalation"


# ============================================================
# NODE 5A
# FINAL APPROVED ACTION
# ============================================================

def finalize_approved_node(
    state: AgentState,
) -> dict:
    """
    Finalize the next action.

    Nothing is actually emailed or transmitted.
    This remains a simulated capstone environment.
    """

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
# NODE 5B
# POLICY ESCALATION
# ============================================================

def finalize_policy_escalation_node(
    state: AgentState,
) -> dict:
    """
    Finalize a policy-driven escalation.
    """

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
# NODE 5C
# REQUIRED TOOL FAILURE ESCALATION
# ============================================================

def forced_escalation_node(
    state: AgentState,
) -> dict:
    """
    Required evidence failure causes safe escalation.
    """

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
# NODE 5D
# UNSUPPORTED INTENT ESCALATION
# ============================================================

def unsupported_intent_node(
    state: AgentState,
) -> dict:
    """
    Step 8 only implements DELIVERY_DISPUTE.

    Other intents are intentionally rejected from autonomous
    processing until their branches are implemented.
    """

    intent = (
        state[
            "intent"
        ].primary_intent.value
    )

    return {
        "final_status":
            "ESCALATE",

        "final_action_type":
            ActionType.ESCALATE,

        "final_reason":
            (
                f"Intent {intent} is not yet "
                f"implemented in the Step 8 "
                f"vertical slice."
            ),
    }


# ============================================================
# BUILD LANGGRAPH
# ============================================================

def build_graph():
    """
    Construct the zero-cost Step 8 ACA LangGraph.
    """

    builder = StateGraph(
        AgentState
    )

    # --------------------------------------------------------
    # NODES
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    builder.add_edge(
        START,
        "classify_reply",
    )

    # --------------------------------------------------------
    # CLASSIFICATION ROUTING
    # --------------------------------------------------------

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

    builder.add_edge(
        "unsupported_intent",
        END,
    )

    # --------------------------------------------------------
    # EVIDENCE ROUTING
    # --------------------------------------------------------

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

    builder.add_edge(
        "forced_escalation",
        END,
    )

    # --------------------------------------------------------
    # PROPOSAL -> POLICY VALIDATOR
    # --------------------------------------------------------

    builder.add_edge(
        "propose_action",
        "validate_proposal",
    )

    # --------------------------------------------------------
    # POLICY ROUTING
    # --------------------------------------------------------

    builder.add_conditional_edges(
        "validate_proposal",

        route_after_validation,

        {
            "approved":
                "finalize_approved",

            "escalation":
                "finalize_policy_escalation",
        },
    )

    builder.add_edge(
        "finalize_approved",
        END,
    )

    builder.add_edge(
        "finalize_policy_escalation",
        END,
    )

    return builder.compile()


# Compile the graph once when the module loads.
graph = build_graph()


# ============================================================
# PUBLIC RUNNER
# ============================================================

def run_aca(
    account_id: int,
    invoice_id: int,
    reply_text: str,
):
    """
    Execute one complete ACA decision cycle.
    """

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