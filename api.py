import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
 
from database import get_connection, initialize_database
from coding import code_transaction
from reconcile import reconcile, explain_anomaly
 
load_dotenv()
 
app = FastAPI(title="GL Coding & Reconciliation Agent")
initialize_database()
 
THRESHOLD = 80.0
 
# ---------- MODELS ----------
class ValidateRequest(BaseModel):
    transaction_id: str
    gl_code: str
 
# ---------- HEALTH ----------
@app.get("/health")
def health():
    return {"status": "running", "service": "GL Coding & Reconciliation Agent"}
 
# ---------- ACTION: run coding on all pending ----------
@app.post("/code/run")
def run_coding():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE status = 'pending'")
    pending = cursor.fetchall()
 
    auto_coded = 0
    needs_review = 0
 
    for txn in pending:
        gl_code, confidence, method = code_transaction(
            txn["description"], txn["payee"], txn["amount"], txn["currency"]
        )
        status = "coded" if confidence >= THRESHOLD else "needs_review"
        if status == "coded":
            auto_coded += 1
        else:
            needs_review += 1
 
        cursor.execute("""
            UPDATE transactions SET gl_code=?, confidence=?, status=?
            WHERE transaction_id=?
        """, (gl_code, confidence, status, txn["transaction_id"]))
 
        cursor.execute("""
            INSERT INTO coding_log (transaction_id, gl_code, confidence, reasoning, method, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (txn["transaction_id"], gl_code, confidence,
              f"Coded via {method} layer", method, datetime.now().isoformat()))
 
    conn.commit()
    conn.close()
 
    total = len(pending)
    return {
        "processed": total,
        "auto_coded": auto_coded,
        "needs_review": needs_review,
        "automation_rate": round(auto_coded / total * 100) if total else 0
    }
 
# ---------- ACTION: human validates a reviewed transaction ----------
@app.post("/validate")
def validate(req: ValidateRequest):
    conn = get_connection()
    cursor = conn.cursor()
 
    # Update the transaction with the human's decision
    cursor.execute("""
        UPDATE transactions SET gl_code=?, confidence=100.0, status='coded'
        WHERE transaction_id=?
    """, (req.gl_code, req.transaction_id))
 
    # Log it as 'validated' so payee-history can trust it
    cursor.execute("""
        INSERT INTO coding_log (transaction_id, gl_code, confidence, reasoning, method, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (req.transaction_id, req.gl_code, 100.0,
          "Human validated", "validated", datetime.now().isoformat()))
 
    conn.commit()
    conn.close()
    return {"message": f"Transaction {req.transaction_id} validated as {req.gl_code}"}
 
# ---------- VIEW: coded transactions ----------
@app.get("/transactions/coded")
def get_coded():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT transaction_id, description, payee, amount, currency, gl_code, confidence
        FROM transactions WHERE status='coded'
        ORDER BY confidence DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"count": len(rows), "transactions": rows}
 
# ---------- VIEW: needs-review queue ----------
@app.get("/transactions/review")
def get_review_queue():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT transaction_id, description, payee, amount, currency, gl_code, confidence
        FROM transactions WHERE status='needs_review'
        ORDER BY confidence ASC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"count": len(rows), "transactions": rows}
 
# ---------- VIEW/ACTION: reconciliation ----------
@app.get("/reconcile")
def run_reconcile(explain: bool = False):
    reconciled, anomalies = reconcile()

    result = {
        "reconciled_count": len(reconciled),
        "anomaly_count": len(anomalies),
        "matches": reconciled[:50],   # show sample of confident fuzzy matches with scores
        "anomalies": anomalies
    }

    if explain:
        for a in anomalies[:5]:
            a["explanation"] = explain_anomaly(a)

    return result
# ---------- serve frontend ----------
app.mount("/static", StaticFiles(directory="static"), name="static")
 
@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/summary")
def spend_summary():
    conn = get_connection()
    cursor = conn.cursor()

    # Load currency rates into a lookup
    cursor.execute("SELECT currency_code, usd_rate FROM currencies")
    rates = {r["currency_code"]: r["usd_rate"] for r in cursor.fetchall()}

    # Get all coded transactions
    cursor.execute("""
        SELECT gl_code, amount, currency FROM transactions
        WHERE status = 'coded' AND gl_code IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()

    # Group by gl_code, summing USD-converted amounts
    summary = {}
    for r in rows:
        rate = rates.get(r["currency"], 1.0)
        usd_value = r["amount"] * rate
        if r["gl_code"] not in summary:
            summary[r["gl_code"]] = {"total_usd": 0, "count": 0}
        summary[r["gl_code"]]["total_usd"] += usd_value
        summary[r["gl_code"]]["count"] += 1

    # Format into a sorted list, biggest spend first
    result = []
    for gl_code, data in summary.items():
        result.append({
            "gl_code": gl_code,
            "total_usd": round(data["total_usd"], 2),
            "transaction_count": data["count"]
        })
    result.sort(key=lambda x: x["total_usd"], reverse=True)

    grand_total = round(sum(x["total_usd"] for x in result), 2)

    return {"grand_total_usd": grand_total, "buckets": result}