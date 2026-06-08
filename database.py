import sqlite3

def get_connection():
    conn = sqlite3.connect("gl_agent.db")
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    # Transactions - the company's books. Now with account_id.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            account_id TEXT,
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

    # GL codes - categories and deterministic keyword rules
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gl_codes (
            gl_code TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            description TEXT,
            keyword_rules TEXT
        )
    """)

    # Coding log - audit trail of every coding decision
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

    # Bank statement - the bank's INDEPENDENT record.
    # No transaction_id. The bank does not know our internal IDs.
    # Matching must be earned via fuzzy comparison.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bank_statement (
            bank_record_id TEXT PRIMARY KEY,
            account_id TEXT,
            settled_date TEXT,
            settled_amount REAL,
            currency TEXT,
            bank_description TEXT
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

    # Accounts - the company's bank accounts (one per country/currency)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            account_name TEXT,
            currency TEXT,
            country TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized (with accounts + independent bank statement).")

if __name__ == "__main__":
    initialize_database()