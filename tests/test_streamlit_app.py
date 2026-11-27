"""Smoke test for the Streamlit Community Cloud entry point."""

import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

from demo.seed import build_demo_database


APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"
VIEWS = (
    "Live Agent Console",
    "Reviewer Inbox",
    "Audit Trail",
    "Evaluation",
    "Traceability",
    "Policy",
    "Guided walkthrough",
)


def test_eval_seed_keeps_original_due_dates(tmp_path, monkeypatch):
    database = tmp_path / "plain.db"
    monkeypatch.setenv("CLEARTIDE_DB_PATH", str(database))
    build_demo_database(database)
    from src.database import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT due_date, amount FROM invoices WHERE account_id = 8801004"
        ).fetchone()
    finally:
        conn.close()
    assert row["due_date"] == "2026-11-15"
    assert row["amount"] == 2400.0


def _assert_clean(app: AppTest) -> None:
    assert not app.exception, app.exception


def test_streamlit_app_views_and_reviewer_flow(tmp_path, monkeypatch):
    database = tmp_path / "streamlit_demo.db"
    monkeypatch.setenv("CLEARTIDE_STREAMLIT_DB", str(database))
    previous = os.environ.pop("CLEARTIDE_DB_PATH", None)
    try:
        app = AppTest.from_file(str(APP), default_timeout=60)
        app.run()
        _assert_clean(app)

        for view in VIEWS:
            app.sidebar.radio(key="walkthrough").set_value(view).run()
            _assert_clean(app)

        app.sidebar.radio(key="walkthrough").set_value("Guided walkthrough").run()
        app.button(key="run-review").click().run()
        _assert_clean(app)
        page = " ".join(block.value for block in app.markdown)
        assert "PR-5.2" in page
        assert "Not sent" in " ".join(metric.value for metric in app.metric)

        app.text_input(key="review-note").set_value(
            "Office approved a callback."
        ).run()
        app.button(key="disp-RESOLVED").click().run()
        _assert_clean(app)
        app.button(key="rerun-review").click().run()
        _assert_clean(app)
        page = " ".join(block.value for block in app.markdown)
        assert "Office approved a callback." in page

        app.sidebar.radio(key="walkthrough").set_value("Evaluation").run()
        _assert_clean(app)
        caption = " ".join(
            block.value for block in list(app.markdown) + list(app.info)
        )
        assert "own labels" in caption
    finally:
        if previous is None:
            os.environ.pop("CLEARTIDE_DB_PATH", None)
        else:
            os.environ["CLEARTIDE_DB_PATH"] = previous
        from src.database import forget_schema_cache

        forget_schema_cache()


def _metric_value(app: AppTest, label: str) -> str:
    values = [metric.value for metric in app.metric if metric.label == label]
    assert values, label
    return values[-1]


def _page_text(app: AppTest) -> str:
    chunks = []
    for group in (app.markdown, app.success, app.info, app.caption, app.warning, app.error):
        chunks.extend(block.value for block in group)
    return " ".join(chunks)


def test_live_console_outcomes(tmp_path, monkeypatch):
    database = tmp_path / "console.db"
    monkeypatch.setenv("CLEARTIDE_STREAMLIT_DB", str(database))
    monkeypatch.setenv("ACA_STAGE_DELAY", "0")
    previous = os.environ.pop("CLEARTIDE_DB_PATH", None)
    try:
        app = AppTest.from_file(str(APP), default_timeout=90)
        app.run()
        _assert_clean(app)
        assert app.sidebar.radio(key="walkthrough").value == "Live Agent Console"
        opening = _page_text(app)
        for label in ("12d past due", "35d past due", "62d past due", "95d past due"):
            assert label in opening

        app.button(key="moment-promise").click().run()
        _assert_clean(app)
        assert "AUTO-APPROVED" in _page_text(app)
        assert "No decisions yet this session" not in _page_text(app)
        assert _metric_value(app, "Autonomous") == "1"
        assert "1 autonomous, 0 escalated, 0 blocked" in _page_text(app)
        northline = [block.value for block in app.markdown if "Northline" in block.value]
        assert any("AUTO-APPROVED" in value for value in northline)

        app.button(key="moment-plan").click().run()
        _assert_clean(app)
        assert "ESCALATED" in _page_text(app)

        app.sidebar.radio(key="walkthrough").set_value("Reviewer Inbox").run()
        _assert_clean(app)
        approve = next(
            button
            for button in app.button
            if button.key and button.key.startswith("inbox-") and button.key.endswith("-APPROVE")
        )
        approve.click().run()
        _assert_clean(app)

        app.sidebar.radio(key="walkthrough").set_value("Live Agent Console").run()
        app.button(key="moment-block").click().run()
        _assert_clean(app)
        blocked_page = _page_text(app)
        assert "BLOCKED" in blocked_page
        assert "PR-3" in blocked_page
        assert "No decisions yet this session" not in blocked_page
        assert _metric_value(app, "Blocked") == "1"
        assert "benign promise" in blocked_page
        assert "Failure to pay may result in legal action." in blocked_page
        assert "regardless of what the agent drafted" in blocked_page
        harbor = [block.value for block in app.markdown if "Harbor Dumpster" in block.value]
        assert any("BLOCKED" in value for value in harbor)

        app.text_area(key="console-reply").set_value("Hello, just checking in.").run()
        app.button(key="run-agent").click().run()
        _assert_clean(app)
        assert "UNCLEAR" in _page_text(app)
        assert "ESCALATED" in _page_text(app)
    finally:
        if previous is None:
            os.environ.pop("CLEARTIDE_DB_PATH", None)
        else:
            os.environ["CLEARTIDE_DB_PATH"] = previous
        from src.database import forget_schema_cache

        forget_schema_cache()
