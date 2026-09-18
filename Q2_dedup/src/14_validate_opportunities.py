from pathlib import Path

import pandas as pd
import psycopg2


DATA = Path("../data")

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "annapurna",
    "user": "annapurna",
    "password": "annapurna",
}


# =========================================================
# CONNECT
# =========================================================

print("Connecting to PostgreSQL...")

conn = psycopg2.connect(**DB_CONFIG)

print("Connected.")


# =========================================================
# LOAD OPPORTUNITY ASSIGNMENTS
# =========================================================

assignments = pd.read_sql(
    """
    SELECT notice_id, opportunity_id
    FROM opportunity_members
    """,
    conn
)

print(f"Loaded {len(assignments)} opportunity assignments")


# =========================================================
# BASIC COUNTS
# =========================================================

unique_opportunities = assignments["opportunity_id"].nunique()

print("\n" + "=" * 60)
print("OPPORTUNITY COUNTS")
print("=" * 60)

print(f"Notice assignments:       {len(assignments)}")
print(f"Unique opportunities:     {unique_opportunities}")


# =========================================================
# LOAD LABELLED PAIRS
# =========================================================

pairs = pd.read_csv(
    DATA / "labelled_pairs.csv"
)

lookup = dict(
    zip(
        assignments["notice_id"],
        assignments["opportunity_id"]
    )
)


# =========================================================
# VALIDATE LABELLED PAIRS
# =========================================================

same_correct = 0
same_missed = 0

different_correct = 0
different_merged = 0

for _, row in pairs.iterrows():

    a = row["notice_id_a"]
    b = row["notice_id_b"]

    opp_a = lookup.get(a)
    opp_b = lookup.get(b)

    if opp_a is None or opp_b is None:
        continue

    same_opportunity = opp_a == opp_b

    if row["label"] == "same":

        if same_opportunity:
            same_correct += 1
        else:
            same_missed += 1

    else:

        if same_opportunity:
            different_merged += 1
        else:
            different_correct += 1


# =========================================================
# RESULTS
# =========================================================

print("\n" + "=" * 60)
print("LABELLED-PAIR VALIDATION")
print("=" * 60)

print("\nSAME pairs:")
print(f"Correctly merged:        {same_correct}")
print(f"Missed merges:           {same_missed}")

print("\nDIFFERENT pairs:")
print(f"Correctly separated:     {different_correct}")
print(f"Incorrectly merged:      {different_merged}")


total_same = same_correct + same_missed
total_different = different_correct + different_merged

if total_same:
    same_recall = same_correct / total_same
else:
    same_recall = 0

if total_different:
    different_specificity = different_correct / total_different
else:
    different_specificity = 0


print("\n" + "=" * 60)
print("QUALITY METRICS")
print("=" * 60)

print(f"Same-pair merge recall:       {same_recall:.4f}")
print(f"Different-pair separation:    {different_specificity:.4f}")


# =========================================================
# COST
# =========================================================

C_FP = 20
C_FN = 1

cost = (
    different_merged * C_FP
    + same_missed * C_FN
)

print("\n" + "=" * 60)
print("ASYMMETRIC COST")
print("=" * 60)

print(f"False merge cost:          {C_FP}")
print(f"False non-merge cost:      {C_FN}")
print(f"Observed validation cost:  {cost}")


# =========================================================
# SAVE RESULTS
# =========================================================

result = pd.DataFrame([{
    "unique_opportunities": unique_opportunities,
    "same_correct": same_correct,
    "same_missed": same_missed,
    "different_correct": different_correct,
    "different_merged": different_merged,
    "same_pair_recall": same_recall,
    "different_pair_separation": different_specificity,
    "false_merge_cost": C_FP,
    "false_nonmerge_cost": C_FN,
    "validation_cost": cost,
}])

result.to_csv(
    "../results/opportunity_validation.csv",
    index=False
)

conn.close()

print("\nSaved: ../results/opportunity_validation.csv")