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
        "anomalies": anomalies
    }
 
    # Optionally add LLM explanations to the first few anomalies
    if explain:
        for a in anomalies[:5]:
            a["explanation"] = explain_anomaly(a)
 
    return result
 
# ---------- serve frontend ----------
app.mount("/static", StaticFiles(directory="static"), name="static")
 
@app.get("/")
def home():
    return FileResponse("static/index.html")