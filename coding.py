from database import get_connection
import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def rules_layer(description):
    """
    Tier 1: deterministic keyword matching.
    Only fires when EXACTLY ONE category matches.
    Returns (gl_code, confidence, method) or None if it can't decide.
    """
    desc_lower = description.lower()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT gl_code, keyword_rules FROM gl_codes WHERE keyword_rules != ''")
    rows = cursor.fetchall()
    conn.close()

    matched_codes = []

    for row in rows:
        gl_code = row["gl_code"]
        keywords = row["keyword_rules"].split(",")
        for kw in keywords:
            kw = kw.strip()
            if kw and kw in desc_lower:
                matched_codes.append(gl_code)
                break  # one keyword hit is enough for this category

    # The key principle: only act on exactly one match
    unique_matches = list(set(matched_codes))

    if len(unique_matches) == 1:
        return (unique_matches[0], 95.0, "rules")
    else:
        return None

def llm_layer(description, payee, amount, currency):
    """
    Tier 3: LLM reasoning for transactions the rules layer couldn't handle.
    The LLM either identifies a clear category, or returns Uncategorized.
    Confidence is assigned by US based on that decision, not by the LLM.
    """
    # Get the list of valid categories to constrain the LLM
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT gl_code, category_name, description FROM gl_codes")
    codes = cursor.fetchall()
    conn.close()

    category_list = "\n".join([f"- {c['gl_code']}: {c['description']}" for c in codes])

    system_prompt = f"""You are a financial transaction categorization assistant.

Your job: assign the correct GL code to a transaction based on its description.

Available GL codes:
{category_list}

Rules:
- Only choose a category if you can identify it with reasonable confidence.
- If the description is too vague or ambiguous to know the category, return "Uncategorized".
- Never guess wildly. When unsure, return "Uncategorized".
- Respond with ONLY the gl_code, nothing else. No explanation."""

    user_message = f"""Transaction:
Description: {description}
Payee: {payee}
Amount: {amount} {currency}

What is the correct gl_code?"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=50,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    gl_code = response.content[0].text.strip()

    # WE assign confidence based on the LLM's decision, not the LLM itself
    if gl_code == "Uncategorized":
        return (gl_code, 30.0, "llm")
    else:
        return (gl_code, 75.0, "llm")

def payee_history_layer(payee):
    """
    Tier 2: learn from past validated decisions for this payee.
    Only trusts decisions that were rules-based (deterministic)
    or explicitly validated by a human. Never learns from
    low-confidence 'Uncategorized' guesses.
    """
    if not payee or payee.strip().lower() in ("unknown", ""):
        return None  # can't learn history for an unknown payee

    conn = get_connection()
    cursor = conn.cursor()

    # Find past TRUSTED codings for this payee:
    # - method = 'rules' (deterministic, always trusted), OR
    # - method = 'validated' (a human confirmed it)
    # and never 'Uncategorized'
    cursor.execute("""
        SELECT cl.gl_code, COUNT(*) as freq
        FROM coding_log cl
        JOIN transactions t ON cl.transaction_id = t.transaction_id
        WHERE t.payee = ?
          AND cl.gl_code != 'Uncategorized'
          AND cl.method IN ('rules', 'validated')
        GROUP BY cl.gl_code
        ORDER BY freq DESC
        LIMIT 1
    """, (payee,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return (row["gl_code"], 90.0, "payee_history")
    return None

def code_transaction(description, payee, amount, currency):
    # Tier 1: deterministic rules
    result = rules_layer(description)
    if result is not None:
        return result

    # Tier 2: payee history (learns from validated past decisions)
    result = payee_history_layer(payee)
    if result is not None:
        return result

    # Tier 3: LLM reasoning
    return llm_layer(description, payee, amount, currency)

if __name__ == "__main__":
    tests = [
        ("FACEBK *ADS 7829", "Meta", 500, "USD"),
        ("WIRE TRANSFER JUAN MARTINEZ", "Juan Martinez", 5000, "USD"),
        ("PAYMENT REF 4492XK", "Unknown", 1200, "USD"),
        ("CONSULTORIA GLOBAL LTDA", "Consultoria Global", 3000, "BRL"),
    ]
    for desc, payee, amt, curr in tests:
        result = code_transaction(desc, payee, amt, curr)
        print(f"{desc:40} -> {result}")