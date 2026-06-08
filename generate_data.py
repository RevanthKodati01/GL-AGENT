import sqlite3
import json
import random
from datetime import datetime, timedelta
from database import get_connection

# Accounts: one per country/currency
ACCOUNTS = [
    ("ACC-US",  "US Operating (USD)",   "USD", "United States"),
    ("ACC-BR",  "Brazil Ops (BRL)",     "BRL", "Brazil"),
    ("ACC-MX",  "Mexico Ops (MXN)",     "MXN", "Mexico"),
    ("ACC-EU",  "Europe Ops (EUR)",     "EUR", "Germany"),
]

CURRENCIES = [("USD","United States",1.0),("BRL","Brazil",0.20),
              ("MXN","Mexico",0.059),("EUR","Germany",1.08),("COP","Colombia",0.00025)]

# (book_payee, book_description, correct_gl_code, bank_description_variant)
# Note the bank_description is a MESSIER version - this is what fuzzy matching must handle
EASY = [
    ("Uber", "UBER *TRIP HELP.UBER.COM", "Travel", "UBER TRIP SF CA"),
    ("Lyft", "LYFT *RIDE SAT 8PM", "Travel", "LYFT RIDE 0492"),
    ("Delta Airlines", "DELTA AIR 0061234567", "Travel", "DELTA AIRLINES TKT"),
    ("Marriott", "MARRIOTT HOTELS RES", "Travel", "MARRIOTT RESORT 88"),
    ("Amazon", "AMZN MKTP US*2K4XY", "Office", "AMAZON MKTPLACE"),
    ("Google Cloud", "GOOGLE *CLOUD EMEA", "Software", "GOOGLE CLOUD SVC"),
    ("Amazon Web Services", "AWS EMEA SERVICES", "Software", "AWS CLOUD EMEA"),
    ("Blue Bottle", "SQ *BLUE BOTTLE COFFEE", "Meals", "SQ BLUE BOTTLE"),
    ("Starbucks", "STARBUCKS STORE 1234", "Meals", "STARBUCKS #1234"),
    ("Zoom", "ZOOM.US 888-799-9666", "Software", "ZOOM VIDEO COMM"),
]

MEDIUM = [
    ("Meta", "FACEBK *ADS 7829", "Marketing", "FACEBOOK ADS"),
    ("LinkedIn", "LINKEDIN PREMIUM", "Software", "LINKEDIN PREM SUB"),
    ("WeWork", "WEWORK MEMBERSHIP", "Office", "WEWORK MONTHLY"),
    ("Comcast", "COMCAST BUSINESS", "Utilities", "COMCAST BIZ INTERNET"),
    ("Dropbox", "DROPBOX*BILLING", "Software", "DROPBOX BILLING"),
    ("Apple", "APPLE.COM/BILL", "Software", "APPLE.COM BILL"),
    ("DigitalOcean", "DIGITALOCEAN.COM", "Software", "DIGITALOCEAN LLC"),
    ("Office Depot", "OFFICE DEPOT #221", "Office", "OFFICE DEPOT 221"),
]

HARD = [
    ("Juan Martinez", "WIRE TRANSFER JUAN MARTINEZ", "Uncategorized", "WIRE JUAN MARTINEZ"),
    ("Servicios Profesionales SA", "SERVICIOS PROFESIONALES SA", "Uncategorized", "SERV PROF SA DE CV"),
    ("Unknown", "PAYMENT REF 4492XK", "Uncategorized", "PMT REF 4492XK"),
    ("Consultoria Global", "CONSULTORIA GLOBAL LTDA", "Uncategorized", "CONSULT GLOBAL LTDA"),
    ("Unknown", "TRANSFER TO ACCT 9921", "Uncategorized", "XFER ACCT 9921"),
    ("Unknown", "MONTHLY RETAINER PMT", "Uncategorized", "RETAINER PYMT"),
]

def generate():
    conn = get_connection()
    cursor = conn.cursor()

    # Clear everything for a clean run
    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM coding_log")
    cursor.execute("DELETE FROM bank_statement")
    cursor.execute("DELETE FROM accounts")
    cursor.execute("DELETE FROM currencies")

    # Seed accounts
    for acc in ACCOUNTS:
        cursor.execute("INSERT INTO accounts VALUES (?,?,?,?)", acc)

    # Seed currencies
    for c in CURRENCIES:
        cursor.execute("INSERT INTO currencies VALUES (?,?,?)", c)

    eval_set = []
    txn_counter = 1000
    bank_counter = 5000

    # We store (book record + its true bank variant) so we can generate
    # a realistic bank statement that corresponds but is distorted.
    txns_for_bank = []

    pools = [(EASY, 50), (MEDIUM, 30), (HARD, 20)]
    for pool, count in pools:
        for _ in range(count):
            payee, desc, correct, bank_desc = random.choice(pool)
            account = random.choice(ACCOUNTS)
            acc_id, _, acc_currency, acc_country = account
            txn_id = f"TXN-{txn_counter}"; txn_counter += 1
            date = (datetime.now() - timedelta(days=random.randint(1,90)))
            amount = round(random.uniform(50, 25000), 2)

            cursor.execute("""
                INSERT INTO transactions
                (transaction_id, account_id, date, payee, description, amount, currency, country, gl_code, confidence, status)
                VALUES (?,?,?,?,?,?,?,?,NULL,NULL,'pending')
            """, (txn_id, acc_id, date.strftime("%Y-%m-%d"), payee, desc, amount, acc_currency, acc_country))

            eval_set.append({"transaction_id": txn_id, "correct_gl_code": correct})
            txns_for_bank.append({
                "account_id": acc_id, "date": date, "amount": amount,
                "currency": acc_currency, "bank_desc": bank_desc
            })

    # ---- Generate the bank statement ----
    # 85% get a matching (distorted) bank record, 8% missing, plus 7% orphans
    for t in txns_for_bank:
        roll = random.random()
        if roll < 0.08:
            continue  # MISSING - no bank record created

        bank_id = f"BR-{bank_counter}"; bank_counter += 1
        # Distort amount: fee 0.1-0.5% + FX noise
        fee = random.uniform(0.001, 0.005)
        fx = random.uniform(-0.002, 0.002)
        settled_amount = round(t["amount"] * (1 - fee + fx), 2)
        # Distort date: 0-3 days later
        settled_date = (t["date"] + timedelta(days=random.randint(0,3))).strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO bank_statement
            (bank_record_id, account_id, settled_date, settled_amount, currency, bank_description)
            VALUES (?,?,?,?,?,?)
        """, (bank_id, t["account_id"], settled_date, settled_amount, t["currency"], t["bank_desc"]))

    # ORPHANS: bank records with no corresponding book transaction
    num_orphans = int(len(txns_for_bank) * 0.07)
    orphan_descs = ["UNKNOWN VENDOR XYZ", "REFUND PROCESSOR", "FX ADJUSTMENT", "BANK FEE REVERSAL", "MISC CREDIT"]
    for _ in range(num_orphans):
        bank_id = f"BR-{bank_counter}"; bank_counter += 1
        acc = random.choice(ACCOUNTS)
        settled_date = (datetime.now() - timedelta(days=random.randint(1,90))).strftime("%Y-%m-%d")
        settled_amount = round(random.uniform(100, 20000), 2)
        cursor.execute("""
            INSERT INTO bank_statement
            (bank_record_id, account_id, settled_date, settled_amount, currency, bank_description)
            VALUES (?,?,?,?,?,?)
        """, (bank_id, acc[0], settled_date, settled_amount, acc[2], random.choice(orphan_descs)))

    conn.commit()

    # Write ground truth for GL coding eval
    with open("eval_set.jsonl", "w") as f:
        for row in eval_set:
            f.write(json.dumps(row) + "\n")

    # Report
    cursor.execute("SELECT COUNT(*) FROM transactions"); ntxn = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bank_statement"); nbank = cursor.fetchone()[0]
    conn.close()
    print(f"Generated {ntxn} transactions across {len(ACCOUNTS)} accounts")
    print(f"Generated {nbank} bank records (independent, no shared IDs)")
    print(f"Wrote eval_set.jsonl with {len(eval_set)} ground-truth labels")

if __name__ == "__main__":
    generate()