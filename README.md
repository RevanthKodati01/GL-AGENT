# GL Coding & Reconciliation Agent

An AI agent that automatically assigns general-ledger codes to financial transactions and reconciles them against bank statements. It categorizes what it can confidently, and flags the rest for human review.

Built with Python and the Anthropic API. No agent frameworks. Every line is explainable.

---

## The problem

Every business transaction has to be assigned a general-ledger code. Is this expense Travel, Software, or Marketing? Today this is largely manual: a person reviews each transaction and categorizes it by hand. At thousands of transactions a month it is slow, repetitive, and error-prone, and a miscoded transaction silently distorts the company's financial reports.

Reconciliation is the same story. Companies must match their internal books against their bank statements to confirm the money actually moved as recorded. It is a legal necessity, but done manually it means checking thousands of records line by line across multiple accounts and currencies, and it is easy to miss the cases that matter most, like a payment that left the books but never settled at the bank.

This project automates both.

---

## What it does

**Tiered GL coding.** Each transaction is categorized through three layers, tried in order:

1. A deterministic rules layer that matches known keywords (UBER to Travel, AWS to Software). Fast, free, and reliable. Handles roughly three quarters of transactions.
2. A payee-history layer that learns from past human-validated decisions. Once a human confirms an unknown payee's category, the agent applies it automatically next time.
3. An LLM layer (Claude) for the genuinely ambiguous transactions, which either identifies a category or returns Uncategorized.

**Confidence-based escalation.** Confidence does not come from the LLM rating itself. It comes from which tier handled the transaction: rules score 95, payee-history 90, the LLM 75 for a confident call, and 30 when it abstains. Anything below an 80 threshold is routed to a human review queue instead of being committed to the books.

**Learning from corrections.** When a human validates a previously uncategorized transaction, that decision is recorded and reused. The uncategorized pile shrinks over time without anyone maintaining a vendor list.

**Reconciliation with fuzzy matching.** The agent matches the company's books against an independent bank statement that shares no transaction IDs, the way a real bank statement works. It scores each potential match on three weighted signals: amount closeness, date closeness, and payee-text similarity. Matching happens within each account. Confident matches are reconciled, ambiguous ones (where two records score too closely) are flagged for a human, and unmatched records are surfaced as anomalies.

**Anomaly detection.** Reconciliation surfaces three kinds of problems: MISSING (a transaction in the books with no bank settlement), ORPHAN (a bank record with no matching transaction), and AMBIGUOUS (a transaction that matches two bank records too closely to decide automatically). Flagged anomalies are explained in plain language by the LLM to speed up human investigation.

**Evaluation with calibration.** A separate eval harness measures the agent against a held-out set of ground-truth labels. It reports overall accuracy, accuracy per category, and calibration: when the agent claims a confidence level, how often it is actually right at that level.

**CFO dashboard.** A web dashboard shows spend by category in a common currency (USD-equivalent), coded transactions, the human-review queue, reconciliation matches with their score breakdowns, and flagged anomalies.

---

## Architecture: the core principle

The LLM never makes the final committed decision on its own.

Deterministic logic decides what gets auto-committed. The rules layer and reconciliation tolerance checks are pure Python. The LLM is used for two things only: categorizing genuinely ambiguous transactions (and even then its output is routed to human review, not auto-committed), and explaining flagged anomalies in plain language. Python decides; the LLM communicates.

This matters in finance because a confident wrong answer is worse than an honest "I don't know." A wrong GL code looks correct and silently corrupts the books. A wrong reconciliation match hides a real discrepancy. So the system is designed to abstain and escalate rather than guess.

---

## The eval finding

The eval measures calibration, not just accuracy, and it surfaced something that drove the architecture.

The rules tier is 100 percent accurate and slightly under-confident (it claims 95, never misses). The LLM tier claims 75 percent confidence but measures only 42 to 62 percent accurate depending on the dataset. It is consistently overconfident.

That finding is exactly why LLM decisions are never auto-committed. The data validated the decision to keep the LLM below the auto-commit threshold and route its output to human review.

Overall accuracy runs in the high 80s to mid 90s across datasets. Every concrete category (Travel, Software, Meals, and so on) scores 100 percent; all variation is in the genuinely ambiguous Uncategorized bucket, which is expected.

Automation rate (transactions coded without human review) holds steady around 72 to 78 percent across fresh datasets, because it is driven by deterministic rules coverage rather than tuned to one batch.

---

## Tech stack

- Python
- FastAPI (REST API and dashboard server)
- SQLite (transactions, GL codes, audit log, bank statement, accounts, currencies)
- Anthropic API (Claude) for the LLM tier and anomaly explanations
- RapidFuzz for fuzzy string matching in reconciliation
- Deployed on Railway

---

## How to run it

```bash
# install dependencies
pip install -r requirements.txt

# set your API key
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# initialize and seed
python database.py
python seed_gl_codes.py
python generate_data.py

# run the coding agent
python run_coding.py

# evaluate
python eval.py

# run reconciliation
python reconcile.py

# start the dashboard
uvicorn api:app --reload
# open http://127.0.0.1:8000
```

---

## What I would do next

This is a working prototype, and there are real limitations I scoped out deliberately:

- **Reconciliation matching** handles fuzzy one-to-one matching within an account. It does not yet handle many-to-one settlement (one bank deposit covering several invoices) or cross-currency matching where a payment settles in a different currency than it was booked in. Fuzzy one-to-many matching would be the next priority.
- **Currency conversion** in the CFO summary uses a single reference rate per currency. Production would store the historical rate at transaction time.
- **The confidence thresholds and matching weights** are set conservatively by reasoning, then checked against the eval. A production system would tune them continuously against measured accuracy.
- **Access and security**: the agent has read access to a synthetic dataset. In production it would have scoped, audited, read-only access, never the ability to move money.

---

## A note on synthetic data

The transactions and bank statement are synthetically generated to model a real company's data: messy bank descriptions, multiple currencies and accounts, fees and FX distortions, settlement delays, and deliberately planted anomalies (missing and orphan records). Ground-truth labels for evaluation are stored separately from the data the agent sees, to prevent leakage.
