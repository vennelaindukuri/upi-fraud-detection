"""SQLite storage and small query helpers."""
import sqlite3
from pathlib import Path
from config import DB_PATH


def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS transactions (
          txn_id TEXT PRIMARY KEY, sender_id TEXT, receiver_id TEXT, amount REAL,
          timestamp TEXT, hour INTEGER, device_id TEXT, location TEXT,
          is_new_receiver INTEGER, is_fraud INTEGER DEFAULT 0,
          decision TEXT DEFAULT 'ALLOW', risk_score REAL DEFAULT 0,
          latency_ms REAL DEFAULT 0
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sender_time ON transactions(sender_id, timestamp)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_receiver ON transactions(receiver_id)")
        con.execute("""CREATE TABLE IF NOT EXISTS users (
          upi_id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
          typical_amount REAL NOT NULL, usual_device TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS receivers (
          upi_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
          account_age_days REAL DEFAULT 0, receiver_risk_score REAL DEFAULT 0,
          is_flagged INTEGER DEFAULT 0, qr_name TEXT
        )""")


def seed_from_csv(csv_path):
    import pandas as pd
    df = pd.read_csv(csv_path)
    rows = df[["txn_id", "sender_id", "receiver_id", "amount", "timestamp", "hour", "device_id", "location", "is_new_receiver", "is_fraud"]]
    with connect() as con:
        existing = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
        if not existing:
            rows.to_sql("transactions", con, if_exists="append", index=False)


def recent_history(sender_id, now, hours=24*30):
    with connect() as con:
        return con.execute("SELECT * FROM transactions WHERE sender_id=? AND timestamp < ? AND timestamp >= datetime(?, ?) ORDER BY timestamp",
            (sender_id, now.isoformat(sep=" "), now.isoformat(sep=" "), f"-{hours} hours")).fetchall()


def insert_transaction(txn):
    with connect() as con:
        con.execute("""INSERT INTO transactions (txn_id,sender_id,receiver_id,amount,timestamp,hour,device_id,location,is_new_receiver,is_fraud,decision,risk_score,latency_ms)
        VALUES (:txn_id,:sender_id,:receiver_id,:amount,:timestamp,:hour,:device_id,:location,:is_new_receiver,:is_fraud,:decision,:risk_score,:latency_ms)""", txn)


def reset_demo_tables():
    """Deliberately reset only the fictional demo ecosystem; safe to repeat."""
    with connect() as con:
        con.execute("DROP TABLE IF EXISTS transactions")
        con.execute("DROP TABLE IF EXISTS users")
        con.execute("DROP TABLE IF EXISTS receivers")
    init_db()
