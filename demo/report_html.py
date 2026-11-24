"""Render the class dashboard. The backup copy embeds its results."""

import json
from pathlib import Path


TEMPLATE = Path(__file__).with_name("dashboard_template.html")


def render_page(payload: dict, live: bool = False) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(payload).replace("<", "\\u003c")
    return (
        html.replace("__PAYLOAD__", data)
        .replace("__LIVE__", "true" if live else "false")
    )
