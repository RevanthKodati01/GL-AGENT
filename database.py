import sqlite3
from datetime import datetime

def get_connection():
    conn = sqlite3.connect("gl_agent.db")
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            date TEXT,
            payee TEXT,
            description TEXT,
            amount REAL,
            currency TEXT,
            country TEXT,
            gl_code TEXT,
            confidence REAL,
            status TEXT DEFAULT 'pending'
        )
    """)
    
    # GL codes - the available categories and deterministic rules
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gl_codes (
            gl_code TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            description TEXT,
            keyword_rules TEXT
        )
    """)

    # Coding log - audit trail of every decision the agent makes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coding_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT,
            gl_code TEXT,
            confidence REAL,
            reasoning TEXT,
            method TEXT,
            timestamp TEXT
        )
    """)

    # Bank statement - the bank's version of transactions, for reconciliation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bank_statement (
            bank_record_id TEXT PRIMARY KEY,
            transaction_id TEXT,
            settled_date TEXT,
            settled_amount REAL,
            currency TEXT
        )
    """)

    # Currencies - exchange rates relative to USD
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS currencies (
            currency_code TEXT PRIMARY KEY,
            country TEXT,
            usd_rate REAL
        )
    """)
    conn.commit()
    conn.close()
    print("Database initialized with transactions table.")

if __name__ == "__main__":
    initialize_database()