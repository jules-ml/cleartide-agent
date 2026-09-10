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
    get_payment_history,
    get_prior_disputes,
    get_prior_promises,
    get_risk_score,
    reconcile_payment_claim,
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
        "payment was already sent",
        "payment already sent",
        "already sent payment",
        "payment has been sent",
        "payment has already been sent",
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
# MOCK DELIVERY ACTION RECOMMENDER
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
# MOCK ALREADY-PAID ACTION RECOMMENDER
# ============================================================

def mock_recommend_already_paid_action(
    state: AgentState,
) -> AgentActionRecommendation:
    """
    Zero-cost deterministic development stand-in for the
    future LLM reasoning step for ALREADY_PAID_CLAIM.

    The function reasons only over verified ledger evidence.

    It never assumes that the customer is correct or incorrect
    without using reconcile_payment_claim first.
    """

    payment_data = state[
        "payment_evidence"
    ]["data"]

    account_data = state[
        "account_evidence"
    ]["data"]["account"]

    payment_claim_verified = bool(
        payment_data.get(
            "payment_claim_verified",
            False,
        )
    )

    invoice_amount = float(
        payment_data.get(
            "invoice_amount",
            0.0,
        )
    )

    posted_payment_total = float(
        payment_data.get(
            "posted_payment_total",
            0.0,
        )
    )

    email_allowed = bool(
        account_data.get(
            "email_allowed",
            False,
        )
    )

    # ========================================================
    # CASE 1
    # PAYMENT IS VERIFIED
    # ========================================================

    if payment_claim_verified:

        return AgentActionRecommendation(
            action_type=(
                ActionType.NO_ACTION_MONITOR
            ),

            target_channel=None,

            message_body=None,

            rationale=(
                "Ledger reconciliation verifies the customer's "
                "payment claim. Posted payments total "
                f"${posted_payment_total:,.2f} against an "
                f"invoice amount of ${invoice_amount:,.2f}. "
                "No additional collection action is appropriate."
            ),
        )

    # ========================================================
    # CASE 2
    # CLAIM IS NOT VERIFIED, BUT EMAIL IS AVAILABLE
    # ========================================================

    if email_allowed:

        return AgentActionRecommendation(
            action_type=(
                ActionType.SEND_MESSAGE
            ),

            target_channel=(
                Channel.EMAIL
            ),

            message_body=(
                "Thank you for the payment update. "
                "We were unable to match a full payment to this "
                "invoice in our current records. Please reply "
                "with the payment date, amount, and transaction "
                "or reference number so we can reconcile it."
            ),

            rationale=(
                "Ledger reconciliation did not verify full "
                "payment of the invoice. Current posted payments "
                f"total ${posted_payment_total:,.2f} against an "
                f"invoice amount of ${invoice_amount:,.2f}. "
                "The customer should be asked for remittance "
                "details rather than being told that no payment "
                "was made."
            ),
        )

    # ========================================================
    # CASE 3
    # CLAIM NOT VERIFIED AND NO EMAIL AVAILABLE
    # ========================================================

    return AgentActionRecommendation(
        action_type=(
            ActionType.FLAG_FOR_HUMAN_CALL
        ),

        target_channel=(
            Channel.HUMAN_CALL_FLAG
        ),

        message_body=None,

        rationale=(
            "The payment claim could not be verified from the "
            "ledger and the account does not permit email "
            "communication. Human follow-up is required."
        ),
    )


# ============================================================
# DEVELOPMENT PAYMENT-PLAN TERMS
# ============================================================

def get_development_payment_plan_terms(
    risk_band_value: str,
) -> tuple[int | None, float | None]:
    """
    Development terms aligned with the current policy file.

    These values are NOT the final authority.

    The deterministic policy validator remains authoritative
    and may reject or escalate a proposed plan.
    """

    terms_by_band = {
        "LOW": (
            60,
            0.20,
        ),

        "MEDIUM": (
            45,
            0.25,
        ),

        "HIGH": (
            30,
            0.40,
        ),

        "CRITICAL": (
            None,
            None,
        ),
    }

    return terms_by_band.get(
        risk_band_value,
        (
            None,
            None,
        ),
    )


# ============================================================
# MOCK PAYMENT-PLAN ACTION RECOMMENDER
# ============================================================

def mock_recommend_payment_plan_action(
    state: AgentState,
) -> AgentActionRecommendation:
    """
    Zero-cost deterministic development stand-in for the
    future LLM reasoning step for PAYMENT_PLAN_REQUEST.

    The reasoning layer may propose a payment plan, but the
    deterministic validator remains responsible for deciding
    whether the agent has authority to execute it.
    """

    risk = state[
        "risk"
    ]

    risk_band_value = (
        risk.band.value
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

    (
        duration_days,
        down_payment_pct,
    ) = (
        get_development_payment_plan_terms(
            risk_band_value
        )
    )

    # ========================================================
    # NO SAFE PLAN TERMS
    # ========================================================

    if (
        duration_days is None
        or down_payment_pct is None
    ):

        return AgentActionRecommendation(
            action_type=(
                ActionType.ESCALATE
            ),

            target_channel=(
                Channel.HUMAN_CALL_FLAG
            ),

            message_body=None,

            rationale=(
                "The account is in a risk band for which "
                "the development policy does not define "
                "autonomous payment-plan terms. Human "
                "review is required."
            ),
        )

    # ========================================================
    # NO PERMITTED EMAIL CHANNEL
    # ========================================================

    if not email_allowed:

        return AgentActionRecommendation(
            action_type=(
                ActionType.FLAG_FOR_HUMAN_CALL
            ),

            target_channel=(
                Channel.HUMAN_CALL_FLAG
            ),

            message_body=None,

            rationale=(
                "A payment-plan request was received and "
                "supporting payment history, promise history, "
                "and risk evidence were retrieved, but email "
                "communication is not permitted for this "
                "account. Human follow-up is required."
            ),
        )

    down_payment_percent = (
        down_payment_pct
        * 100
    )

    return AgentActionRecommendation(
        action_type=(
            ActionType.PROPOSE_PAYMENT_PLAN
        ),

        target_channel=(
            Channel.EMAIL
        ),

        message_body=(
            "Thank you for reaching out about a payment plan. "
            "Based on the current account information, a plan "
            f"of up to {duration_days} days with at least "
            f"{down_payment_percent:.0f}% as an initial "
            "payment may be considered. Final approval remains "
            "subject to account policy."
        ),

        rationale=(
            "The customer requested a payment plan. "
            "Payment history, prior promises, and the trusted "
            "risk score were retrieved before proposing terms. "
            f"The current risk band is {risk_band_value}. "
            "The proposal must pass the deterministic policy "
            "validator before any customer-facing execution."
        ),
    )


# ============================================================
# MOCK PROMISE-TO-PAY ACTION RECOMMENDER
# ============================================================

def mock_recommend_promise_to_pay_action(
    state: AgentState,
) -> AgentActionRecommendation:
    """
    Zero-cost deterministic development stand-in for the
    future LLM reasoning step for PROMISE_TO_PAY.

    The recommendation uses exact structured memory from
    get_prior_promises together with the trusted risk band.

    Development behavior:

        prior broken promise
            -> FLAG_FOR_HUMAN_CALL

        HIGH / CRITICAL risk
            -> FLAG_FOR_HUMAN_CALL

        otherwise, if email is permitted
            -> SEND_MESSAGE acknowledging the promise

        otherwise
            -> FLAG_FOR_HUMAN_CALL
    """

    promise_data = state[
        "prior_promises_evidence"
    ][
        "data"
    ]

    promises = (
        promise_data.get(
            "promises",
            [],
        )
        or []
    )

    broken_promises = [
        promise
        for promise in promises
        if str(
            promise.get(
                "status",
                "",
            )
        ).upper()
        == "BROKEN"
    ]

    broken_promise_count = len(
        broken_promises
    )

    risk = state[
        "risk"
    ]

    risk_band_value = (
        risk.band.value
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

    # ========================================================
    # CASE 1
    # PRIOR BROKEN PROMISE EXISTS
    # ========================================================

    if broken_promise_count > 0:

        return AgentActionRecommendation(
            action_type=(
                ActionType.FLAG_FOR_HUMAN_CALL
            ),

            target_channel=(
                Channel.HUMAN_CALL_FLAG
            ),

            message_body=None,

            rationale=(
                "The customer made a new promise to pay, "
                f"but structured account memory shows "
                f"{broken_promise_count} prior broken "
                "promise(s). Human follow-up is appropriate "
                "rather than treating the new promise as a "
                "routine commitment."
            ),
        )

    # ========================================================
    # CASE 2
    # HIGH OR CRITICAL RISK
    # ========================================================

    if risk_band_value in {
        "HIGH",
        "CRITICAL",
    }:

        return AgentActionRecommendation(
            action_type=(
                ActionType.FLAG_FOR_HUMAN_CALL
            ),

            target_channel=(
                Channel.HUMAN_CALL_FLAG
            ),

            message_body=None,

            rationale=(
                "The customer made a new promise to pay, "
                f"but the trusted risk band is "
                f"{risk_band_value}. Human follow-up is "
                "appropriate for this higher-risk account."
            ),
        )

    # ========================================================
    # CASE 3
    # ROUTINE ACKNOWLEDGEMENT
    # ========================================================

    if email_allowed:

        return AgentActionRecommendation(
            action_type=(
                ActionType.SEND_MESSAGE
            ),

            target_channel=(
                Channel.EMAIL
            ),

            message_body=(
                "Thank you for the update. We have noted "
                "your commitment to make the payment as "
                "described in your message."
            ),

            rationale=(
                "The customer made a promise to pay. "
                "Structured promise history contains no "
                "prior broken promises requiring additional "
                "attention, the current risk band is "
                f"{risk_band_value}, and email communication "
                "is permitted."
            ),
        )

    # ========================================================
    # CASE 4
    # NO PERMITTED EMAIL CHANNEL
    # ========================================================

    return AgentActionRecommendation(
        action_type=(
            ActionType.FLAG_FOR_HUMAN_CALL
        ),

        target_channel=(
            Channel.HUMAN_CALL_FLAG
        ),

        message_body=None,

        rationale=(
            "The customer made a promise to pay, but the "
            "account does not permit email communication. "
            "Human follow-up is required."
        ),
    )


# ============================================================
# MOCK AMOUNT-DISPUTE ACTION RECOMMENDER
# ============================================================

def mock_recommend_amount_dispute_action(
    state: AgentState,
) -> AgentActionRecommendation:
    """
    Zero-cost deterministic development stand-in for the
    future LLM reasoning step for AMOUNT_DISPUTE.

    This reasoning step uses exact structured dispute memory
    plus the trusted risk result. It deliberately does not
    enforce the disputed-amount authority threshold here;
    that is a hard policy constraint and belongs in the
    deterministic validator.

    Development behavior:

        unresolved prior amount dispute
            -> FLAG_FOR_HUMAN_CALL

        otherwise
            -> LOG_DISPUTE_AND_HOLD

    LOG_DISPUTE_AND_HOLD is an internal collections hold,
    not a service-hold action and not a customer-facing
    communication.
    """

    dispute_data = state[
        "prior_disputes_evidence"
    ][
        "data"
    ]

    disputes = (
        dispute_data.get(
            "disputes",
            [],
        )
        or []
    )

    prior_amount_disputes = [
        dispute
        for dispute in disputes
        if str(
            dispute.get(
                "dispute_type",
                "",
            )
        ).upper()
        == "AMOUNT_DISPUTE"
    ]

    unresolved_amount_disputes = [
        dispute
        for dispute in prior_amount_disputes
        if str(
            dispute.get(
                "status",
                "",
            )
        ).upper()
        not in {
            "RESOLVED",
            "CLOSED",
        }
    ]

    risk = state[
        "risk"
    ]

    risk_band_value = (
        risk.band.value
    )

    # ========================================================
    # CASE 1
    # EXISTING UNRESOLVED AMOUNT DISPUTE
    # ========================================================

    if unresolved_amount_disputes:

        return AgentActionRecommendation(
            action_type=(
                ActionType.FLAG_FOR_HUMAN_CALL
            ),

            target_channel=(
                Channel.HUMAN_CALL_FLAG
            ),

            message_body=None,

            rationale=(
                "The customer raised an amount dispute, and "
                "structured account memory shows an existing "
                "unresolved amount dispute. Human review is "
                "required before another autonomous dispute "
                "action is recorded. The trusted risk band is "
                f"{risk_band_value}."
            ),
        )

    # ========================================================
    # CASE 2
    # NEW AMOUNT DISPUTE WITH NO UNRESOLVED DUPLICATE
    # ========================================================

    resolved_count = sum(
        1
        for dispute in prior_amount_disputes
        if str(
            dispute.get(
                "status",
                "",
            )
        ).upper()
        in {
            "RESOLVED",
            "CLOSED",
        }
    )

    return AgentActionRecommendation(
        action_type=(
            ActionType.LOG_DISPUTE_AND_HOLD
        ),

        target_channel=None,

        message_body=None,

        rationale=(
            "The customer raised an amount dispute. Exact "
            "structured dispute history was retrieved before "
            "the recommendation. There are no unresolved prior "
            "amount disputes requiring immediate human review; "
            f"{resolved_count} prior resolved amount dispute(s) "
            "were found. The trusted risk band is "
            f"{risk_band_value}. Record the dispute and pause "
            "autonomous collections activity while the amount "
            "is reviewed."
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
    """
    Route supported intents into implemented vertical slices.

    Current supported slices:

        DELIVERY_DISPUTE
        ALREADY_PAID_CLAIM
        PAYMENT_PLAN_REQUEST
        PROMISE_TO_PAY

    Everything else continues to fail closed.
    """

    primary_intent = (
        state[
            "intent"
        ].primary_intent
    )

    if (
        primary_intent
        == Intent.DELIVERY_DISPUTE
    ):

        return "delivery_dispute"

    if (
        primary_intent
        == Intent.ALREADY_PAID_CLAIM
    ):

        return "already_paid_claim"

    if (
        primary_intent
        == Intent.PAYMENT_PLAN_REQUEST
    ):

        return "payment_plan_request"

    if (
        primary_intent
        == Intent.PROMISE_TO_PAY
    ):

        return "promise_to_pay"

    if (
        primary_intent
        == Intent.AMOUNT_DISPUTE
    ):

        return "amount_dispute"

    return "unsupported_intent"


# ============================================================
# NODE 2A
# GUARDED DELIVERY EVIDENCE RETRIEVAL
# ============================================================

def gather_delivery_evidence_node(
    state: AgentState,
) -> dict:
    """
    Gather required delivery evidence while enforcing
    deterministic per-decision tool limits.
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

    # ========================================================
    # TOOL 1
    # VERIFY DELIVERY
    # ========================================================

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

    # ========================================================
    # TOOL 2
    # ACCOUNT HISTORY
    # ========================================================

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

    # ========================================================
    # TOOL 3
    # RISK SCORE
    # ========================================================

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

    # ========================================================
    # BUILD TRUSTED RISK OBJECT
    # ========================================================

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
# NODE 2B
# GUARDED ALREADY-PAID EVIDENCE RETRIEVAL
# ============================================================

def gather_already_paid_evidence_node(
    state: AgentState,
) -> dict:
    """
    Gather the verified evidence required to process an
    ALREADY_PAID_CLAIM.

    Required evidence:

        reconcile_payment_claim
        account context
        risk score

    Every tool call passes through the deterministic tool
    guard and is linked to the decision_id.
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

    # ========================================================
    # TOOL 1
    # RECONCILE PAYMENT CLAIM
    # ========================================================

    payment_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "reconcile_payment_claim"
            ),

            arguments={
                "invoice_id":
                    state[
                        "invoice_id"
                    ]
            },

            tool_function=(
                reconcile_payment_claim
            ),
        )
    )

    update[
        "payment_evidence"
    ] = payment_result

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
        payment_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: "
            "reconcile_payment_claim "
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

    # ========================================================
    # TOOL 2
    # ACCOUNT CONTEXT
    # ========================================================

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

    # ========================================================
    # TOOL 3
    # TRUSTED RISK SCORE
    # ========================================================

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

    # ========================================================
    # BUILD TRUSTED RISK OBJECT
    # ========================================================

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
# NODE 2C
# GUARDED PAYMENT-PLAN EVIDENCE RETRIEVAL
# ============================================================

def gather_payment_plan_evidence_node(
    state: AgentState,
) -> dict:
    """
    Gather evidence required for PAYMENT_PLAN_REQUEST.

    Required evidence:
        get_payment_history
        get_risk_score

    Additional structured context:
        get_prior_promises
        get_account_history

    Every tool call passes through the deterministic tool guard
    and is linked to the current decision_id.
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

    # ========================================================
    # TOOL 1
    # PAYMENT HISTORY
    # ========================================================

    payment_history_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "get_payment_history"
            ),

            arguments={
                "account_id":
                    state[
                        "account_id"
                    ]
            },

            tool_function=(
                get_payment_history
            ),
        )
    )

    update[
        "payment_history_evidence"
    ] = payment_history_result

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
        payment_history_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: get_payment_history "
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

    # ========================================================
    # TOOL 2
    # PRIOR PROMISES
    # ========================================================

    prior_promises_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "get_prior_promises"
            ),

            arguments={
                "account_id":
                    state[
                        "account_id"
                    ]
            },

            tool_function=(
                get_prior_promises
            ),
        )
    )

    update[
        "prior_promises_evidence"
    ] = prior_promises_result

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
        prior_promises_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: get_prior_promises "
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

    # ========================================================
    # TOOL 3
    # ACCOUNT CONTEXT
    # ========================================================

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
            "FR-2.7: get_account_history "
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

    # ========================================================
    # TOOL 4
    # TRUSTED RISK SCORE
    # ========================================================

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
            "FR-2.7: get_risk_score "
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

    # ========================================================
    # BUILD TRUSTED RISK OBJECT
    # ========================================================

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
# NODE 2D
# GUARDED PROMISE-TO-PAY EVIDENCE RETRIEVAL
# ============================================================

def gather_promise_to_pay_evidence_node(
    state: AgentState,
) -> dict:
    """
    Gather evidence required for PROMISE_TO_PAY.

    Required evidence:

        get_prior_promises
        get_risk_score

    Additional structured context:

        get_account_history

    Every tool invocation passes through the deterministic
    tool guard and is tied to the current decision_id.
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

    # ========================================================
    # TOOL 1
    # PRIOR PROMISE MEMORY
    # ========================================================

    prior_promises_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "get_prior_promises"
            ),

            arguments={
                "account_id":
                    state[
                        "account_id"
                    ]
            },

            tool_function=(
                get_prior_promises
            ),
        )
    )

    update[
        "prior_promises_evidence"
    ] = prior_promises_result

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
        prior_promises_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: get_prior_promises "
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

    # ========================================================
    # TOOL 2
    # ACCOUNT CONTEXT
    # ========================================================

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
            "FR-2.7: get_account_history "
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

    # ========================================================
    # TOOL 3
    # TRUSTED RISK SCORE
    # ========================================================

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
            "FR-2.7: get_risk_score "
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

    # ========================================================
    # BUILD TRUSTED RISK OBJECT
    # ========================================================

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
# NODE 2E
# GUARDED AMOUNT-DISPUTE EVIDENCE RETRIEVAL
# ============================================================

def gather_amount_dispute_evidence_node(
    state: AgentState,
) -> dict:
    """
    Gather evidence required for AMOUNT_DISPUTE.

    Required structured memory/context:

        get_prior_disputes
        get_account_history
        get_risk_score

    Exact relational dispute history is retrieved before the
    recommender reasons about whether the new dispute can be
    logged and held or requires human review.

    Every tool invocation passes through the deterministic
    tool guard and is tied to the current decision_id.
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

    # ========================================================
    # TOOL 1
    # PRIOR DISPUTE MEMORY
    # ========================================================

    prior_disputes_result, violation = (
        execute_guarded_tool(
            guard=guard,

            tool_name=(
                "get_prior_disputes"
            ),

            arguments={
                "account_id":
                    state[
                        "account_id"
                    ]
            },

            tool_function=(
                get_prior_disputes
            ),
        )
    )

    update[
        "prior_disputes_evidence"
    ] = prior_disputes_result

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
        prior_disputes_result[
            "status"
        ]
        != "SUCCESS"
    ):

        update[
            "forced_escalation_reason"
        ] = (
            "FR-2.7: get_prior_disputes "
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

    # ========================================================
    # TOOL 2
    # ACCOUNT CONTEXT
    # ========================================================

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
            "FR-2.7: get_account_history "
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

    # ========================================================
    # TOOL 3
    # TRUSTED RISK SCORE
    # ========================================================

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
            "FR-2.7: get_risk_score "
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

    # ========================================================
    # BUILD TRUSTED RISK OBJECT
    # ========================================================

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
    """
    Produce the action recommendation for whichever supported
    vertical slice is active.

    The reasoning layer chooses:
        action
        channel
        message
        rationale

    Application code supplies trusted:
        evidence IDs
        risk score
        risk band
        policy version
        payment-plan terms where applicable
    """

    primary_intent = (
        state[
            "intent"
        ].primary_intent
    )

    risk = state[
        "risk"
    ]

    payment_plan_duration_days = None
    payment_plan_down_payment_pct = None

    # ========================================================
    # DELIVERY DISPUTE
    # ========================================================

    if (
        primary_intent
        == Intent.DELIVERY_DISPUTE
    ):

        recommendation = (
            mock_recommend_delivery_action(
                state
            )
        )

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

    # ========================================================
    # ALREADY PAID CLAIM
    # ========================================================

    elif (
        primary_intent
        == Intent.ALREADY_PAID_CLAIM
    ):

        recommendation = (
            mock_recommend_already_paid_action(
                state
            )
        )

        tool_call_ids = [
            state[
                "payment_evidence"
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

    # ========================================================
    # PAYMENT PLAN REQUEST
    # ========================================================

    elif (
        primary_intent
        == Intent.PAYMENT_PLAN_REQUEST
    ):

        recommendation = (
            mock_recommend_payment_plan_action(
                state
            )
        )

        tool_call_ids = [
            state[
                "payment_history_evidence"
            ][
                "tool_call_id"
            ],

            state[
                "prior_promises_evidence"
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

        if (
            recommendation.action_type
            == ActionType.PROPOSE_PAYMENT_PLAN
        ):

            (
                payment_plan_duration_days,
                payment_plan_down_payment_pct,
            ) = (
                get_development_payment_plan_terms(
                    risk.band.value
                )
            )

    # ========================================================
    # PROMISE TO PAY
    # ========================================================

    elif (
        primary_intent
        == Intent.PROMISE_TO_PAY
    ):

        recommendation = (
            mock_recommend_promise_to_pay_action(
                state
            )
        )

        tool_call_ids = [
            state[
                "prior_promises_evidence"
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

    # ========================================================
    # AMOUNT DISPUTE
    # ========================================================

    elif (
        primary_intent
        == Intent.AMOUNT_DISPUTE
    ):

        recommendation = (
            mock_recommend_amount_dispute_action(
                state
            )
        )

        tool_call_ids = [
            state[
                "prior_disputes_evidence"
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

    # ========================================================
    # DEFENSIVE FAIL CLOSED
    # ========================================================

    else:

        raise RuntimeError(
            "propose_action_node received an "
            "unsupported intent."
        )

    policy = load_policy()

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

        payment_plan_duration_days=(
            payment_plan_duration_days
        ),

        payment_plan_down_payment_pct=(
            payment_plan_down_payment_pct
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

    invoice_records = state[
        "account_evidence"
    ][
        "data"
    ].get(
        "invoices",
        [],
    )

    ledger_amount = next(
        (
            float(invoice["amount"])
            for invoice in invoice_records
            if int(invoice["invoice_id"])
            == int(state["invoice_id"])
            and invoice.get("amount") is not None
        ),
        None,
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

        ledger_amount=(
            ledger_amount
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

    Current development rule:

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

    # ========================================================
    # SAFE REVISION RULE
    # PR-4.1
    # ========================================================

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

    # ========================================================
    # NO SAFE AUTOMATIC REVISION EXISTS
    # ========================================================

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
                f"implemented in the current "
                f"ACA development build."
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
        "gather_already_paid_evidence",
        gather_already_paid_evidence_node,
    )

    builder.add_node(
        "gather_payment_plan_evidence",
        gather_payment_plan_evidence_node,
    )

    builder.add_node(
        "gather_promise_to_pay_evidence",
        gather_promise_to_pay_evidence_node,
    )

    builder.add_node(
        "gather_amount_dispute_evidence",
        gather_amount_dispute_evidence_node,
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

            "already_paid_claim":
                "gather_already_paid_evidence",

            "payment_plan_request":
                "gather_payment_plan_evidence",

            "promise_to_pay":
                "gather_promise_to_pay_evidence",

            "amount_dispute":
                "gather_amount_dispute_evidence",

            "unsupported_intent":
                "unsupported_intent",
        },
    )

    # ========================================================
    # EVIDENCE ROUTES
    # ========================================================

    for evidence_node in (
        "gather_delivery_evidence",
        "gather_already_paid_evidence",
        "gather_payment_plan_evidence",
        "gather_promise_to_pay_evidence",
        "gather_amount_dispute_evidence",
    ):
        builder.add_conditional_edges(
            evidence_node,
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
    # VALIDATION ROUTE
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
    # FINAL ROUTES -> AUDIT PERSISTENCE
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
