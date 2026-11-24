import os
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cleartide.db"

# Kept for callers that import the historical default path.
DB_PATH = DEFAULT_DB_PATH

_SCHEMA_READY: set[str] = set()


def resolve_db_path() -> Path:
    """
    Historical tests use data/cleartide.db.

    Demo and synthetic evaluation set CLEARTIDE_DB_PATH so they
    never write into that fixture database.
    """

    override = os.environ.get("CLEARTIDE_DB_PATH")

    if override:
        return Path(override).expanduser().resolve()

    return DEFAULT_DB_PATH


def _ensure_runtime_columns(conn: sqlite3.Connection) -> None:
    """Add review columns on databases created before the review workflow."""

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if "escalations" not in tables:
        return

    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(escalations)").fetchall()
    }

    statements = {
        "disposition_code":
            "ALTER TABLE escalations ADD COLUMN disposition_code TEXT",
        "reviewer_note":
            "ALTER TABLE escalations ADD COLUMN reviewer_note TEXT",
        "reviewed_by":
            "ALTER TABLE escalations ADD COLUMN reviewed_by TEXT",
    }

    for name, sql in statements.items():
        if name not in columns:
            conn.execute(sql)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_notes (
            note_id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            escalation_id INTEGER,
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()


def forget_schema_cache(path=None) -> None:
    if path is None:
        _SCHEMA_READY.clear()
        return

    _SCHEMA_READY.discard(str(Path(path).resolve()))


def get_connection():
    """
    Create a SQLite connection to the Cleartide simulated
    system of record.
    """

    path = resolve_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)

    # Makes rows accessible by column name:
    # row["account_id"] instead of row[0]
    conn.row_factory = sqlite3.Row

    # Enforce foreign-key relationships.
    conn.execute("PRAGMA foreign_keys = ON")

    key = str(path)

    if key not in _SCHEMA_READY:
        _ensure_runtime_columns(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "escalations" in tables:
            _SCHEMA_READY.add(key)

    return conn