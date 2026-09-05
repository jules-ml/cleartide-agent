from src.agent import (
    DEVELOPMENT_REASONING_MODE,
    run_aca,
)


def separator():
    print()
    print("=" * 72)
    print()


def main():

    separator()

    print(
        "CLEARTIDE ACA - STEP 8 "
        "ZERO-COST VERTICAL SLICE"
    )

    print(
        "Reasoning mode:",
        DEVELOPMENT_REASONING_MODE,
    )

    separator()

    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text=(
    "We never received invoice 5001. "
    "Can you send it again?"
    ),
    )

    # ========================================================
    # 1. INTENT
    # ========================================================

    intent = result[
        "intent"
    ]

    print(
        "1. INTENT CLASSIFICATION"
    )

    print(
        "Primary intent:",
        intent.primary_intent.value,
    )

    print(
        "Confidence:",
        intent.confidence,
    )

    print(
        "Secondary intents:",
        [
            item.value
            for item
            in intent.secondary_intents
        ],
    )

    separator()

    # ========================================================
    # 2. DELIVERY EVIDENCE
    # ========================================================

    if (
        "delivery_evidence"
        in result
    ):

        delivery = result[
            "delivery_evidence"
        ]

        print(
            "2. DELIVERY EVIDENCE"
        )

        print(
            "Tool call:",
            delivery[
                "tool_call_id"
            ],
        )

        print(
            "Tool:",
            delivery[
                "tool_name"
            ],
        )

        print(
            "Status:",
            delivery[
                "status"
            ],
        )

        print(
            "Was delivered:",
            delivery[
                "data"
            ].get(
                "was_delivered"
            ),
        )

        latest = (
            delivery[
                "data"
            ].get(
                "latest_delivery_event"
            )
        )

        if latest:

            print(
                "Delivery status:",
                latest.get(
                    "delivery_status"
                ),
            )

            print(
                "Failure reason:",
                latest.get(
                    "failure_reason"
                ),
            )

    separator()

    # ========================================================
    # 3. RISK
    # ========================================================

    if "risk" in result:

        risk = result[
            "risk"
        ]

        print(
            "3. TRUSTED RISK RESULT"
        )

        print(
            "Score:",
            risk.score,
        )

        print(
            "Band:",
            risk.band.value,
        )

        print(
            "Model version:",
            risk.model_version,
        )

        print(
            "Contributing factors:",
            risk.contributing_factors,
        )

    separator()

    # ========================================================
    # 4. PROPOSED ACTION
    # ========================================================

    if (
        "proposed_action"
        in result
    ):

        proposal = result[
            "proposed_action"
        ]

        print(
            "4. ACTION RECOMMENDATION"
        )

        print(
            "Action:",
            proposal.action_type.value,
        )

        print(
            "Channel:",
            (
                proposal.target_channel.value
                if proposal.target_channel
                else None
            ),
        )

        print(
            "Message:",
            proposal.message_body,
        )

        print(
            "Rationale:",
            proposal.rationale,
        )

        print(
            "Tool calls relied upon:",
            proposal.tool_call_ids,
        )

        print(
            "Trusted risk score:",
            proposal.risk_score,
        )

        print(
            "Risk band:",
            proposal.risk_band.value,
        )

        print(
            "Policy version:",
            proposal.policy_version,
        )

    separator()

    # ========================================================
    # 5. POLICY
    # ========================================================

    if (
        "validation"
        in result
    ):

        validation = result[
            "validation"
        ]

        print(
            "5. POLICY VALIDATOR"
        )

        print(
            "Outcome:",
            validation.outcome.value,
        )

        print(
            "Violated constraints:",
            validation.violated_constraints,
        )

        print(
            "Explanation:",
            validation.explanation,
        )

    separator()

    # ========================================================
    # 6. FINAL RESULT
    # ========================================================

    print(
        "6. FINAL DECISION"
    )

    print(
        "Status:",
        result[
            "final_status"
        ],
    )

    print(
        "Action:",
        result[
            "final_action_type"
        ].value,
    )

    print(
        "Reason:",
        result[
            "final_reason"
        ],
    )

    separator()


if __name__ == "__main__":
    main()