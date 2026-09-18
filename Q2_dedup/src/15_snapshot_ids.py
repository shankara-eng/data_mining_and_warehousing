import pandas as pd
import psycopg2

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "annapurna",
    "user": "annapurna",
    "password": "annapurna",
}

conn = psycopg2.connect(**DB_CONFIG)

df = pd.read_sql(
    """
    SELECT notice_id, opportunity_id
    FROM opportunity_members
    ORDER BY notice_id
    """,
    conn
)

conn.close()

df.to_csv(
    "../results/opportunity_ids_before_rerun.csv",
    index=False
)

print(f"Saved {len(df)} notice → opportunity mappings.")
print(f"Unique opportunities: {df['opportunity_id'].nunique()}")
print("Saved: ../results/opportunity_ids_before_rerun.csv")
