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


# =========================================================
# LOAD SNAPSHOT
# =========================================================

snapshot = pd.read_csv(
    RESULTS / "opportunity_ids_before_rerun.csv"
)

print(f"Snapshot mappings: {len(snapshot)}")
print(
    f"Snapshot opportunities: "
    f"{snapshot['opportunity_id'].nunique()}"
)


# =========================================================
# CONNECT
# =========================================================

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()


# =========================================================
# CLEAR ONLY OPPORTUNITY ASSIGNMENTS
# =========================================================

print("Clearing current opportunity assignments...")

cur.execute(
    "TRUNCATE opportunity_members, opportunities CASCADE"
)

conn.commit()


# =========================================================
# RESTORE OPPORTUNITIES
# =========================================================

print("Restoring opportunity records...")

opportunities = (
    snapshot[
        ["opportunity_id", "notice_id"]
    ]
    .drop_duplicates("opportunity_id")
)

for _, row in opportunities.iterrows():

    cur.execute(
        """
        INSERT INTO opportunities
            (opportunity_id, canonical_notice_id)
        VALUES
            (%s, %s)
        """,
        (
            row["opportunity_id"],
            row["notice_id"],
        )
    )


# =========================================================
# RESTORE MEMBERSHIPS
# =========================================================

print("Restoring notice memberships...")

for _, row in snapshot.iterrows():

    cur.execute(
        """
        INSERT INTO opportunity_members
            (opportunity_id, notice_id)
        VALUES
            (%s, %s)
        """,
        (
            row["opportunity_id"],
            row["notice_id"],
        )
    )


conn.commit()

cur.close()
conn.close()


# =========================================================
# VERIFY
# =========================================================

print("\n" + "=" * 60)
print("RESTORE COMPLETE")
print("=" * 60)

print(f"Restored mappings:       {len(snapshot)}")
print(
    f"Restored opportunities:  "
    f"{snapshot['opportunity_id'].nunique()}"
)