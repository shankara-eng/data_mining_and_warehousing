from pathlib import Path
import pandas as pd
import psycopg2

RESULTS = Path("../results")

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "annapurna",
    "user": "annapurna",
    "password": "annapurna",
}

before = pd.read_csv(
    RESULTS / "opportunity_ids_before_rerun.csv"
)

conn = psycopg2.connect(**DB_CONFIG)

after = pd.read_sql(
    """
    SELECT notice_id, opportunity_id
    FROM opportunity_members
    """,
    conn
)

conn.close()

merged = before.merge(
    after,
    on="notice_id",
    suffixes=("_before", "_after")
)

same_id = (
    merged["opportunity_id_before"]
    == merged["opportunity_id_after"]
)

changed = merged[~same_id]

print("\n" + "=" * 60)
print("STABLE ID VALIDATION")
print("=" * 60)

print(f"Notices compared:       {len(merged)}")
print(f"IDs unchanged:          {same_id.sum()}")
print(f"IDs changed:            {len(changed)}")

print(
    f"ID stability:           "
    f"{same_id.mean():.4f}"
)

print("\nUnique opportunities:")
print(
    f"Before rerun:           "
    f"{before['opportunity_id'].nunique()}"
)

print(
    f"After rerun:            "
    f"{after['opportunity_id'].nunique()}"
)

if len(changed) > 0:

    print("\nFirst changed mappings:")
    print(
        changed.head(20).to_string(index=False)
    )

changed.to_csv(
    RESULTS / "changed_opportunity_ids.csv",
    index=False
)

print("\nSaved: ../results/changed_opportunity_ids.csv")