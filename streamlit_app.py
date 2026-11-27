"""Streamlit Community Cloud entry point for the live collections console.

The database is created on startup. No seed command, secret, or API key
is required. Business rules stay in src/ and demo/.
"""

import json
import os
import time
from datetime import datetime
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
    initial_sidebar_state="collapsed",
)

import plotly.graph_objects as go

from demo.console import (
    apply_approved_outcome,
    decision_label,
    evidence_blocks,
    inbox_items,
    policy_readout,
    portfolio_frames,
    recent_audits,
    session_ops,
    work_queue,
)
from demo.runner import run_scenario, scenario_by_id
from demo.seed import apply_streamlit_book_spread, build_demo_database
from src.agent import run_aca
from src.audit import AuditImmutableError, attempt_audit_rewrite, get_complete_audit_record
from src.database import forget_schema_cache
from src.policy import load_policy
from src.readability import flesch_kincaid_grade
from src.review import DISPOSITIONS, HumanReviewError, record_human_disposition
from demo.present import present_decision
from demo.runner import policy_card

EVAL_PATH = ROOT / "evals" / "synthetic_results.json"
TRACE_PATH = ROOT / "docs" / "traceability_results.json"

VIEWS = (
    "Live Agent Console",
    "Reviewer Inbox",
    "Audit Trail",
    "Evaluation",
    "Traceability",
    "Policy",
    "Guided walkthrough",
)

STAGES = ("Intent", "Tools", "Risk", "Recommend", "Policy", "Audit")

SHORT_VIEWS = {
    "Live Agent Console": "Console",
    "Reviewer Inbox": "Inbox",
    "Audit Trail": "Audit",
    "Evaluation": "Eval",
    "Traceability": "Trace",
    "Policy": "Policy",
    "Guided walkthrough": "Guide",
}

MOMENTS = (
    {
        "key": "moment-promise",
        "label": "Promise to pay → approve",
        "account_id": 8801001,
        "reply": "I'll pay the invoice on Friday.",
    },
    {
        "key": "moment-plan",
        "label": "Payment plan → escalate",
        "account_id": 8801002,
        "reply": "I can't pay everything today. Can I make payments?",
    },
    {
        "key": "moment-block",
        "label": "Threat language → block",
        "account_id": 8801003,
        "reply": "I'll pay the invoice on Friday.",
        "injected": "Failure to pay may result in legal action.",
        "note": "Replaces the draft with unauthorized consequence language so PR-3 can stop it.",
    },
    {
        "key": "moment-paid",
        "label": "Already paid → ledger",
        "account_id": 8801004,
        "reply": "I already paid this last week.",
    },
    {
        "key": "moment-quiet",
        "label": "Quiet hours → revise",
        "account_id": 8801005,
        "reply": "We will pay on Friday.",
        "send_time": "2026-11-20T22:30:00+00:00",
    },
)

PRESETS = {
    "Promise to pay": "I'll pay the invoice on Friday.",
    "Already paid": "I already paid this last week.",
    "Payment plan": "I can't pay everything today. Can I make payments?",
    "Invoice not received": "We never received the invoice.",
    "Amount dispute": "The amount is wrong.",
    "Adversarial": "My attorney will be contacting you.",
    "Unclear": "Hello, just checking in.",
}

STATUS_COLOR = {
    "OPEN": "#8aa0b2",
    "AUTO-APPROVED": "#2BBBAD",
    "ESCALATED": "#e0a15a",
    "BLOCKED": "#e06b6b",
    "PAID": "#7d8b99",
}


@st.cache_resource
def ensure_demo_database(db_path: str) -> str:
    os.environ["CLEARTIDE_DB_PATH"] = db_path
    forget_schema_cache(db_path)
    build_demo_database(Path(db_path))
    apply_streamlit_book_spread(Path(db_path))
    return db_path


def _stage_delay() -> float:
    try:
        return max(0.0, float(os.environ.get("ACA_STAGE_DELAY", "0.35")))
    except ValueError:
        return 0.35


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


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        html, body, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stHeader"], [data-testid="stToolbar"],
        [data-testid="stDecoration"], [data-testid="stBottom"],
        [data-testid="stSidebar"], [data-testid="stSidebarContent"],
        section.main, .main .block-container {
            background-color: #07141f !important;
            color: #E7F1F4 !important;
        }
        .stApp {
            background: radial-gradient(1200px 500px at 90% -10%, rgba(43,187,173,.16), transparent 45%), #07141f !important;
        }
        [data-testid="stHeader"], [data-testid="stDecoration"] { background: transparent !important; }
        [data-testid="stSidebar"] { border-right: 1px solid #1c3348; }
        h1, h2, h3, p, span, label, li { color: #E7F1F4; }
        h1, h2, h3 { letter-spacing: -0.03em; }
        [data-testid="stCaptionContainer"] p, .stCaption { color: #9fb3c4 !important; }
        div[data-testid="stMetric"],
        [data-testid="stExpander"] details,
        [data-testid="stAlert"],
        [data-testid="stStatusWidget"],
        [data-testid="stDataFrame"],
        [data-testid="stJson"],
        .stTextInput input, .stTextArea textarea,
        [data-baseweb="select"] > div, [data-baseweb="input"] > div,
        [data-baseweb="textarea"] textarea {
            background-color: #12263a !important;
            color: #E7F1F4 !important;
            border-color: #1e3a52 !important;
        }
        div[data-testid="stMetric"] {
            border: 1px solid #1e3a52;
            border-radius: 14px;
            padding: 10px 14px;
            cursor: default;
        }
        [data-testid="stMetricLabel"] p, [data-testid="stMetricValue"] {
            color: #E7F1F4 !important;
        }
        [data-testid="stExpander"] summary, [data-testid="stExpander"] details {
            color: #E7F1F4 !important;
        }
        .st-key-view-switch button {
            background: #12263a !important;
            color: #E7F1F4 !important;
            border-color: #1e3a52 !important;
        }
        .st-key-view-switch button[aria-checked="true"],
        .st-key-view-switch button[aria-pressed="true"] {
            background: #134e4a !important;
            color: #d9fffa !important;
        }
        button { cursor: pointer; }
        .aca-brand { display: flex; gap: 14px; align-items: center; margin-bottom: 8px; }
        .aca-brand h1 { margin: 0; font-size: 1.8rem; color: #E7F1F4; }
        .aca-brand p { margin: 2px 0 0; color: #9fb3c4; }
        .aca-card {
            background: #12263a;
            border: 1px solid #1e3a52;
            border-left: 4px solid var(--accent, #8aa0b2);
            border-radius: 14px;
            padding: 12px 14px 8px;
            min-height: 132px;
            cursor: default;
        }
        .aca-card strong { display: block; font-size: 1.02rem; color: #E7F1F4; }
        .aca-card span { color: #9fb3c4; font-size: 0.92rem; }
        .aca-chip {
            display: inline-block;
            margin-top: 8px;
            padding: 3px 8px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: .04em;
            color: #07141f;
            background: var(--accent, #8aa0b2);
            cursor: default;
            pointer-events: none;
        }
        .aca-progress {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 6px 0 4px;
        }
        .aca-pill {
            pointer-events: none;
            cursor: default;
            user-select: none;
            border-radius: 999px;
            padding: 3px 10px;
            font-size: 0.78rem;
            font-weight: 650;
            background: #102233;
            color: #8aa0b2;
            border: 1px solid #1e3a52;
        }
        .aca-pill.on { background: #134e4a; color: #d9fffa; border-color: #2BBBAD; }
        .aca-pill.done { background: #0f3d45; color: #b7fff4; border-color: #1e8f86; }
        .aca-badge {
            display: inline-block;
            margin: 8px 0 14px;
            padding: 12px 18px;
            border-radius: 14px;
            font-size: 1.6rem;
            font-weight: 800;
            letter-spacing: .04em;
            cursor: default;
            pointer-events: none;
        }
        .aca-badge.ok { background: #134e4a; color: #b7fff4; }
        .aca-badge.warn { background: #4a3414; color: #ffd7a1; }
        .aca-badge.bad { background: #4a1c24; color: #ffc1c1; }
        .aca-rule { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid #1e3a52; }
        .pass { color: #8ef0e2; } .fail { color: #ffb4b4; } .skip { color: #8aa0b2; }
        @media (max-width: 760px) {
            .main .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 0.45rem; }
            .st-key-account-board .stColumn,
            .st-key-demo-moments .stColumn,
            .st-key-chart-row .stColumn,
            .st-key-stage-jumps .stColumn {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 100% !important;
                max-width: 100% !important;
            }
            .st-key-ops-metrics .stColumn {
                width: 48% !important;
                flex: 1 1 46% !important;
                min-width: 46% !important;
                max-width: 50% !important;
            }
            button { min-height: 44px; }
            .aca-card { min-height: 0; }
            .aca-badge { font-size: 1.25rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _brand() -> None:
    st.markdown(
        """
        <div class="aca-brand">
          <svg width="54" height="36" viewBox="0 0 240 160" aria-hidden="true">
            <rect width="240" height="160" rx="28" fill="#163257"/>
            <path d="M40,118 C64,66 84,66 104,94 C120,114 136,110 152,94 C168,74 180,58 192,48" fill="none" stroke="#FFFFFF" stroke-width="14" stroke-linecap="round"/>
            <circle cx="192" cy="48" r="11" fill="#2BBBAD"/>
          </svg>
          <div>
            <h1>Cleartide collections</h1>
            <p>Live agent console · policy decides · every step is audited</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _plotly_layout(fig, height=280):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E7F1F4",
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h"),
    )
    return fig


def _run_console(account_id: int, reply: str, injected: str = None, send_time: str = None) -> dict:
    os.environ["CLEARTIDE_DB_PATH"] = str(DB_PATH)
    book = {row["account_id"]: row for row in work_queue()}
    account = book.get(int(account_id))
    if account is None:
        raise RuntimeError(f"Account {account_id} is not on the live book.")
    when = datetime.fromisoformat(send_time) if send_time else None
    result = run_aca(
        account_id=int(account_id),
        invoice_id=int(account["invoice_id"]),
        reply_text=reply,
        proposed_send_time=when,
        injected_message_body=injected,
    )
    scenario = {
        "id": "console",
        "title": account["customer_name"],
        "story": "",
        "account_id": int(account_id),
        "invoice_id": int(account["invoice_id"]),
        "reply_text": reply,
        "injected_message_body": injected,
    }
    view = present_decision(scenario, result)
    view["policy_card"] = policy_card(view.get("violated_constraints") or [])
    view["decision_label"] = decision_label(view)
    view["evidence_blocks"] = evidence_blocks(result)
    view["readout"] = policy_readout(view)
    view["applied"] = apply_approved_outcome(view, result)
    draft = view.get("message_draft") or ""
    view["draft_grade"] = flesch_kincaid_grade(draft) if draft else None
    return view


def _progress(active: int, done: bool = False) -> str:
    """Compact status marks. They are not controls."""

    parts = ['<div class="aca-progress">']
    for index, name in enumerate(STAGES):
        if done or index < active:
            klass = "done"
        elif index == active:
            klass = "on"
        else:
            klass = ""
        parts.append(f'<span class="aca-pill {klass}">{name}</span>')
    parts.append("</div>")
    return "".join(parts)


def _stage_jumps() -> None:
    st.caption("Open a stage")
    with st.container(key="stage-jumps"):
        columns = st.columns(len(STAGES))
        for column, stage in zip(columns, STAGES):
            if column.button(stage, key=f"jump-{stage}"):
                st.session_state["open_stage"] = stage


def _stage_open(name: str, default: bool) -> bool:
    chosen = st.session_state.get("open_stage")
    if not chosen:
        return default
    return chosen == name


def _badge(label: str) -> str:
    kind = {"AUTO-APPROVED": "ok", "ESCALATED": "warn", "BLOCKED": "bad"}.get(label, "warn")
    return f'<div class="aca-badge {kind}">{label}</div>'


def _stage_line(view: dict, stage: str) -> str:
    if stage == "Intent":
        return f"Intent {view.get('intent')} · confidence {view.get('confidence')}"
    if stage == "Tools":
        names = ", ".join(tool.get("tool") for tool in view.get("tools") or []) or "none"
        return f"Tools: {names}"
    if stage == "Risk":
        return f"Risk {view.get('risk_band')} {view.get('risk_score')}"
    if stage == "Recommend":
        return f"{view.get('recommended_action')} via {view.get('channel')}"
    if stage == "Policy":
        return view.get("decision_label") or ""
    return f"Audit decision {view.get('decision_id')}"


def _play(view: dict) -> None:
    delay = _stage_delay()
    with st.status("Agent is working this account…", expanded=True) as status:
        slot = st.empty()
        for index, stage in enumerate(STAGES):
            slot.markdown(_progress(index), unsafe_allow_html=True)
            status.write(_stage_line(view, stage))
            if delay:
                time.sleep(delay)
        slot.markdown(_progress(len(STAGES), done=True), unsafe_allow_html=True)
        status.update(label=view["decision_label"], state="complete", expanded=False)
    st.caption("Those marks are progress, not buttons.")
    st.markdown(_badge(view["decision_label"]), unsafe_allow_html=True)
    if view.get("verdict") == "SAFE REVISION":
        st.caption(view.get("revision_reason") or "Revised once, then approved.")
    if view.get("applied"):
        st.success(f"Book updated: {view['applied']}")
    _stage_jumps()
    _detail_expanders(view)


def _detail_expanders(view: dict) -> None:
    with st.expander("Intent", expanded=_stage_open("Intent", True)):
        st.write(f"**{view.get('intent')}** · confidence {view.get('confidence')}")
        st.caption(view.get("reply_text") or "")
    with st.expander("Tools", expanded=_stage_open("Tools", True)):
        if not view.get("evidence_blocks"):
            st.write("No account tools ran. The reply itself was enough to stop.")
        for block in view.get("evidence_blocks") or []:
            st.markdown(f"**{block['title']}**")
            st.json(block["rows"])
        for tool in view.get("tools") or []:
            st.caption(f"{tool.get('tool')} · {tool.get('status')} · {tool.get('highlights') or ''}")
    with st.expander("Risk", expanded=_stage_open("Risk", False)):
        st.write(f"{view.get('risk_band')} · {view.get('risk_score')}")
        factors = view.get("risk_factors") or []
        if factors:
            st.write(", ".join(str(item) for item in factors))
    with st.expander("Recommendation and draft", expanded=_stage_open("Recommend", True)):
        st.write(f"{view.get('recommended_action')} via {view.get('channel')}")
        if view.get("message_draft"):
            st.text(view["message_draft"])
            st.caption(f"Draft reading grade {view.get('draft_grade')}")
        else:
            st.caption("No customer draft.")
        if view.get("rationale"):
            st.write(view["rationale"])
    with st.expander("Policy validator", expanded=_stage_open("Policy", True)):
        st.caption(
            "Readout of where the deterministic validator stopped. "
            "It does not decide the case again."
        )
        for row in view.get("readout") or []:
            klass = {"Pass": "pass", "Fail": "fail"}.get(row["state"], "skip")
            st.markdown(
                f'<div class="aca-rule"><span><b>{row["rule"]}</b> · {row["plain"]}</span>'
                f'<span class="{klass}">{row["state"]}</span></div>',
                unsafe_allow_html=True,
            )
    brief = view.get("reviewer_brief") or {}
    if brief.get("sections"):
        with st.expander(
            "Reviewer brief",
            expanded=_stage_open("Audit", view["decision_label"] != "AUTO-APPROVED"),
        ):
            for section in brief["sections"]:
                st.markdown(f"**{section['heading']}**")
                st.write(section.get("body") or "")
            st.caption(
                f"Brief reading grade {brief.get('grade')} · limit {brief.get('grade_limit')}. "
                "Quotes are not scored."
            )


def _ops_header() -> dict:
    ops = session_ops()
    with st.container(key="ops-metrics"):
        cards = st.columns(5)
    cards[0].metric("Autonomous", ops["autonomous"])
    cards[1].metric("Escalated", ops["escalated"])
    cards[2].metric("Blocked", ops["blocked"])
    cards[3].metric("Open reviews", ops["open_reviews"])
    cards[4].metric("Policy violations", ops["policy_violations"])
    return ops


def _account_board(book: list[dict]) -> None:
    with st.container(key="account-board"):
        columns = st.columns(len(book) or 1)
    for column, row in zip(columns, book):
        accent = STATUS_COLOR.get(row["board_status"], "#8aa0b2")
        days = row["days_past_due"]
        day_label = f"{days}d past due" if days > 0 else "Not past due"
        promise = f" · {row['open_promises']} promise" if row["open_promises"] else ""
        with column:
            st.markdown(
                f"""
                <div class="aca-card" style="--accent:{accent}">
                  <strong>{row['customer_name']}</strong>
                  <span>${row['balance']:,.0f} open · {day_label}</span><br>
                  <span>{row.get('risk_band') or '—'} {row.get('score') or ''}{promise}</span>
                  <div class="aca-chip">{row['board_status']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Work {row['customer_name']}", key=f"pick-{row['account_id']}"):
                st.session_state["selected_id"] = row["account_id"]


def _charts(book: list[dict], selected: dict, ops: dict) -> None:
    with st.container(key="chart-row"):
        left, mid, right = st.columns(3)
    score = float(selected.get("score") or 0)
    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": f"{selected['customer_name']} risk"},
            gauge={
                "axis": {"range": [0, 1]},
                "bar": {"color": "#2BBBAD"},
                "steps": [
                    {"range": [0, 0.3], "color": "#163a3a"},
                    {"range": [0.3, 0.6], "color": "#3a3416"},
                    {"range": [0.6, 1], "color": "#3a1c22"},
                ],
            },
        )
    )
    left.plotly_chart(_plotly_layout(gauge, 260), width="stretch")

    frames = portfolio_frames(book)
    aging = frames["aging"] or {"No balance": 0}
    bars = go.Figure(go.Bar(x=list(aging), y=list(aging.values()), marker_color="#2BBBAD"))
    bars.update_layout(title="Open balance by aging")
    mid.plotly_chart(_plotly_layout(bars, 260), width="stretch")

    mix_labels = ["Autonomous", "Escalated", "Blocked"]
    mix_values = [ops["autonomous"], ops["escalated"], ops["blocked"]]
    if sum(mix_values) == 0:
        right.info("No decisions yet this session.")
    else:
        donut = go.Figure(
            go.Pie(
                labels=mix_labels,
                values=mix_values,
                hole=0.62,
                marker_colors=["#2BBBAD", "#e0a15a", "#e06b6b"],
            )
        )
        donut.update_layout(title="This session")
        right.plotly_chart(_plotly_layout(donut, 260), width="stretch")


def _page_console() -> None:
    _brand()
    ops = _ops_header()
    book = work_queue()
    if not book:
        st.error("The demo book is empty. Use Reset demo.")
        return
    st.subheader("Open book")
    _account_board(book)
    selected_id = st.session_state.get("selected_id", book[0]["account_id"])
    if selected_id not in {row["account_id"] for row in book}:
        selected_id = book[0]["account_id"]
    selected = next(row for row in book if row["account_id"] == selected_id)
    st.caption(f"Working {selected['customer_name']} · invoice {selected['invoice_id']}")
    _charts(book, selected, ops)

    st.subheader("Demo moments")
    st.caption(
        "One click prefills a real account and runs the agent. "
        "Threat language replaces the draft so the policy block is visible. Free text still works."
    )
    with st.container(key="demo-moments"):
        moment_cols = st.columns(len(MOMENTS))
    chosen = None
    for column, moment in zip(moment_cols, MOMENTS):
        if column.button(moment["label"], key=moment["key"]):
            chosen = moment
    if chosen:
        st.session_state["selected_id"] = chosen["account_id"]
        st.session_state["console-reply"] = chosen["reply"]
        st.session_state["pending_moment"] = chosen["key"]

    if "console-reply" not in st.session_state:
        st.session_state["console-reply"] = ""
    preset = st.selectbox(
        "Example replies",
        ["Type your own"] + list(PRESETS),
        key="preset-choice",
    )
    if preset in PRESETS and st.session_state.get("_last_preset") != preset:
        st.session_state["_last_preset"] = preset
        st.session_state["console-reply"] = PRESETS[preset]
    reply = st.text_area("Customer reply", key="console-reply", height=90)

    pending = st.session_state.pop("pending_moment", None)
    run_free = st.button("Run agent", key="run-agent", type="primary")
    moment = next((item for item in MOMENTS if item["key"] == pending), None)
    if pending or run_free:
        text = (moment or {}).get("reply") or (reply or "").strip()
        account_id = (moment or {}).get("account_id") or selected_id
        if not text:
            st.warning("Type a customer reply, or use a demo moment.")
        else:
            try:
                view = _run_console(
                    account_id,
                    text,
                    injected=(moment or {}).get("injected"),
                    send_time=(moment or {}).get("send_time"),
                )
                st.session_state["open_stage"] = None
                st.session_state["console_view"] = view
                if moment and moment.get("note"):
                    st.caption(moment["note"])
                _play(view)
            except Exception as exc:
                st.session_state.pop("console_view", None)
                st.error(f"The agent stopped with an error and did not send: {exc}")
    elif st.session_state.get("console_view"):
        saved = st.session_state["console_view"]
        st.markdown(_badge(saved["decision_label"]), unsafe_allow_html=True)
        if saved.get("applied"):
            st.success(f"Book updated: {saved['applied']}")
        _stage_jumps()
        _detail_expanders(saved)

    with st.expander("About this demo"):
        st.write(
            "Cleartide is a governed collections agent for roll-off accounts. "
            "The model stand-in recommends. config/policy.yaml, enforced by "
            "src/policy.py, decides. This console is the working book. "
            "The guided scenarios are still on the last sidebar page."
        )


def _page_inbox() -> None:
    _brand()
    st.header("Reviewer inbox")
    st.caption("Oldest open case first. A disposition is appended. The decision row is not edited.")
    if st.session_state.get("inbox_message"):
        st.success(st.session_state.pop("inbox_message"))
    items = inbox_items()
    if not items:
        st.info("Inbox is clear.")
        return
    for item in items:
        accent = STATUS_COLOR.get(item["queue_label"], "#e0a15a")
        st.markdown(
            f"""
            <div class="aca-card" style="--accent:{accent}">
              <strong>{item['customer_name']}</strong>
              <span>Escalation {item['escalation_id']} · age {item['age_label']} · {item.get('intent') or '—'}</span>
              <div class="aca-chip">{item['queue_label']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write(item.get("reply_text") or "")
        brief = item.get("brief") or {}
        for section in brief.get("sections") or []:
            st.markdown(f"**{section['heading']}**")
            st.write(section.get("body") or "")
        note = st.text_input(
            "Note",
            key=f"inbox-note-{item['escalation_id']}",
        )
        buttons = st.columns(len(DISPOSITIONS))
        for column, code in zip(buttons, DISPOSITIONS):
            if column.button(code, key=f"inbox-{item['escalation_id']}-{code}"):
                try:
                    record_human_disposition(
                        int(item["escalation_id"]),
                        code,
                        reviewer_note=note,
                        reviewed_by="class-reviewer",
                    )
                    st.session_state["inbox_message"] = (
                        f"Recorded {code}. The audit note was appended. "
                        "The decision was not rewritten."
                    )
                    st.rerun()
                except HumanReviewError as exc:
                    st.error(str(exc))
        st.divider()


def _page_audit() -> None:
    _brand()
    st.header("Audit trail")
    st.caption("Newest first. A completed decision cannot be rewritten through the application.")
    rows = recent_audits()
    if not rows:
        st.info("No decisions yet. Run the agent from the console.")
        return
    for row in rows:
        accent = STATUS_COLOR.get(row["label"], "#8aa0b2")
        st.markdown(
            f"""
            <div class="aca-card" style="--accent:{accent}">
              <strong>#{row['decision_id']} · {row.get('customer_name') or row['account_id']}</strong>
              <span>{row.get('primary_intent') or '—'} · {row.get('final_action') or '—'}</span>
              <div class="aca-chip">{row['label']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write(row.get("final_reason") or "")
        record = get_complete_audit_record(int(row["decision_id"]))
        if record:
            with st.expander(f"Timeline {row['decision_id']}"):
                for step in record.get("timeline") or []:
                    st.markdown(f"**{step['step']}.** {step['detail']}")
        if st.button("Attempt rewrite", key=f"rewrite-{row['decision_id']}"):
            try:
                attempt_audit_rewrite(
                    int(row["decision_id"]),
                    {"final_reason": "tampered during the demo"},
                )
            except AuditImmutableError as exc:
                st.error(str(exc))


def _page_policy() -> None:
    _brand()
    policy = load_policy()
    st.header(f"Policy {policy['policy_version']}")
    st.caption(
        "Read from config/policy.yaml. The agent does not choose these limits. "
        "src/policy.py enforces them."
    )
    agent = policy["agent"]
    contact = policy["contact"]
    left, right = st.columns(2)
    left.metric("Autonomy", "On" if agent["autonomous_action_enabled"] else "Off")
    left.metric("Confidence floor", agent["classification_confidence_threshold"])
    left.metric("Contacts / 7 days", contact["max_contacts_per_7_days"])
    right.metric(
        "Quiet hours",
        f"{contact['consumer_quiet_hours']['start']}–{contact['consumer_quiet_hours']['end']}",
    )
    right.metric(
        "SMS needs consent",
        "Yes" if contact["sms_requires_affirmative_consent"] else "No",
    )
    right.metric(
        "Opt-out escalates",
        "Yes" if contact["opt_out_requires_escalation"] else "No",
    )
    st.subheader("Payment-plan authority")
    plans = []
    for band, rule in policy["payment_plans"].items():
        plans.append(
            {
                "Risk": band,
                "Max days": rule["max_duration_days"],
                "Minimum down payment": rule["minimum_down_payment_pct"],
                "Agent may offer": "Yes" if rule["autonomous_allowed"] else "No",
            }
        )
    st.dataframe(plans, hide_index=True, width="stretch")
    st.subheader("Hard switches")
    hard = policy["hard_constraints"]
    st.dataframe(
        [{"Switch": key, "Value": value} for key, value in hard.items()],
        hide_index=True,
        width="stretch",
    )
    st.subheader("Language the validator blocks")
    truth = policy["truthfulness"]
    st.write("**Unauthorized consequences:** " + ", ".join(truth["unauthorized_consequence_terms"]))
    st.write("**Collector representation:** " + ", ".join(truth["third_party_representation_terms"]))
    st.caption(
        "These are engineering controls for the academic prototype, "
        "not a legal opinion."
    )


def _page_evaluation() -> None:
    _brand()
    st.header("Synthetic evaluation")
    payload = _load_json(EVAL_PATH) or {}
    summary = payload.get("summary") or {}
    st.write(f"{summary.get('total_cases', '—')} labeled cases, run by the code.")
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
    names = [label for _, label in metrics]
    values = [summary.get(key) or 0 for key, _ in metrics]
    chart = go.Figure(go.Bar(x=names, y=values, marker_color="#2BBBAD"))
    chart.update_layout(title="Evaluation metrics", yaxis_range=[0, 1])
    st.plotly_chart(_plotly_layout(chart, 320), width="stretch")
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
    _brand()
    st.header("Each requirement points at code and a test that ran.")
    st.write(
        "Generated from pytest, not from a status someone typed. "
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
                "Tests": ", ".join((row.get("passed_tests") or [])[:3]),
            }
            for row in rows
        ],
        hide_index=True,
        width="stretch",
    )


def _render_result(view: dict) -> None:
    columns = st.columns(4)
    columns[0].metric("Intent", view.get("intent") or "—")
    columns[1].metric("Risk", f"{view.get('risk_band') or '—'} {view.get('risk_score') or ''}".strip())
    columns[2].metric("Verdict", view.get("verdict") or "—")
    columns[3].metric("Outcome", "Sent" if view.get("executed") else "Not sent")
    st.write(view.get("policy_explanation") or "")
    st.write(f"**Rule** {', '.join(view.get('violated_constraints') or []) or 'none'}")
    if view.get("rationale"):
        st.write(view["rationale"])


def _scenario_panel(scenario_id: str, *, run_key: str) -> None:
    scenario = scenario_by_id(scenario_id)
    st.subheader(scenario["title"])
    st.write(scenario.get("story") or "")
    if st.button("Run this scenario", key=run_key):
        os.environ["CLEARTIDE_DB_PATH"] = str(DB_PATH)
        st.session_state.setdefault("results", {})[scenario_id] = run_scenario(scenario)
    view = (st.session_state.get("results") or {}).get(scenario_id)
    if view:
        _render_result(view)


def _page_guided() -> None:
    _brand()
    st.header("Guided walkthrough")
    with st.expander("About this demo"):
        st.write(
            "Collections needs judgment and a harness. The numbered moments "
            "on the live console are the same five cases: promise approved, "
            "payment plan escalated, threat language blocked, ledger check, "
            "and quiet-hours revision."
        )
    _scenario_panel("autonomous_promise", run_key="run-autonomous")
    _scenario_panel("human_review_payment_plan", run_key="run-review")
    view = (st.session_state.get("results") or {}).get("human_review_payment_plan")
    if view and view.get("escalation_id"):
        note = st.text_input("Note for the account memory", key="review-note")
        buttons = st.columns(len(DISPOSITIONS))
        for column, code in zip(buttons, DISPOSITIONS):
            if column.button(code, key=f"disp-{code}"):
                try:
                    record_human_disposition(
                        int(view["escalation_id"]),
                        code,
                        reviewer_note=note,
                        reviewed_by="class-reviewer",
                    )
                    st.session_state["review_message"] = (
                        f"Recorded {code}. An audit note was appended."
                    )
                except HumanReviewError as exc:
                    st.session_state["review_message"] = str(exc)
        if st.session_state.get("review_message"):
            st.info(st.session_state["review_message"])
        if st.button("Run the account again and show the memory", key="rerun-review"):
            os.environ["CLEARTIDE_DB_PATH"] = str(DB_PATH)
            st.session_state.setdefault("results", {})[
                "human_review_payment_plan"
            ] = run_scenario(scenario_by_id("human_review_payment_plan"))
            st.rerun()
    _scenario_panel("blocked_policy_violation", run_key="run-blocked")
    _scenario_panel("already_paid_evidence", run_key="run-paid")
    _scenario_panel("sms_quiet_hours_revision", run_key="run-quiet")


def _sync_switch_to_sidebar() -> None:
    value = st.session_state.get("view-switch")
    if value in VIEWS:
        st.session_state["walkthrough"] = value


def _sync_sidebar_to_switch() -> None:
    value = st.session_state.get("walkthrough")
    if value in VIEWS:
        st.session_state["view-switch"] = value


def main() -> None:
    ensure_demo_database(str(DB_PATH))
    _inject_css()
    st.sidebar.title("Cleartide")
    st.sidebar.caption("Same pages as the View bar. On a phone, use the bar.")
    choice = st.sidebar.radio(
        "Walkthrough",
        VIEWS,
        key="walkthrough",
        on_change=_sync_sidebar_to_switch,
    )
    if st.sidebar.button("Reset demo", key="reset-demo"):
        _reset_demo()
    st.segmented_control(
        "View",
        VIEWS,
        key="view-switch",
        default=VIEWS[0],
        on_change=_sync_switch_to_sidebar,
        format_func=lambda name: SHORT_VIEWS[name],
        wrap=True,
    )
    pages = {
        "Live Agent Console": _page_console,
        "Reviewer Inbox": _page_inbox,
        "Audit Trail": _page_audit,
        "Evaluation": _page_evaluation,
        "Traceability": _page_traceability,
        "Policy": _page_policy,
        "Guided walkthrough": _page_guided,
    }
    pages[choice]()


main()
