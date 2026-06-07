from anthropic.types import bash_code_execution_result_block_param
import sqlite3
import json
import random
from datetime import datetime, timedelta
from database import get_connection

# Realistic vendor pools by category
# Format: (description, payee, correct_gl_code, difficulty)
# Replace your EASY, MEDIUM, HARD lists in generate_data.py with these.
# The correct codes now use the SHORT gl_codes that match your gl_codes table.

EASY = [
    ("UBER *TRIP HELP.UBER.COM", "Uber", "Travel"),
    ("LYFT *RIDE SAT 8PM", "Lyft", "Travel"),
    ("DELTA AIR 0061234567", "Delta Airlines", "Travel"),
    ("MARRIOTT HOTELS RES", "Marriott", "Travel"),
    ("AMZN MKTP US*2K4XY", "Amazon", "Office"),
    ("GOOGLE *CLOUD EMEA", "Google Cloud", "Software"),
    ("AWS EMEA SERVICES", "Amazon Web Services", "Software"),
    ("SQ *BLUE BOTTLE COFFEE", "Blue Bottle", "Meals"),
    ("STARBUCKS STORE 1234", "Starbucks", "Meals"),
    ("ZOOM.US 888-799-9666", "Zoom", "Software"),
]

MEDIUM = [
    ("FACEBK *ADS 7829", "Meta", "Marketing"),
    ("LINKEDIN PREMIUM", "LinkedIn", "Software"),
    ("WEWORK MEMBERSHIP", "WeWork", "Office"),
    ("COMCAST BUSINESS", "Comcast", "Utilities"),
    ("DROPBOX*BILLING", "Dropbox", "Software"),
    ("APPLE.COM/BILL", "Apple", "Software"),
    ("DIGITALOCEAN.COM", "DigitalOcean", "Software"),
    ("OFFICE DEPOT #221", "Office Depot", "Office"),
]

HARD = [
    ("WIRE TRANSFER JUAN MARTINEZ", "Juan Martinez", "Uncategorized"),
    ("SERVICIOS PROFESIONALES SA", "Servicios Profesionales SA", "Uncategorized"),
    ("PAYMENT REF 4492XK", "Unknown", "Uncategorized"),
    ("CONSULTORIA GLOBAL LTDA", "Consultoria Global", "Uncategorized"),
    ("TRANSFER TO ACCT 9921", "Unknown", "Uncategorized"),
    ("MONTHLY RETAINER PMT", "Unknown", "Uncategorized"),
]

CURRENCIES = [("USD", "United States", 1.0), ("BRL", "Brazil", 0.20),
              ("MXN", "Mexico", 0.059), ("EUR", "Germany", 1.08),
              ("COP", "Colombia", 0.00025)]

def generate():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM coding_log")
    # Seed currencies
    for code, country, rate in CURRENCIES:
        cursor.execute("INSERT OR IGNORE INTO currencies VALUES (?, ?, ?)", (code, country, rate))

    eval_set = []
    txn_counter = 1000

    # 50 easy, 30 medium, 20 hard
    pools = [(EASY, 50), (MEDIUM, 30), (HARD, 20)]

    for pool, count in pools:
        for i in range(count):
            desc, payee, correct = random.choice(pool)
            currency, country, _ = random.choice(CURRENCIES)
            txn_id = f"TXN-{txn_counter}"
            txn_counter += 1
            date = (datetime.now() - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d")
            amount = round(random.uniform(50, 25000), 2)

            cursor.execute("""
                INSERT OR IGNORE INTO transactions
                (transaction_id, date, payee, description, amount, currency, country, gl_code, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 'pending')
            """, (txn_id, date, payee, desc, amount, currency, country))

            eval_set.append({"transaction_id": txn_id, "correct_gl_code": correct})

    conn.commit()
    conn.close()

    # Write ground truth separately
    with open("eval_set.jsonl", "w") as f:
        for row in eval_set:
            f.write(json.dumps(row) + "\n")

    print(f"Generated {len(eval_set)} transactions and eval_set.jsonl")

if __name__ == "__main__":
    generate()