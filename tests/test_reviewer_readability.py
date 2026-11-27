"""FR-6.4 proxies for a nontechnical review packet.

These checks do not claim a person has rated the prose. They check
that the brief has the required sections, that every code on the page
has a plain-English gloss, that the brief is not a JSON dump, and that
the Flesch-Kincaid grade of the agent-written sentences stays at or
below the documented limit.
"""

from src.agent import run_aca
from src.evaluation import cleanup_decision
from src.readability import REVIEWER_GRADE_LIMIT, flesch_kincaid_grade
from src.reviewer_brief import (
    SECTION_HEADINGS,
    assess_reviewer_brief,
    build_reviewer_brief,
)
from demo.seed import build_demo_database
from demo.synthetic_cases import build_synthetic_cases


def test_grade_limit_is_the_plain_language_ceiling():
    assert REVIEWER_GRADE_LIMIT == 8.0


def test_easy_prose_is_under_the_limit_and_dense_prose_is_not():
    easy = (
        "The customer asked to pay over time. "
        "The agent stopped. A person must decide."
    )
    dense = (
        "The autonomous recommendation was programmatically invalidated because "
        "the deterministic authorization subsystem identified a noncompliant "
        "representation regarding unauthorized consequential enforcement activity. "
        "Subsequent operationalization requires supervisory adjudication."
    )
    assert flesch_kincaid_grade(easy) <= REVIEWER_GRADE_LIMIT
    assert flesch_kincaid_grade(dense) > REVIEWER_GRADE_LIMIT


def test_proxy_rejects_a_json_blob_and_a_missing_section():
    brief = build_reviewer_brief(
        {
            "reply_text": "Hello.",
            "final_reason": "Stopped.",
        }
    )
    broken = {
        "sections": brief["sections"],
        "plain_text": brief["plain_text"].replace(
            SECTION_HEADINGS[0], "Internal dump"
        )
        + ' {"error": null}',
    }
    report = assess_reviewer_brief(broken)
    assert report["ok"] is False
    assert any("missing section" in item or "empty section" in item for item in report["problems"])
    assert any("json" in item or "null" in item for item in report["problems"])


def test_synthetic_escalation_packets_meet_readability_proxies(tmp_path, monkeypatch):
    database = tmp_path / "readability.db"
    monkeypatch.setenv("CLEARTIDE_DB_PATH", str(database))
    build_demo_database(database)

    cases = [
        case
        for case in build_synthetic_cases()
        if case["expected_final_status"] == "ESCALATE"
    ]
    archetypes = {case["archetype"] for case in cases}
    assert len(cases) >= 40
    assert archetypes >= {
        "unclear_inquiry",
        "payment_plan_medium_risk",
        "amount_dispute_ambiguous",
        "hostile_or_legal",
        "email_opt_out",
        "unsafe_draft_blocked",
    }

    grades = []
    try:
        for case in cases:
            result = run_aca(
                account_id=case["account_id"],
                invoice_id=case["invoice_id"],
                reply_text=case["reply_text"],
                injected_message_body=case.get("injected_message_body"),
            )
            assert result["final_status"] == "ESCALATE", case["case_id"]
            packet = result["escalation_packet"]
            brief = packet.reviewer_brief
            report = assess_reviewer_brief(brief)
            assert report["ok"], (case["case_id"], case["archetype"], report)
            assert case["reply_text"] in brief["plain_text"]
            grades.append(report["grade"])
            cleanup_decision(result["decision_id"])
    finally:
        monkeypatch.undo()

    assert grades
    assert max(grades) <= REVIEWER_GRADE_LIMIT
