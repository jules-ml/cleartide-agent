from src.evaluation import (
    evaluate_suite,
    load_golden_cases,
    write_results,
)


def pct(value):
    """
    Format decimal metric as a percentage.
    """

    if value is None:
        return "N/A"

    return f"{value * 100:.1f}%"


def separator():
    print()
    print("=" * 72)
    print()


def main():

    cases = load_golden_cases(
        active_only=True
    )

    print()
    print(
        "CLEARTIDE ACA - STEP 10 "
        "DEVELOPMENT EVALUATION"
    )

    print(
        "Active golden cases:",
        len(cases),
    )

    separator()

    results, summary = (
        evaluate_suite(
            cases,
            cleanup=False,
        )
    )

    # ========================================================
    # CASE RESULTS
    # ========================================================

    for result in results:

        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        print(
            f'{result["case_id"]}: '
            f'{status}'
        )

        print(
            "  Intent:",
            result[
                "actual_intent"
            ],
        )

        print(
            "  Final action:",
            result[
                "actual_final_action"
            ],
        )

        print(
            "  Tools:",
            result[
                "actual_tools"
            ],
        )

        if (
            result[
                "missing_required_tools"
            ]
        ):

            print(
                "  Missing required tools:",
                result[
                    "missing_required_tools"
                ],
            )

        if (
            result[
                "unexpected_tools"
            ]
        ):

            print(
                "  Unexpected tools:",
                result[
                    "unexpected_tools"
                ],
            )

        print()

    separator()

    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        "STEP 10 SUMMARY"
    )

    print()

    print(
        "Cases:",
        summary[
            "total_cases"
        ],
    )

    print(
        "Intent accuracy:",
        pct(
            summary[
                "intent_accuracy"
            ]
        ),
    )

    print(
        "Action accuracy:",
        pct(
            summary[
                "action_accuracy"
            ]
        ),
    )

    print(
        "Status accuracy:",
        pct(
            summary[
                "status_accuracy"
            ]
        ),
    )

    print(
        "Required-tool compliance:",
        pct(
            summary[
                "required_tool_compliance"
            ]
        ),
    )

    print(
        "Tool precision:",
        pct(
            summary[
                "tool_precision_rate"
            ]
        ),
    )

    print(
        "Minimum-sufficient trajectory:",
        pct(
            summary[
                "minimum_sufficient_rate"
            ]
        ),
    )

    print(
        "Policy safety:",
        pct(
            summary[
                "policy_safety_rate"
            ]
        ),
    )

    print(
        "Hard policy violations:",
        summary[
            "hard_policy_violations"
        ],
    )

    print(
        "Overall pass rate:",
        pct(
            summary[
                "overall_pass_rate"
            ]
        ),
    )

    separator()

    output_path = write_results(
        results,
        summary,
    )

    print(
        "Machine-readable results written to:"
    )

    print(
        output_path
    )

    print()


if __name__ == "__main__":
    main()