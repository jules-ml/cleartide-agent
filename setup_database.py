import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "cleartide.db"


def create_database():
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id INTEGER PRIMARY KEY,
        customer_name TEXT NOT NULL,
        industry TEXT,
        debt_type TEXT,
        account_status TEXT NOT NULL DEFAULT 'active',
        sms_consent INTEGER NOT NULL DEFAULT 0,
        email_allowed INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS invoices (
        invoice_id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        issue_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        FOREIGN KEY (account_id) REFERENCES accounts(account_id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        invoice_id INTEGER,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        status TEXT NOT NULL,
        payment_method TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS communications (
        communication_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        invoice_id INTEGER,
        direction TEXT NOT NULL,
        channel TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS delivery_log (
        delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        delivery_status TEXT NOT NULL,
        delivered_at TEXT,
        failure_reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS disputes (
        dispute_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        invoice_id INTEGER,
        dispute_type TEXT NOT NULL,
        disputed_amount REAL,
        status TEXT NOT NULL DEFAULT 'open',
        resolution TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS promises_to_pay (
        promise_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        invoice_id INTEGER,
        promised_amount REAL NOT NULL,
        promised_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS risk_scores (
        risk_score_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        invoice_id INTEGER,
        score REAL NOT NULL CHECK(score >= 0 AND score <= 1),
        risk_band TEXT NOT NULL,
        model_version TEXT NOT NULL,
        contributing_factors TEXT,
        scored_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS tool_calls (
        tool_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id INTEGER,
        tool_name TEXT NOT NULL,
        arguments_json TEXT NOT NULL,
        result_json TEXT,
        status TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS escalations (
        escalation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        invoice_id INTEGER,
        reply_text TEXT NOT NULL,
        intent TEXT,
        confidence REAL,
        proposed_action TEXT,
        rejection_reason TEXT,
        risk_score REAL,
        risk_band TEXT,
        human_disposition TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );

    CREATE TABLE IF NOT EXISTS agent_actions (
        decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        invoice_id INTEGER,
        reply_text TEXT NOT NULL,
        primary_intent TEXT NOT NULL,
        secondary_intents TEXT,
        confidence REAL NOT NULL,
        debt_classification TEXT,
        risk_score REAL,
        risk_band TEXT,
        proposed_action TEXT,
        final_action TEXT NOT NULL,
        target_channel TEXT,
        message_body TEXT,
        rationale TEXT,
        validator_outcome TEXT,
        violated_constraint TEXT,
        policy_version TEXT NOT NULL,
        model_version TEXT,
        cost REAL,
        latency_ms REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
    );
    """)

    conn.commit()
    conn.close()

    print(f"Cleartide database created at: {DB_PATH}")


if __name__ == "__main__":
    create_database()