"""Build a fresh isolated demo database. Never touches the historical fixture DB."""

import json
from datetime import datetime, timezone
from pathlib import Path

from demo.fixtures import demo_accounts
from setup_database import setup_database
from src.database import forget_schema_cache, get_connection


def build_demo_database(path: Path) -> Path:
    path = Path(path)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix) if suffix else path
        if candidate.exists():
            candidate.unlink()

    forget_schema_cache(path)
    setup_database(path)
    forget_schema_cache(path)

    scored_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()

    try:
        for account in demo_accounts():
            conn.execute(
                """
                INSERT INTO accounts (
                    account_id, customer_name, industry, debt_type,
                    account_status, sms_consent, email_allowed,
                    lifetime_value, customer_since
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account["account_id"],
                    account["customer_name"],
                    account["industry"],
                    account["debt_type"],
                    account["account_status"],
                    int(account["sms_consent"]),
                    int(account["email_allowed"]),
                    account["lifetime_value"],
                    account["customer_since"],
                ),
            )
            conn.execute(
                """
                INSERT INTO invoices (
                    invoice_id, account_id, amount, issue_date, due_date, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account["invoice_id"],
                    account["account_id"],
                    account["amount"],
                    account["issue_date"],
                    account["due_date"],
                    account["invoice_status"],
                ),
            )
            conn.execute(
                """
                INSERT INTO risk_scores (
                    account_id, invoice_id, score, risk_band,
                    model_version, contributing_factors, scored_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account["account_id"],
                    account["invoice_id"],
                    account["risk_score"],
                    account["risk_band"],
                    "demo-fixture-v1",
                    json.dumps(account["factors"]),
                    scored_at,
                ),
            )

            for payment in account["payments"]:
                conn.execute(
                    """
                    INSERT INTO payments (
                        account_id, invoice_id, amount, payment_date,
                        status, payment_method
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account["account_id"],
                        account["invoice_id"],
                        payment["amount"],
                        "2026-11-10",
                        payment["status"],
                        "ACH",
                    ),
                )

            for promise in account["promises"]:
                conn.execute(
                    """
                    INSERT INTO promises_to_pay (
                        account_id, invoice_id, promised_amount,
                        promised_date, status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        account["account_id"],
                        account["invoice_id"],
                        promise["amount"],
                        "2026-10-20",
                        promise["status"],
                    ),
                )

            for message in account["communications"]:
                conn.execute(
                    """
                    INSERT INTO communications (
                        account_id, invoice_id, direction, channel, message
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        account["account_id"],
                        account["invoice_id"],
                        message["direction"],
                        message["channel"],
                        message["message"],
                    ),
                )

            if account["delivery_status"]:
                conn.execute(
                    """
                    INSERT INTO delivery_log (
                        invoice_id, channel, delivery_status,
                        delivered_at, failure_reason
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        account["invoice_id"],
                        "EMAIL",
                        account["delivery_status"],
                        None,
                        account["failure_reason"],
                    ),
                )

            for channel in account["opt_outs"]:
                conn.execute(
                    """
                    INSERT INTO channel_opt_outs (account_id, channel, source)
                    VALUES (?, ?, ?)
                    """,
                    (account["account_id"], channel, "demo-fixture"),
                )

        conn.commit()
    finally:
        conn.close()

    return path
