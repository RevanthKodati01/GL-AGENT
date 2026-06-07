from database import get_connection
import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
TOLERANCE = 0.01  # 1% - differences within this are explainable (fees/FX)

def reconcile():
    conn = get_connection()
    cursor = conn.cursor()

    # Load all transactions (our books) and bank records
    cursor.execute("SELECT * FROM transactions")
    transactions = {t["transaction_id"]: t for t in cursor.fetchall()}

    cursor.execute("SELECT * FROM bank_statement")
    bank_records = cursor.fetchall()

    # Build a lookup of which transaction_ids the bank has
    bank_by_txn = {}
    for b in bank_records:
        bank_by_txn[b["transaction_id"]] = b

    conn.close()

    reconciled = []
    anomalies = []

    # ---- Pass 1: check every transaction in our books ----
    for txn_id, txn in transactions.items():
        if txn_id not in bank_by_txn:
            # MISSING: in our books, no bank record
            anomalies.append({
                "type": "MISSING",
                "transaction_id": txn_id,
                "detail": f"Transaction of {txn['amount']} {txn['currency']} has no bank settlement record"
            })
            continue

        bank = bank_by_txn[txn_id]
        diff = abs(txn["amount"] - bank["settled_amount"])
        diff_pct = diff / txn["amount"]

        if diff_pct <= TOLERANCE:
            # MATCHED within tolerance - explainable
            reconciled.append({
                "transaction_id": txn_id,
                "book_amount": txn["amount"],
                "bank_amount": bank["settled_amount"],
                "diff_pct": round(diff_pct * 100, 3),
                "status": "RECONCILED"
            })
        else:
            # Difference too large - anomaly
            anomalies.append({
                "type": "AMOUNT_MISMATCH",
                "transaction_id": txn_id,
                "detail": f"Books say {txn['amount']}, bank says {bank['settled_amount']} ({round(diff_pct*100,1)}% difference)"
            })

    # ---- Pass 2: check for orphan bank records ----
    for b in bank_records:
        if b["transaction_id"] not in transactions:
            # ORPHAN: bank has it, our books don't
            anomalies.append({
                "type": "ORPHAN",
                "transaction_id": b["transaction_id"],
                "detail": f"Bank record {b['bank_record_id']} for {b['settled_amount']} {b['currency']} has no matching transaction in books"
            })

    # ---- Report ----
    print("=" * 55)
    print("RECONCILIATION REPORT")
    print("=" * 55)
    print(f"\nReconciled (matched within {TOLERANCE*100}% tolerance): {len(reconciled)}")
    print(f"Anomalies requiring investigation: {len(anomalies)}\n")

    # Break down anomalies by type
    by_type = {}
    for a in anomalies:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
    print("ANOMALY BREAKDOWN:")
    for atype, count in by_type.items():
        print(f"  {atype}: {count}")

    print("\nSAMPLE ANOMALIES:")
    for a in anomalies[:8]:
        print(f"  [{a['type']}] {a['transaction_id']}: {a['detail']}")

    return reconciled, anomalies
def explain_anomaly(anomaly):
    """
    LLM explains a flagged anomaly in plain language.
    The LLM does NOT decide if it's an anomaly - Python already did.
    The LLM only explains and suggests next steps for the human investigator.
    """
    system_prompt = """You are a financial reconciliation assistant.
A reconciliation engine has already flagged this item as an anomaly.
Your job is NOT to decide if it's a problem - that's already determined.
Your job is to explain in 2-3 sentences: what the anomaly means,
the most likely causes, and what a human should check.
Be concise and practical. No preamble."""

    user_message = f"""Anomaly type: {anomaly['type']}
Transaction ID: {anomaly['transaction_id']}
Detail: {anomaly['detail']}

Explain this anomaly and recommend next steps."""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    return response.content[0].text.strip()
if __name__ == "__main__":
    reconciled, anomalies = reconcile()

    print("\n" + "=" * 55)
    print("LLM EXPLANATIONS (first 3 anomalies)")
    print("=" * 55)
    for a in anomalies[:3]:
        print(f"\n[{a['type']}] {a['transaction_id']}")
        print(f"Raw: {a['detail']}")
        print(f"Explanation: {explain_anomaly(a)}")