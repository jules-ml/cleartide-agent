from src.agent import run_aca

from src.audit import get_decision_record
from src.database import get_connection


def test_invalid_debt_type_defaults_to_consumer_in_audit():
    conn = get_connection()
    original = conn.execute(
        "SELECT debt_type FROM accounts WHERE account_id = ?",
        (1001,),
    ).fetchone()["debt_type"]
    conn.execute(
        "UPDATE accounts SET debt_type = ? WHERE account_id = ?",
        ("UNKNOWN", 1001),
    )
    conn.commit()
    conn.close()

    decision_id = None

    try:
        result = run_aca(
            account_id=1001,
            invoice_id=5001,
            reply_text="I never received the invoice.",
        )

        decision_id = result["decision_id"]
        assert result["debt_classification"].value == "CONSUMER"
        record = get_decision_record(decision_id)

        assert record is not None
        assert record["debt_classification"] == "CONSUMER"

    finally:
        conn = get_connection()
        conn.execute(
            "UPDATE accounts SET debt_type = ? WHERE account_id = ?",
            (original, 1001),
        )

        if decision_id is not None:
            conn.execute(
                "DELETE FROM escalations WHERE decision_id = ?",
                (decision_id,),
            )
            conn.execute(
                "DELETE FROM tool_calls WHERE decision_id = ?",
                (decision_id,),
            )
            conn.execute(
                "DELETE FROM agent_actions WHERE decision_id = ?",
                (decision_id,),
            )

        conn.commit()
        conn.close()



def test_valid_commercial_debt_type_is_preserved_in_audit():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="I never received the invoice.",
    )

    decision_id = result["decision_id"]
    assert result["debt_classification"].value == "COMMERCIAL"

    try:
        record = get_decision_record(decision_id)

        assert record is not None
        assert record["debt_classification"] == "COMMERCIAL"

    finally:
        conn = get_connection()
        conn.execute(
            "DELETE FROM escalations WHERE decision_id = ?",
            (decision_id,),
        )
        conn.execute(
            "DELETE FROM tool_calls WHERE decision_id = ?",
            (decision_id,),
        )
        conn.execute(
            "DELETE FROM agent_actions WHERE decision_id = ?",
            (decision_id,),
        )
        conn.commit()
        conn.close()



def test_null_debt_type_defaults_to_consumer_in_audit():
    conn = get_connection()
    original = conn.execute(
        "SELECT debt_type FROM accounts WHERE account_id = ?",
        (1001,),
    ).fetchone()["debt_type"]
    conn.execute(
        "UPDATE accounts SET debt_type = NULL WHERE account_id = ?",
        (1001,),
    )
    conn.commit()
    conn.close()

    decision_id = None

    try:
        result = run_aca(
            account_id=1001,
            invoice_id=5001,
            reply_text="I never received the invoice.",
        )

        decision_id = result["decision_id"]
        assert result["debt_classification"].value == "CONSUMER"
        record = get_decision_record(decision_id)

        assert record is not None
        assert record["debt_classification"] == "CONSUMER"

    finally:
        conn = get_connection()
        conn.execute(
            "UPDATE accounts SET debt_type = ? WHERE account_id = ?",
            (original, 1001),
        )

        if decision_id is not None:
            conn.execute(
                "DELETE FROM escalations WHERE decision_id = ?",
                (decision_id,),
            )
            conn.execute(
                "DELETE FROM tool_calls WHERE decision_id = ?",
                (decision_id,),
            )
            conn.execute(
                "DELETE FROM agent_actions WHERE decision_id = ?",
                (decision_id,),
            )

        conn.commit()
        conn.close()
