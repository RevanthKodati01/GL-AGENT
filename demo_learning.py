from datetime import datetime
from database import get_connection
from coding import code_transaction

def simulate_human_validation(payee, gl_code):
    """
    Simulates a human reviewing an Uncategorized transaction
    and assigning the correct code. This writes a 'validated'
    entry to the coding_log that the payee-history layer will trust.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Find a transaction from this payee to attach the validation to
    cursor.execute("SELECT transaction_id FROM transactions WHERE payee = ? LIMIT 1", (payee,))
    row = cursor.fetchone()
    if not row:
        print(f"No transaction found for payee {payee}")
        conn.close()
        return

    cursor.execute("""
        INSERT INTO coding_log (transaction_id, gl_code, confidence, reasoning, method, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (row["transaction_id"], gl_code, 100.0,
          f"Human validated {payee} as {gl_code}", "validated",
          datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"Human validated: {payee} -> {gl_code}")


if __name__ == "__main__":
    payee = "Juan Martinez"

    print("=== BEFORE human validation ===")
    result = code_transaction("WIRE TRANSFER JUAN MARTINEZ", payee, 5000, "USD")
    print(f"Agent codes Juan as: {result}\n")

    print("=== Human reviews and validates ===")
    simulate_human_validation(payee, "Contractor")
    print()

    print("=== AFTER human validation ===")
    result = code_transaction("WIRE TRANSFER JUAN MARTINEZ", payee, 5000, "USD")
    print(f"Agent codes Juan as: {result}")