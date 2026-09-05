import sqlite3
from pathlib import Path


DB_PATH = Path("data/cleartide.db")


def create_database():
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id INTEGER PRIMARY KEY,
        customer_name TEXT NOT NULL,
        balance REAL NOT NULL,
        days_past_due INTEGER NOT NULL,
        risk_score REAL
    )
    """)

    conn.commit()
    conn.close()

    print(f"Cleartide database created at: {DB_PATH}")


if __name__ == "__main__":
    create_database()