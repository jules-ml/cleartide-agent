"""Streamlit Community Cloud entry point for the class demo.

The database is created on startup. No seed command, secret, or API key
is required. Business rules stay in src/ and demo/.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _bind_database() -> Path:
    raw = os.environ.get("CLEARTIDE_STREAMLIT_DB")
    path = Path(raw) if raw else ROOT / "data" / "streamlit_demo.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["CLEARTIDE_DB_PATH"] = str(path.resolve())
    return path.resolve()


DB_PATH = _bind_database()

import streamlit as st

st.set_page_config(
    page_title="Cleartide ACA",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from demo.runner import run_scenario, scenario_by_id
from demo.seed import build_demo_database
from demo.server import list_decisions
from src.audit import (
    AuditImmutableError,
    attempt_audit_rewrite,
    get_complete_audit_record,
)
from src.database import forget_schema_cache
from src.review import DISPOSITIONS, HumanReviewError, record_human_disposition

EVAL_PATH = ROOT / "evals" / "synthetic_results.json"
TRACE_PATH = ROOT / "docs" / "traceability_results.json"

VIEWS = (
    "01 Overview",
    "02 Autonomous",
    "03 Human review",
    "04 Policy block",
    "05 Audit trail",
    "06 Evaluation",
    "07 Traceability",
)

SCENARIO_BY_VIEW = {
    "02 Autonomous": "autonomous_promise",
    "03 Human review": "human_review_payment_plan",
    "04 Policy block": "blocked_policy_violation",
}


@st.cache_resource
def ensure_demo_database(db_path: str) -> str:
    """Build the isolated demo database once per server process."""

    os.environ["CLEARTIDE_DB_PATH"] = db_path
    forget_schema_cache(db_path)
    build_demo_database(Path(db_path))
    return db_path


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _reset_demo() -> None:
    forget_schema_cache(DB_PATH)
    ensure_demo_database.clear()
    st.session_state.clear()
    st.rerun()


def _run_and_store(scenario_id: str) -> dict:
    os.environ["CLEARTIDE_DB_PATH"] = str(DB_PATH)
    view = run_scenario(scenario_by_id(scenario_id))
    st.session_state.setdefault("results", {})[scenario_id] = view
    return view


def _render_result(view: dict) -> None:
    columns = st.columns(4)
    columns[0].metric("Intent", view.get("intent") or "—")
    columns[1].metric("Risk", f"{view.get('risk_band') or '—'} {view.get('risk_score') or ''}".strip())
    columns[2].metric("Verdict", view.get("verdict") or "—")
    columns[3].metric("Outcome", "Sent" if view.get("executed") else "Not sent")

    left, right = st.columns(2)
    with left:
        st.subheader("Customer")
        st.write(f"“{view.get('reply_text') or ''}”")
        st.caption(f"Account {view.get('account_id')} · Invoice {view.get('invoice_id')}")
        if view.get("injected_message_body"):
            st.markdown("**Injected agent draft**")
            st.write(view["injected_message_body"])
        if view.get("rationale"):
            st.markdown("**Rationale**")
            st.write(view["rationale"])
    with right:
        st.subheader("Governance")
        rules = ", ".join(view.get("violated_constraints") or []) or "none"
        fields = ", ".join(view.get("violated_fields") or []) or "none"
        st.write(f"**Rule** {rules}")
        st.write(f"**Fields** {fields}")
        st.write(view.get("policy_explanation") or "")
        st.write(
            f"**Final** {view.get('final_status')} / {view.get('final_action')}"
        )
        st.write(f"**Revisions** {view.get('revision_count') or 0}")
        if view.get("revision_reason"):
            st.caption(view["revision_reason"])
        tool_lines = [
            f"{tool.get('tool')}  {tool.get('status')}  {tool.get('highlights') or ''}".rstrip()
            for tool in view.get("tools") or []
        ]
        st.markdown("**Tools and evidence**")
        st.code("\n".join(tool_lines) or "No tools", language=None)
        if view.get("message_draft"):
            st.markdown("**Draft**")
            st.text(view["message_draft"])

    brief = view.get("reviewer_brief") or {}
    sections = brief.get("sections") or []
    if sections:
        st.subheader("Reviewer packet")
        for section in sections:
            st.markdown(f"**{section['heading']}**")
            st.write(section.get("body") or "")
        st.caption(
            f"Reading grade {brief.get('grade')} · limit {brief.get('grade_limit')}. "
            "Quotes are not scored. This grade is a proxy for a human reader."
        )

    card = view.get("policy_card")
    if card:
        st.subheader("Policy source")
        st.write(card.get("statement") or "")
        st.caption(
            f"{card.get('source_file')} · enforced by {card.get('enforced_by')} "
            f"· version {card.get('policy_version')}"
        )
        st.json(card.get("excerpt") or {})

    timeline = ((view.get("audit") or {}).get("timeline")) or []
    if timeline:
        st.subheader(f"Audit timeline · decision {view.get('decision_id')}")
        for step in timeline:
            st.markdown(f"**{step['step']}.** {step['detail']}")


def _scenario_panel(scenario_id: str, *, run_key: str) -> None:
    scenario = scenario_by_id(scenario_id)
    st.header(scenario["title"])
    st.write(scenario.get("story") or "")
    if st.button("Run this scenario", key=run_key, type="primary"):
        with st.spinner("Running the agent…"):
            _run_and_store(scenario_id)
    view = (st.session_state.get("results") or {}).get(scenario_id)
    if view:
        _render_result(view)


def _page_overview() -> None:
    st.header("Collections needs judgment. It also needs a harness.")
    st.write(
        "A roll-off customer can say “I’ll pay the invoice on Friday,” "
        "“I already paid this last week,” or “I can’t pay everything today. "
        "Can I make payments?” Cleartide classifies that reply, pulls the "
        "ledger, and recommends a next step. It cannot send, promise, or "
        "threaten anything the deterministic policy does not allow."
    )
    first, second, third = st.columns(3)
    first.subheader("The agent reasons")
    first.write(
        "Intent selects the tools. The draft is written from retrieved "
        "evidence, not from the customer’s sentence alone."
    )
    second.subheader("Authority is separate")
    second.write(
        "config/policy.yaml holds the limits. src/policy.py is the final "
        "authority. The recommender does not get a vote on consent, quiet "
        "hours, or threats."
    )
    third.subheader("The record stays")
    third.write(
        "Every decision is finalized once. A human disposition is appended. "
        "The original decision is not rewritten."
    )
    st.subheader("Decision path")
    labels = st.columns(7)
    for column, name in zip(
        labels,
        ("Reply", "Intent", "Tools", "Risk", "Recommend", "Policy", "Audit"),
    ):
        column.info(name)
    st.caption(
        "Policy either allows the step or hands it to a person. Both end in "
        "the audit. The branching diagram is in docs/architecture.md."
    )
    st.subheader("Also in this demo")
    st.caption("Tabs 02, 03, and 04 are the walkthrough. These two are extra.")
    paid, quiet = st.columns(2)
    if paid.button("4. Already paid, ledger checked", key="run-paid"):
        with st.spinner("Running the agent…"):
            _run_and_store("already_paid_evidence")
    if quiet.button("5. Quiet hours, revise to email", key="run-quiet"):
        with st.spinner("Running the agent…"):
            _run_and_store("sms_quiet_hours_revision")
    for scenario_id in ("already_paid_evidence", "sms_quiet_hours_revision"):
        view = (st.session_state.get("results") or {}).get(scenario_id)
        if view:
            st.divider()
            st.markdown(f"**{view['title']}**")
            _render_result(view)


def _page_review() -> None:
    scenario_id = "human_review_payment_plan"
    _scenario_panel(scenario_id, run_key="run-review")
    view = (st.session_state.get("results") or {}).get(scenario_id)
    if not view or not view.get("escalation_id"):
        return
    st.subheader("Reviewer action")
    st.caption(
        f"Escalation {view['escalation_id']}. "
        "This writes an audit note. It does not edit the decision."
    )
    note = st.text_input("Note for the account memory", key="review-note")
    buttons = st.columns(len(DISPOSITIONS))
    for column, code in zip(buttons, DISPOSITIONS):
        if column.button(code, key=f"disp-{code}"):
            try:
                recorded = record_human_disposition(
                    int(view["escalation_id"]),
                    code,
                    reviewer_note=note,
                    reviewed_by="class-reviewer",
                )
                st.session_state["review_message"] = (
                    f"Recorded {recorded['disposition_code']} on escalation "
                    f"{recorded['escalation_id']}. An audit note was appended. "
                    "The original decision row was not rewritten."
                )
            except HumanReviewError as exc:
                st.session_state["review_message"] = str(exc)
    if st.session_state.get("review_message"):
        st.info(st.session_state["review_message"])
    if st.button(
        "Run the account again and show the memory",
        key="rerun-review",
    ):
        with st.spinner("Running the agent…"):
            _run_and_store(scenario_id)
        st.rerun()


def _page_audit() -> None:
    st.header("Finalized decisions stay put.")
    st.write(
        "A completed decision cannot be rewritten through the application. "
        "Human review adds a note beside it."
    )
    decisions = list_decisions()
    if not decisions:
        st.info("No decisions yet. Run a scenario, then come back.")
        return
    labels = [
        f"{row['decision_id']} · {row['primary_intent']} · {row['final_action']}"
        for row in decisions
    ]
    choice = st.selectbox("Decision", labels, key="audit-choice")
    decision_id = int(choice.split(" · ", 1)[0])
    record = get_complete_audit_record(decision_id)
    if not record:
        st.warning("That decision has no audit record.")
        return
    decision = record.get("decision") or {}
    st.caption(
        f"Decision {decision_id} · {decision.get('audit_status')} · "
        f"policy {decision.get('policy_version')}"
    )
    st.write(decision.get("final_reason") or "")
    for step in record.get("timeline") or []:
        st.markdown(f"**{step['step']}.** {step['detail']}")
    if st.button("Attempt to rewrite this record", key="rewrite-audit"):
        try:
            attempt_audit_rewrite(
                decision_id,
                {"final_reason": "tampered during the demo"},
            )
        except AuditImmutableError as exc:
            st.error(str(exc))


def _page_evaluation() -> None:
    st.header("Synthetic evaluation")
    payload = _load_json(EVAL_PATH) or {}
    summary = payload.get("summary") or {}
    st.write(
        f"{summary.get('total_cases', '—')} labeled cases, run by the code."
    )
    st.info(
        "These numbers are measured against the deterministic agent’s own "
        "labels. They are not a live-model benchmark and they are not "
        "business results."
    )
    if not summary:
        st.warning("evals/synthetic_results.json is not in this checkout.")
        return
    metrics = (
        ("decision_accuracy", "Decision accuracy"),
        ("policy_compliance_rate", "Policy compliance"),
        ("policy_violation_rate", "Policy-violation rate"),
        ("escalation_accuracy", "Escalation accuracy"),
        ("escalation_precision", "Escalation precision"),
        ("escalation_recall", "Escalation recall"),
        ("failure_handling_rate", "Failure handling"),
        ("intent_accuracy", "Intent accuracy"),
        ("action_accuracy", "Action accuracy"),
        ("channel_accuracy", "Channel accuracy"),
    )
    columns = st.columns(5)
    for index, (key, label) in enumerate(metrics):
        columns[index % 5].metric(label, _pct(summary.get(key)))
    reading = summary.get("reviewer_readability") or {}
    if reading:
        st.caption(
            f"Reviewer packets: {reading.get('packets')}. "
            f"Reading grade mean {reading.get('mean_grade')}, "
            f"max {reading.get('max_grade')}, "
            f"limit {reading.get('grade_limit')}. "
            f"Briefs over the limit: {reading.get('briefs_failing_proxy')}. "
            "Quotes are not scored."
        )


def _page_traceability() -> None:
    st.header("Each requirement points at code and a test that ran.")
    st.write(
        "Generated from pytest, not from a status someone typed. "
        "A row passes only when every mapped test passed in that run. "
        "FR-6.4 uses proxies for a human reading: required sections, "
        "a plain gloss for every code, no JSON in the brief, and a "
        "Flesch-Kincaid grade at or below 8."
    )
    payload = _load_json(TRACE_PATH) or {}
    rows = [
        row
        for row in payload.get("requirements") or []
        if str(row.get("requirement_id", "")).startswith("FR-")
    ]
    if not rows:
        st.warning("docs/traceability_results.json is not in this checkout.")
        return
    st.dataframe(
        [
            {
                "Requirement": row["requirement_id"],
                "Summary": row["requirement_summary"],
                "Result": row["result"],
                "Tests": ", ".join((row.get("passed_tests") or [])[:4]),
            }
            for row in rows
        ],
        hide_index=True,
        width="stretch",
    )


def main() -> None:
    ensure_demo_database(str(DB_PATH))
    st.sidebar.title("Cleartide ACA")
    st.sidebar.caption(
        "The agent recommends. Policy decides. Every step is audited."
    )
    choice = st.sidebar.radio("Walkthrough", VIEWS, key="walkthrough")
    if st.sidebar.button("Reset demo", key="reset-demo"):
        _reset_demo()
    st.sidebar.caption(
        "Reset rebuilds the demo database for this server. "
        "Reviewer notes stay until then."
    )

    if choice == "01 Overview":
        _page_overview()
    elif choice == "03 Human review":
        _page_review()
    elif choice == "05 Audit trail":
        _page_audit()
    elif choice == "06 Evaluation":
        _page_evaluation()
    elif choice == "07 Traceability":
        _page_traceability()
    else:
        scenario_id = SCENARIO_BY_VIEW[choice]
        run_key = "run-autonomous" if "Autonomous" in choice else "run-blocked"
        _scenario_panel(scenario_id, run_key=run_key)


main()
