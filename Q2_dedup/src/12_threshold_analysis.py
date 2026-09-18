from pathlib import Path
import pandas as pd
import re

DATA = Path("../data")

# ---------------------------------------------------------
# Load notices
# ---------------------------------------------------------
files = sorted((DATA / "notices").glob("*.csv"))
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

print(f"Loaded {len(df)} notices")

# ---------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------
def clean_text(text):
    text = str(text).lower()

    # Remove common portal boilerplate
    boilerplate = [
        "national procurement aggregation service",
        "state procurement cell",
    ]

    for phrase in boilerplate:
        text = text.replace(phrase, " ")

    # Normalize reference numbers
    text = re.sub(
        r'\b(?:tender|nit|ref(?:erence)?|bid)[\s:/-]*[a-z0-9/-]+\b',
        ' ',
        text
    )

    # Normalize dates
    text = re.sub(
        r'\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b',
        ' DATE ',
        text
    )

    # Normalize money/value formats
    text = re.sub(
        r'(?:rs\.?|inr|₹)\s*[\d,]+(?:\.\d+)?',
        ' MONEY ',
        text
    )

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def shingles(text, n=3):
    words = clean_text(text).split()
    return {
        " ".join(words[i:i+n])
        for i in range(len(words) - n + 1)
    }


# ---------------------------------------------------------
# Build lookup
# ---------------------------------------------------------
notice_text = {}

for _, row in df.iterrows():
    notice_text[row["notice_id"]] = shingles(
        f'{row.get("title", "")} {row.get("body", "")}'
    )

# ---------------------------------------------------------
# Load labelled pairs
# ---------------------------------------------------------
pairs = pd.read_csv(DATA / "labelled_pairs.csv")

scores = []

for _, row in pairs.iterrows():
    a = notice_text[row["notice_id_a"]]
    b = notice_text[row["notice_id_b"]]

    union = len(a | b)

    if union == 0:
        score = 0.0
    else:
        score = len(a & b) / union

    scores.append(score)

pairs["similarity"] = scores

# ---------------------------------------------------------
# Test thresholds
# ---------------------------------------------------------
print("\n" + "=" * 70)
print("THRESHOLD ANALYSIS")
print("=" * 70)

print("\nSimilarity by label:")

for label in ["same", "different"]:
    s = pairs.loc[pairs["label"] == label, "similarity"]

    print(
        f"{label:10s} "
        f"count={len(s):3d} "
        f"median={s.median():.4f} "
        f"mean={s.mean():.4f} "
        f"min={s.min():.4f} "
        f"max={s.max():.4f}"
    )

# ---------------------------------------------------------
# Cost analysis
# C_FP = 20
# C_FN = 1
# ---------------------------------------------------------
C_FP = 20
C_FN = 1

print("\n" + "=" * 70)
print("COST ANALYSIS")
print("=" * 70)

print(f"\nC_FP = {C_FP}")
print(f"C_FN = {C_FN}")
print("\nThreshold means: similarity >= threshold => MERGE")

results = []

for threshold in [x / 100 for x in range(50, 96, 2)]:

    predicted_merge = pairs["similarity"] >= threshold

    fp = (
        predicted_merge &
        (pairs["label"] == "different")
    ).sum()

    fn = (
        (~predicted_merge) &
        (pairs["label"] == "same")
    ).sum()

    tp = (
        predicted_merge &
        (pairs["label"] == "same")
    ).sum()

    tn = (
        (~predicted_merge) &
        (pairs["label"] == "different")
    ).sum()

    cost = C_FP * fp + C_FN * fn

    results.append({
        "threshold": threshold,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "cost": cost,
    })

result_df = pd.DataFrame(results)

print(
    result_df.to_string(
        index=False,
        formatters={
            "threshold": "{:.2f}".format
        }
    )
)

# ---------------------------------------------------------
# Best empirical threshold
# ---------------------------------------------------------
best = result_df.loc[result_df["cost"].idxmin()]

print("\n" + "=" * 70)
print("LOWEST EMPIRICAL COST")
print("=" * 70)

print(f"Threshold: {best['threshold']:.2f}")
print(f"TP:        {int(best['TP'])}")
print(f"FP:        {int(best['FP'])}")
print(f"FN:        {int(best['FN'])}")
print(f"TN:        {int(best['TN'])}")
print(f"Cost:      {int(best['cost'])}")

result_df.to_csv(
    "../results/threshold_analysis.csv",
    index=False
)

print("\nSaved: ../results/threshold_analysis.csv")