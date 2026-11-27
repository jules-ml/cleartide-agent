"""Smoke test for the Streamlit Community Cloud entry point."""

import os
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"
VIEWS = (
    "01 Overview",
    "02 Autonomous",
    "03 Human review",
    "04 Policy block",
    "05 Audit trail",
    "06 Evaluation",
    "07 Traceability",
)


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

        app.sidebar.radio(key="walkthrough").set_value("03 Human review").run()
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

        app.sidebar.radio(key="walkthrough").set_value("06 Evaluation").run()
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
