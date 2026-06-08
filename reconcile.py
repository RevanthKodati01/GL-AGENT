import os
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from rapidfuzz import fuzz
from database import get_connection

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Scoring weights - amount trusted most, date least (settlement noise)
W_AMOUNT = 0.5
W_DATE   = 0.2
W_PAYEE  = 0.3

MATCH_THRESHOLD = 0.70   # best candidate must score >= this to be a confident match
AMBIGUITY_GAP   = 0.05   # if #1 and #2 are closer than this, it's ambiguous -> review


def amount_score(book_amt, bank_amt):
    """1.0 = identical, decays as percentage difference grows."""
    if book_amt == 0:
        return 0.0
    diff_pct = abs(book_amt - bank_amt) / book_amt
    return max(0.0, 1.0 - diff_pct)


def date_score(book_date_str, bank_date_str):
    """1.0 = same day, 0.0 once 7+ days apart."""
    d1 = datetime.strptime(book_date_str, "%Y-%m-%d")
    d2 = datetime.strptime(bank_date_str, "%Y-%m-%d")
    days = abs((d1 - d2).days)
    return max(0.0, 1.0 - days / 7.0)


def payee_score(book_desc, bank_desc):
    """Fuzzy string similarity 0-1 using rapidfuzz token_set_ratio."""
    return fuzz.token_set_ratio(book_desc.lower(), bank_desc.lower()) / 100.0


def score_pair(txn, bank):
    """Combined weighted match score between one transaction and one bank record."""
    a = amount_score(txn["amount"], bank["settled_amount"])
    d = date_score(txn["date"], bank["settled_date"])
    p = payee_score(txn["description"], bank["bank_description"])
    total = W_AMOUNT * a + W_DATE * d + W_PAYEE * p
    return total, {"amount": round(a,3), "date": round(d,3), "payee": round(p,3)}


def reconcile():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions")
    transactions = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM bank_statement")
    bank_records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Track which bank records get consumed by a match
    matched_bank_ids = set()

    reconciled = []
    anomalies = []

    # ---- Pass 1: for each book transaction, find best bank match WITHIN SAME ACCOUNT ----
    for txn in transactions:
        # candidate bank records: same account, not already matched
        candidates = [b for b in bank_records
                      if b["account_id"] == txn["account_id"]
                      and b["bank_record_id"] not in matched_bank_ids]

        if not candidates:
            anomalies.append({
                "type": "MISSING",
                "transaction_id": txn["transaction_id"],
                "detail": f"{txn['description']} ({txn['amount']} {txn['currency']}) has no candidate bank record in account {txn['account_id']}"
            })
            continue

        # score against every candidate
        scored = []
        for b in candidates:
            total, breakdown = score_pair(txn, b)
            scored.append((total, b, breakdown))
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_bank, best_breakdown = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0

        if best_score < MATCH_THRESHOLD:
            # nothing good enough -> the transaction is unmatched
            anomalies.append({
                "type": "MISSING",
                "transaction_id": txn["transaction_id"],
                "detail": f"{txn['description']} ({txn['amount']} {txn['currency']}) best match scored only {round(best_score,2)} - below threshold"
            })
        elif (best_score - second_score) < AMBIGUITY_GAP and second_score >= MATCH_THRESHOLD:
            # two candidates too close -> ambiguous, flag for human
            anomalies.append({
                "type": "AMBIGUOUS",
                "transaction_id": txn["transaction_id"],
                "detail": f"{txn['description']} matches 2 bank records too closely ({round(best_score,2)} vs {round(second_score,2)}) - needs human"
            })
        else:
            # confident match
            matched_bank_ids.add(best_bank["bank_record_id"])
            reconciled.append({
                "transaction_id": txn["transaction_id"],
                "bank_record_id": best_bank["bank_record_id"],
                "score": round(best_score, 3),
                "breakdown": best_breakdown
            })

    # ---- Pass 2: any bank record never matched is an ORPHAN ----
    for b in bank_records:
        if b["bank_record_id"] not in matched_bank_ids:
            anomalies.append({
                "type": "ORPHAN",
                "transaction_id": b["bank_record_id"],
                "detail": f"Bank record {b['bank_record_id']} ({b['bank_description']}, {b['settled_amount']} {b['currency']}) has no matching transaction in account {b['account_id']}"
            })

    # ---- Report ----
    print("=" * 60)
    print("RECONCILIATION REPORT (fuzzy matching, multi-account)")
    print("=" * 60)
    print(f"\nConfident matches: {len(reconciled)}")
    print(f"Anomalies: {len(anomalies)}")
    by_type = {}
    for a in anomalies:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
    print("Anomaly breakdown:", by_type)
    print("\nSample confident matches:")
    for r in reconciled[:5]:
        print(f"  {r['transaction_id']} <-> {r['bank_record_id']} score={r['score']} {r['breakdown']}")
    print("\nSample anomalies:")
    for a in anomalies[:5]:
        print(f"  [{a['type']}] {a['detail']}")

    return reconciled, anomalies


def explain_anomaly(anomaly):
    """LLM explains a flagged anomaly. Python decided it's an anomaly; LLM only communicates."""
    system_prompt = """You are a financial reconciliation assistant.
A reconciliation engine has already flagged this item as an anomaly.
Explain in 2-3 sentences: what it means, likely causes, and what a human should check.
Be concise and practical. No preamble."""
    user_message = f"""Anomaly type: {anomaly['type']}
Reference: {anomaly['transaction_id']}
Detail: {anomaly['detail']}

Explain and recommend next steps."""
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    return response.content[0].text.strip()


if __name__ == "__main__":
    reconcile()