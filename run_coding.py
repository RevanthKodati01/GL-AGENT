from datetime import datetime
from database import get_connection
from coding import code_transaction

THRESHOLD = 80.0  # below this, escalate to human review

def run_all_pending():
    conn = get_connection()
    cursor = conn.cursor()

    # Get all transactions that haven't been coded yet
    cursor.execute("SELECT * FROM transactions WHERE status = 'pending'")
    transactions = cursor.fetchall()

    print(f"Coding {len(transactions)} pending transactions...\n")

    auto_coded = 0
    needs_review = 0

    for txn in transactions:
        gl_code, confidence, method = code_transaction(
            txn["description"], txn["payee"], txn["amount"], txn["currency"]
        )

        # Escalation logic: threshold decides auto-code vs human review
        if confidence >= THRESHOLD:
            status = "coded"
            auto_coded += 1
        else:
            status = "needs_review"
            needs_review += 1

        # Update the transaction
        cursor.execute("""
            UPDATE transactions
            SET gl_code = ?, confidence = ?, status = ?
            WHERE transaction_id = ?
        """, (gl_code, confidence, status, txn["transaction_id"]))

        # Write to the audit trail
        cursor.execute("""
            INSERT INTO coding_log (transaction_id, gl_code, confidence, reasoning, method, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            txn["transaction_id"], gl_code, confidence,
            f"Coded via {method} layer", method,
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()

    print(f"Auto-coded (confidence >= {THRESHOLD}): {auto_coded}")
    print(f"Needs human review (confidence < {THRESHOLD}): {needs_review}")
    print(f"Automation rate: {round(auto_coded/len(transactions)*100)}%")

if __name__ == "__main__":
    run_all_pending()