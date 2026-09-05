from src.database import get_connection


def fix_schema():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = OFF")

    cursor.execute(
        """
        CREATE TABLE agent_actions_new (
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

    cursor.execute(
        """
        INSERT INTO agent_actions_new (
            decision_id,
            account_id,
            invoice_id,
            reply_text,
            primary_intent,
            secondary_intents,
            confidence,
            debt_classification,
            risk_score,
            risk_band,
            proposed_action,
            final_action,
            target_channel,
            message_body,
            rationale,
            validator_outcome,
            violated_constraint,
            policy_version,
            model_version,
            cost,
            latency_ms,
            created_at,
            final_reason,
            reasoning_mode,
            revision_count,
            audit_status
        )

        SELECT
            decision_id,
            account_id,
            invoice_id,
            reply_text,
            primary_intent,
            secondary_intents,
            confidence,
            debt_classification,
            risk_score,
            risk_band,
            proposed_action,
            final_action,
            target_channel,
            message_body,
            rationale,
            validator_outcome,
            violated_constraint,
            policy_version,
            model_version,
            cost,
            latency_ms,
            created_at,
            final_reason,
            reasoning_mode,
            revision_count,
            audit_status

        FROM agent_actions
        """
    )

    cursor.execute(
        """
        DROP TABLE agent_actions
        """
    )

    cursor.execute(
        """
        ALTER TABLE agent_actions_new
        RENAME TO agent_actions
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

    cursor.execute("PRAGMA foreign_keys = ON")

    conn.commit()
    conn.close()

    print("agent_actions schema fixed successfully.")


if __name__ == "__main__":
    fix_schema()