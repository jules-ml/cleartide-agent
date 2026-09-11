import sqlite3
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "cleartide.db"


# ============================================================
# DATABASE SETUP
# ============================================================

def setup_database():
    """
    Create the Cleartide ACA development database from scratch.

    This schema reflects the Step 9 architecture:
    - persistent decision audit records
    - linked tool calls
    - escalation packets
    - structured relational memory
    - risk records
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    cursor = conn.cursor()

    # ========================================================
    # ACCOUNTS
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id INTEGER PRIMARY KEY,

            customer_name TEXT NOT NULL,

            industry TEXT,

            debt_type TEXT,

            account_status TEXT,

            sms_consent INTEGER DEFAULT 0,

            email_allowed INTEGER DEFAULT 1,

            lifetime_value REAL NOT NULL DEFAULT 0.0,

            customer_since TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    account_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(accounts)"
        ).fetchall()
    }

    if "lifetime_value" not in account_columns:
        cursor.execute(
            "ALTER TABLE accounts "
            "ADD COLUMN lifetime_value REAL NOT NULL DEFAULT 0.0"
        )

    if "customer_since" not in account_columns:
        cursor.execute(
            "ALTER TABLE accounts "
            "ADD COLUMN customer_since TEXT"
        )

    # ========================================================
    # INVOICES
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id INTEGER PRIMARY KEY,

            account_id INTEGER NOT NULL,

            amount REAL NOT NULL,

            issue_date TEXT,

            due_date TEXT,

            status TEXT,

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id)
        )
        """
    )

    # ========================================================
    # PAYMENTS
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,

            account_id INTEGER NOT NULL,

            invoice_id INTEGER,

            amount REAL NOT NULL,

            payment_date TEXT,

            status TEXT,

            payment_method TEXT,

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id),

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # COMMUNICATIONS
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS communications (
            communication_id INTEGER PRIMARY KEY AUTOINCREMENT,

            account_id INTEGER NOT NULL,

            invoice_id INTEGER,

            direction TEXT,

            channel TEXT,

            message TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id),

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # DELIVERY LOG
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS delivery_log (
            delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,

            invoice_id INTEGER NOT NULL,

            channel TEXT,

            delivery_status TEXT,

            delivered_at TEXT,

            failure_reason TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # DISPUTES
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS disputes (
            dispute_id INTEGER PRIMARY KEY AUTOINCREMENT,

            account_id INTEGER NOT NULL,

            invoice_id INTEGER,

            dispute_type TEXT,

            disputed_amount REAL,

            status TEXT,

            resolution TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            resolved_at TEXT,

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id),

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # PROMISES TO PAY
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS promises_to_pay (
            promise_id INTEGER PRIMARY KEY AUTOINCREMENT,

            account_id INTEGER NOT NULL,

            invoice_id INTEGER,

            promised_amount REAL,

            promised_date TEXT,

            status TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id),

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # RISK SCORES
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_scores (
            risk_score_id INTEGER PRIMARY KEY AUTOINCREMENT,

            account_id INTEGER NOT NULL,

            invoice_id INTEGER,

            score REAL NOT NULL
                CHECK (
                    score >= 0.0
                    AND score <= 1.0
                ),

            risk_band TEXT,

            model_version TEXT,

            contributing_factors TEXT,

            scored_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id),

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # AGENT ACTIONS
    #
    # This is the persistent decision/audit record.
    #
    # IMPORTANT:
    # Fields such as primary_intent, risk_score, final_action,
    # etc. are nullable because the decision row is created
    # BEFORE reasoning begins and completed later.
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_actions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,

            account_id INTEGER NOT NULL,

            invoice_id INTEGER,

            reply_text TEXT NOT NULL,

            primary_intent TEXT,

            secondary_intents TEXT,

            confidence REAL,

            debt_classification TEXT,

            risk_score REAL,

            risk_band TEXT,

            proposed_action TEXT,

            final_action TEXT,

            target_channel TEXT,

            message_body TEXT,

            rationale TEXT,

            validator_outcome TEXT,

            violated_constraint TEXT,

            policy_version TEXT,

            model_version TEXT,

            cost REAL DEFAULT 0.0,

            latency_ms REAL,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            final_reason TEXT,

            reasoning_mode TEXT,

            revision_count INTEGER DEFAULT 0,

            audit_status TEXT DEFAULT 'STARTED',

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id),

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # TOOL CALLS
    #
    # Every tool invocation can be tied to one decision_id.
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_calls (
            tool_call_id INTEGER PRIMARY KEY AUTOINCREMENT,

            decision_id INTEGER,

            tool_name TEXT NOT NULL,

            arguments_json TEXT,

            result_json TEXT,

            status TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (decision_id)
                REFERENCES agent_actions(decision_id)
        )
        """
    )

    # ========================================================
    # ESCALATIONS
    #
    # Human-review record plus serialized escalation packet.
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS escalations (
            escalation_id INTEGER PRIMARY KEY AUTOINCREMENT,

            decision_id INTEGER,

            account_id INTEGER NOT NULL,

            invoice_id INTEGER,

            reply_text TEXT,

            intent TEXT,

            confidence REAL,

            proposed_action TEXT,

            rejection_reason TEXT,

            risk_score REAL,

            risk_band TEXT,

            human_disposition TEXT,

            packet_json TEXT,

            status TEXT DEFAULT 'OPEN',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            resolved_at TEXT,

            FOREIGN KEY (decision_id)
                REFERENCES agent_actions(decision_id),

            FOREIGN KEY (account_id)
                REFERENCES accounts(account_id),

            FOREIGN KEY (invoice_id)
                REFERENCES invoices(invoice_id)
        )
        """
    )

    # ========================================================
    # INDEXES
    # ========================================================

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_invoices_account_id
        ON invoices(account_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_payments_account_id
        ON payments(account_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_payments_invoice_id
        ON payments(invoice_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_communications_account_id
        ON communications(account_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_delivery_log_invoice_id
        ON delivery_log(invoice_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_disputes_account_id
        ON disputes(account_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_promises_account_id
        ON promises_to_pay(account_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_risk_scores_account_id
        ON risk_scores(account_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_risk_scores_invoice_id
        ON risk_scores(invoice_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_agent_actions_account_id
        ON agent_actions(account_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_agent_actions_invoice_id
        ON agent_actions(invoice_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_tool_calls_decision_id
        ON tool_calls(decision_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_escalations_decision_id
        ON escalations(decision_id)
        """
    )

    # ========================================================
    # FINISH
    # ========================================================

    conn.commit()
    conn.close()

    print(
        f"Cleartide database schema created successfully at: "
        f"{DB_PATH}"
    )


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    setup_database()