from datetime import datetime, timezone

from src.agent import run_aca
from src.database import get_connection
from src.evaluation import cleanup_decision
from src.tools import get_recent_outbound_contacts


ACCOUNT_ID = 9075001


def setup_step22_fixture():
    conn = get_connection()

    conn.execute(
        "DELETE FROM communications WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM accounts WHERE account_id = ?",
        (ACCOUNT_ID,),
    )

    conn.execute(
        "INSERT INTO accounts "
        "(account_id, customer_name, industry, debt_type, account_status) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            ACCOUNT_ID,
            "Step 22 Test Account",
            "Waste Hauling",
            "CONSUMER",
            "ACTIVE",
        ),
    )

    rows = [
        ("OUTBOUND", "EMAIL", "2026-09-04 15:59:59"),
        ("OUTBOUND", "EMAIL", "2026-09-04 16:00:00"),
        ("INBOUND", "EMAIL", "2026-09-10 12:00:00"),
        ("OUTBOUND", "SMS", "2026-09-11 15:59:59"),
        ("OUTBOUND", "EMAIL", "2026-09-11 16:00:00"),
    ]

    for direction, channel, created_at in rows:
        conn.execute(
            "INSERT INTO communications "
            "(account_id, direction, channel, message, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                ACCOUNT_ID,
                direction,
                channel,
                "Step 22 contact fixture.",
                created_at,
            ),
        )

    conn.commit()
    conn.close()


def cleanup_step22_fixture(tool_call_id):
    conn = get_connection()

    if tool_call_id is not None:
        numeric_id = int(tool_call_id.removeprefix("TC-"))
        conn.execute(
            "DELETE FROM tool_calls WHERE tool_call_id = ?",
            (numeric_id,),
        )

    conn.execute(
        "DELETE FROM communications WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM accounts WHERE account_id = ?",
        (ACCOUNT_ID,),
    )

    conn.commit()
    conn.close()


def test_recent_outbound_contacts_uses_rolling_seven_day_window():
    result = None
    setup_step22_fixture()

    try:
        result = get_recent_outbound_contacts(
            account_id=ACCOUNT_ID,
            proposed_send_time=datetime(
            2026,
            9,
            11,
            16,
            0,
            tzinfo=timezone.utc,
        ),
     )

        assert result["status"] == "SUCCESS"
        assert result["data"]["count"] == 2

        contacts = result["data"]["contacts"]

        assert {
            contact["created_at"]
            for contact in contacts
        } == {
            "2026-09-04 16:00:00",
            "2026-09-11 15:59:59",
        }

        assert all(
            contact["direction"] == "OUTBOUND"
            for contact in contacts
        )

    finally:
        cleanup_step22_fixture(
            result["tool_call_id"]
            if result is not None
            else None
        )



AGENT_ACCOUNT_ID = 9075003
AGENT_INVOICE_ID = 9075004


def setup_step22_agent_fixture():
    conn = get_connection()

    conn.execute(
        "DELETE FROM risk_scores WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM communications WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM invoices WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM accounts WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )

    conn.execute(
        "INSERT INTO accounts "
        "(account_id, customer_name, industry, debt_type, "
        "account_status, sms_consent, email_allowed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            AGENT_ACCOUNT_ID,
            "Step 22 Agent Test Account",
            "Waste Hauling",
            "COMMERCIAL",
            "ACTIVE",
            0,
            1,
        ),
    )

    conn.execute(
        "INSERT INTO invoices "
        "(invoice_id, account_id, amount, issue_date, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            AGENT_INVOICE_ID,
            AGENT_ACCOUNT_ID,
            1000.00,
            "2026-08-01",
            "2026-08-31",
            "OPEN",
        ),
    )

    conn.execute(
        "INSERT INTO risk_scores "
        "(account_id, invoice_id, score, risk_band, model_version, "
        "contributing_factors, scored_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            AGENT_ACCOUNT_ID,
            AGENT_INVOICE_ID,
            0.25,
            "LOW",
            "step22-test",
            '["step22 fixture"]',
            "2026-09-01 12:00:00",
        ),
    )

    for created_at in (
        "2026-09-08 12:00:00",
        "2026-09-09 12:00:00",
        "2026-09-10 12:00:00",
        "2026-09-11 12:00:00",
    ):
        conn.execute(
            "INSERT INTO communications "
            "(account_id, invoice_id, direction, channel, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                AGENT_ACCOUNT_ID,
                AGENT_INVOICE_ID,
                "OUTBOUND",
                "EMAIL",
                "Step 22 frequency fixture.",
                created_at,
            ),
        )

    conn.commit()
    conn.close()


def cleanup_step22_agent_fixture(result):
    if result is not None and result.get("decision_id") is not None:
        cleanup_decision(result["decision_id"])

    conn = get_connection()
    conn.execute(
        "DELETE FROM risk_scores WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM communications WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM invoices WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM accounts WHERE account_id = ?",
        (AGENT_ACCOUNT_ID,),
    )
    conn.commit()
    conn.close()


def test_fifth_contact_is_blocked_by_agent_graph():
    result = None
    setup_step22_agent_fixture()

    try:
        result = run_aca(
            account_id=AGENT_ACCOUNT_ID,
            invoice_id=AGENT_INVOICE_ID,
            reply_text="We already paid this invoice.",
            proposed_send_time=datetime(
                2026,
                9,
                11,
                16,
                0,
                tzinfo=timezone.utc,
            ),
        )

        assert result["final_status"] == "ESCALATE"
        assert result["final_action_type"].value == "ESCALATE"
        assert (
            result["recent_outbound_contacts_evidence"]["data"]["count"]
            == 4
        )
        assert any(
            tool["tool_name"] == "get_recent_outbound_contacts"
            for tool in result["escalation_packet"].tool_results
        )

    finally:
        cleanup_step22_agent_fixture(result)
