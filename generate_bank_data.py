import random
from datetime import datetime, timedelta
from database import get_connection

def generate_bank_statement():
    conn = get_connection()
    cursor = conn.cursor()

    # Clear old bank data so reruns are clean
    cursor.execute("DELETE FROM bank_statement")

    # Get all transactions from our books
    cursor.execute("SELECT * FROM transactions")
    transactions = cursor.fetchall()

    bank_counter = 5000
    missing_count = 0
    orphan_count = 0
    matched_count = 0

    for txn in transactions:
        roll = random.random()

        if roll < 0.08:
            # MISSING: transaction exists in books but NOT at bank.
            # We simply skip creating a bank record. Nothing to insert.
            missing_count += 1
            continue

        # MATCHED (85%): create a bank record with realistic distortions
        bank_id = f"BR-{bank_counter}"
        bank_counter += 1

        # Distortion 1: settlement date is 0-3 days later
        txn_date = datetime.strptime(txn["date"], "%Y-%m-%d")
        settled_date = (txn_date + timedelta(days=random.randint(0, 3))).strftime("%Y-%m-%d")

        # Distortion 2: amount shifts slightly from fees + FX
        # Small fee (0.1% to 0.5%) plus tiny FX noise
        fee_pct = random.uniform(0.001, 0.005)
        fx_noise = random.uniform(-0.002, 0.002)
        settled_amount = round(txn["amount"] * (1 - fee_pct + fx_noise), 2)

        cursor.execute("""
            INSERT INTO bank_statement (bank_record_id, transaction_id, settled_date, settled_amount, currency)
            VALUES (?, ?, ?, ?, ?)
        """, (bank_id, txn["transaction_id"], settled_date, settled_amount, txn["currency"]))
        matched_count += 1

    # ORPHANS (7%): bank records with transaction_ids that don't exist
    num_orphans = int(len(transactions) * 0.07)
    for i in range(num_orphans):
        bank_id = f"BR-{bank_counter}"
        bank_counter += 1
        fake_txn_id = f"TXN-FAKE-{i}"  # deliberately doesn't exist in our books
        settled_date = (datetime.now() - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d")
        settled_amount = round(random.uniform(100, 20000), 2)
        currency = random.choice(["USD", "BRL", "MXN", "EUR"])
        cursor.execute("""
            INSERT INTO bank_statement (bank_record_id, transaction_id, settled_date, settled_amount, currency)
            VALUES (?, ?, ?, ?, ?)
        """, (bank_id, fake_txn_id, settled_date, settled_amount, currency))
        orphan_count += 1

    conn.commit()
    conn.close()

    print(f"Bank statement generated:")
    print(f"  Matched records: {matched_count}")
    print(f"  Missing (in books, not at bank): {missing_count}")
    print(f"  Orphan (at bank, not in books): {orphan_count}")

if __name__ == "__main__":
    generate_bank_statement()