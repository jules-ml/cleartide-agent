from src.database import get_connection


def column_exists(conn, table_name, column_name):
    """
    Return True when a SQLite table already contains
    the requested column.
    """

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return column_name in {
        row["name"]
        for row in rows
    }


def add_column_if_missing(
    conn,
    table_name,
    column_name,
    definition,
):
    """
    Add a column only when it does not already exist.

    Makes this migration safe to run more than once.
    """

    if column_exists(
        conn,
        table_name,
        column_name,
    ):
        print(
            f"{table_name}.{column_name} "
            f"already exists"
        )

        return

    conn.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {definition}
        """
    )

    print(
        f"Added {table_name}.{column_name}"
    )


def migrate():
    conn = get_connection()

    # ========================================================
    # AGENT ACTION AUDIT FIELDS
    # ========================================================

    add_column_if_missing(
        conn,
        "agent_actions",
        "final_reason",
        "final_reason TEXT",
    )

    add_column_if_missing(
        conn,
        "agent_actions",
        "reasoning_mode",
        "reasoning_mode TEXT",
    )

    add_column_if_missing(
        conn,
        "agent_actions",
        "revision_count",
        "revision_count INTEGER DEFAULT 0",
    )

    add_column_if_missing(
        conn,
        "agent_actions",
        "audit_status",
        "audit_status TEXT DEFAULT 'STARTED'",
    )

    # ========================================================
    # ESCALATION LINKAGE / PACKET
    # ========================================================

    add_column_if_missing(
        conn,
        "escalations",
        "decision_id",
        "decision_id INTEGER",
    )

    add_column_if_missing(
        conn,
        "escalations",
        "packet_json",
        "packet_json TEXT",
    )

    # ========================================================
    # INDEXES
    # ========================================================

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_tool_calls_decision_id
        ON tool_calls(decision_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_escalations_decision_id
        ON escalations(decision_id)
        """
    )

    conn.commit()
    conn.close()

    print()
    print("Step 9 database migration complete.")


if __name__ == "__main__":
    migrate()