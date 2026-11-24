"""Local dashboard server. No network calls and no API keys."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.audit import (
    AuditImmutableError,
    attempt_audit_rewrite,
    get_complete_audit_record,
)
from src.database import get_connection
from src.review import HumanReviewError, record_human_disposition

from demo.report_html import render_page
from demo.runner import run_scenario, scenario_by_id


def _json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def list_decisions(limit: int = 40) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT decision_id, account_id, primary_intent, final_action,
               audit_status, created_at
        FROM agent_actions
        WHERE audit_status = 'COMPLETED'
        ORDER BY decision_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def make_handler(page_payload: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _read(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                body = render_page(page_payload, live=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/decisions":
                _json(self, 200, list_decisions())
                return
            if path.startswith("/api/audit/"):
                decision_id = int(path.rsplit("/", 1)[-1])
                record = get_complete_audit_record(decision_id)
                if record and record.get("decision"):
                    record["decision"].pop("_audit_notes", None)
                _json(self, 200 if record else 404, record or {"error": "missing"})
                return
            self.send_error(404)

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            try:
                payload = self._read()
            except json.JSONDecodeError:
                _json(self, 400, {"message": "Request body was not JSON."})
                return

            if path == "/api/run":
                try:
                    scenario = scenario_by_id(payload["scenario_id"])
                except KeyError:
                    _json(self, 404, {"message": "Unknown scenario."})
                    return
                _json(self, 200, run_scenario(scenario))
                return

            if path == "/api/disposition":
                try:
                    recorded = record_human_disposition(
                        int(payload["escalation_id"]),
                        payload["disposition"],
                        reviewer_note=payload.get("reviewer_note") or "",
                        reviewed_by="class-reviewer",
                    )
                except (HumanReviewError, KeyError, TypeError, ValueError) as exc:
                    _json(self, 400, {"message": str(exc)})
                    return
                _json(
                    self,
                    200,
                    {
                        "message": (
                            f"Recorded {recorded['disposition_code']} on "
                            f"escalation {recorded['escalation_id']}. "
                            "An audit note was appended. "
                            "The original decision row was not rewritten."
                        ),
                        "case": {
                            key: recorded.get(key)
                            for key in (
                                "escalation_id",
                                "disposition_code",
                                "human_disposition",
                                "status",
                            )
                        },
                    },
                )
                return

            if path == "/api/audit/rewrite":
                decision_id = int(payload["decision_id"])
                try:
                    attempt_audit_rewrite(
                        decision_id,
                        {"final_reason": "tampered during the demo"},
                    )
                except AuditImmutableError as exc:
                    _json(self, 409, {"message": str(exc), "refused": True})
                    return
                _json(self, 500, {"message": "Rewrite was not refused."})
                return

            self.send_error(404)

    return Handler


def serve(payload: dict, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(payload))
    print(f"Cleartide demo dashboard: http://{host}:{port}")
    print("Keys 1–7 switch views. Ctrl+C stops the server.")
    server.serve_forever()
