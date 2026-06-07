import json
from collections import defaultdict
from database import get_connection

def load_ground_truth(path="eval_set.jsonl"):
    """Load the correct answers from the separate ground truth file."""
    truth = {}
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            truth[row["transaction_id"]] = row["correct_gl_code"]
    return truth

def run_eval():
    truth = load_ground_truth()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT transaction_id, gl_code, confidence, status FROM transactions")
    results = cursor.fetchall()
    conn.close()

    total = 0
    correct = 0

    # Per-category tracking
    category_total = defaultdict(int)
    category_correct = defaultdict(int)

    # Calibration tracking: group by confidence level
    confidence_buckets = defaultdict(lambda: {"total": 0, "correct": 0})

    for row in results:
        txn_id = row["transaction_id"]
        if txn_id not in truth:
            continue  # only evaluate transactions we have ground truth for

        predicted = row["gl_code"]
        actual = truth[txn_id]
        confidence = row["confidence"]

        total += 1
        is_correct = (predicted == actual)
        if is_correct:
            correct += 1

        # Per category (by the TRUE category)
        category_total[actual] += 1
        if is_correct:
            category_correct[actual] += 1

        # Calibration: bucket by confidence
        confidence_buckets[confidence]["total"] += 1
        if is_correct:
            confidence_buckets[confidence]["correct"] += 1

    # ---- REPORT ----
    print("=" * 50)
    print("GL CODING AGENT - EVALUATION REPORT")
    print("=" * 50)

    print(f"\nOVERALL ACCURACY: {correct}/{total} = {round(correct/total*100, 1)}%\n")

    print("ACCURACY BY CATEGORY:")
    for cat in sorted(category_total.keys()):
        t = category_total[cat]
        c = category_correct[cat]
        print(f"  {cat:25} {c}/{t} = {round(c/t*100)}%")

    print("\nCALIBRATION (is confidence honest?):")
    print("  When agent says X% confident, how often is it actually right?")
    for conf in sorted(confidence_buckets.keys(), reverse=True):
        bucket = confidence_buckets[conf]
        actual_accuracy = round(bucket["correct"]/bucket["total"]*100)
        print(f"  Claimed {conf}% -> Actually correct {actual_accuracy}% ({bucket['correct']}/{bucket['total']})")

if __name__ == "__main__":
    run_eval()