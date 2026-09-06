import csv

from pathlib import Path

from src.evaluation import (
    evaluate_suite,
    load_golden_cases,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)


# ============================================================
# TEST 1
# GOLDEN DATASET STRUCTURE
# ============================================================

def test_golden_dataset_contains_all_intents():

    cases = load_golden_cases(
        active_only=False
    )

    intents = {
        case[
            "expected_intent"
        ]
        for case in cases
    }

    required_intents = {
        "DELIVERY_DISPUTE",
        "PAYMENT_PLAN_REQUEST",
        "ALREADY_PAID_CLAIM",
        "PROMISE_TO_PAY",
        "AMOUNT_DISPUTE",
        "HOSTILE_OR_ADVERSARIAL",
        "UNCLEAR",
    }

    assert (
        required_intents
        <= intents
    )


# ============================================================
# TEST 2
# DEVELOPMENT LABELS ARE NOT MISREPRESENTED
# ============================================================

def test_seed_cases_are_marked_not_human_reviewed():

    cases = load_golden_cases(
        active_only=False
    )

    for case in cases:

        assert (
            case[
                "label_status"
            ]
            == "DEVELOPMENT_SEED"
        )

        assert (
            case[
                "human_reviewed"
            ]
            is False
        )


# ============================================================
# TEST 3
# CURRENT ACTIVE REGRESSION SUITE
# ============================================================

def test_active_golden_cases_pass():

    cases = load_golden_cases(
        active_only=True
    )

    assert len(cases) >= 4

    results, summary = (
        evaluate_suite(
            cases,
            cleanup=True,
        )
    )

    failed = [
        result
        for result in results
        if not result[
            "passed"
        ]
    ]

    assert (
        failed
        == []
    )

    assert (
        summary[
            "intent_accuracy"
        ]
        == 1.0
    )

    assert (
        summary[
            "required_tool_compliance"
        ]
        == 1.0
    )

    assert (
        summary[
            "hard_policy_violations"
        ]
        == 0
    )


# ============================================================
# TEST 4
# TRACEABILITY MATRIX STRUCTURE
# ============================================================

def test_traceability_matrix_has_required_structure():

    path = (
        ROOT_DIR
        / "docs"
        / "requirements_traceability.csv"
    )

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        rows = list(
            csv.DictReader(
                file
            )
        )

    assert len(rows) > 0

    required_columns = {
        "requirement_id",
        "category",
        "requirement_summary",
        "implementation_artifact",
        "verification_artifact",
        "status",
        "notes",
    }

    assert (
        required_columns
        <= set(
            rows[0].keys()
        )
    )

    requirement_ids = [
        row[
            "requirement_id"
        ]
        for row in rows
    ]

    assert (
        len(
            requirement_ids
        )
        == len(
            set(
                requirement_ids
            )
        )
    )

    required_core_ids = {
        "FR-1.1",
        "FR-2.8",
        "FR-5.6",
        "GV-5",
    }

    assert (
        required_core_ids
        <= set(
            requirement_ids
        )
    )