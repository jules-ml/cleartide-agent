import json

from src.database import get_connection


def seed_data():
    conn = get_connection()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # ACCOUNT
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT OR REPLACE INTO accounts (
            account_id,
            customer_name,
            industry,
            debt_type,
            account_status,
            sms_consent,
            email_allowed
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1001,
            "Harborview Waste Services",
            "Waste Hauling",
            "COMMERCIAL",
            "active",
            1,
            1,
        ),
    )

    # --------------------------------------------------------
    # INVOICE WITH FAILED DELIVERY
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT OR REPLACE INTO invoices (
            invoice_id,
            account_id,
            amount,
            issue_date,
            due_date,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            5001,
            1001,
            8750.00,
            "2026-07-10",
            "2026-08-10",
            "open",
        ),
    )

    # --------------------------------------------------------
    # DELIVERY LOG
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO delivery_log (
            invoice_id,
            channel,
            delivery_status,
            delivered_at,
            failure_reason
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            5001,
            "EMAIL",
            "FAILED",
            None,
            "Mailbox rejected message",
        ),
    )

    # --------------------------------------------------------
    # PREVIOUS POSTED PAYMENT
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO payments (
            account_id,
            invoice_id,
            amount,
            payment_date,
            status,
            payment_method
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            1001,
            5001,
            1000.00,
            "2026-08-15",
            "posted",
            "ACH",
        ),
    )

    # --------------------------------------------------------
    # COMMUNICATION HISTORY
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO communications (
            account_id,
            invoice_id,
            direction,
            channel,
            message
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            1001,
            5001,
            "OUTBOUND",
            "EMAIL",
            "Reminder regarding invoice 5001.",
        ),
    )

    # --------------------------------------------------------
    # PRIOR PROMISE
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO promises_to_pay (
            account_id,
            invoice_id,
            promised_amount,
            promised_date,
            status
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            1001,
            5001,
            3000.00,
            "2026-08-25",
            "broken",
        ),
    )

    # --------------------------------------------------------
    # PRIOR DISPUTE
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO disputes (
            account_id,
            invoice_id,
            dispute_type,
            disputed_amount,
            status,
            resolution
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            1001,
            5001,
            "AMOUNT_DISPUTE",
            250.00,
            "resolved",
            "Customer accepted corrected supporting documentation.",
        ),
    )

    # --------------------------------------------------------
    # RISK SCORE FIXTURE
    #
    # This is NOT the final trained model.
    # It is a temporary development fixture.
    # --------------------------------------------------------

    factors = json.dumps(
        [
            "invoice more than 20 days past due",
            "prior broken promise to pay",
            "partial payment received",
        ]
    )

    cursor.execute(
        """
        INSERT INTO risk_scores (
            account_id,
            invoice_id,
            score,
            risk_band,
            model_version,
            contributing_factors
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            1001,
            5001,
            0.42,
            "MEDIUM",
            "fixture-v0",
            factors,
        ),
    )

    conn.commit()
    conn.close()

    print("Cleartide synthetic development data loaded.")


if __name__ == "__main__":
    seed_data()