import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "data" / "cleartide.db"


def get_connection():
    """
    Create a SQLite connection to the Cleartide simulated
    system of record.
    """

    conn = sqlite3.connect(DB_PATH)

    # Makes rows accessible by column name:
    # row["account_id"] instead of row[0]
    conn.row_factory = sqlite3.Row

    # Enforce foreign-key relationships.
    conn.execute("PRAGMA foreign_keys = ON")

    return conn