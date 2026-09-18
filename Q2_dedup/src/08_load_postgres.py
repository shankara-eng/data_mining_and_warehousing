from pathlib import Path
import pandas as pd
import psycopg2

DATA = Path("data")
NOTICE_DIR = DATA / "notices"

DB = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "annapurna",
    "user": "annapurna",
    "password": "annapurna",
}

files = sorted(NOTICE_DIR.glob("*.csv"))

notices = pd.concat(
    [pd.read_csv(f) for f in files],
    ignore_index=True
).fillna("")

print(f"Loaded {len(notices)} notices")

conn = psycopg2.connect(**DB)
cur = conn.cursor()

rows = [
    (
        str(r.notice_id),
        str(r.portal_id),
        str(r.published_at) if r.published_at else None,
        str(r.title),
        str(r.body),
        float(r.estimated_value)
        if str(r.estimated_value).strip()
        else None,
        str(r.closing_date)
        if str(r.closing_date).strip()
        else None,
        ""
    )
    for r in notices.itertuples(index=False)
]

cur.executemany(
    """
    INSERT INTO notices
    (
        notice_id,
        portal_id,
        published_at,
        title,
        body,
        estimated_value,
        closing_date,
        normalized_text
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (notice_id) DO NOTHING
    """,
    rows
)

conn.commit()

cur.execute("SELECT COUNT(*) FROM notices")
count = cur.fetchone()[0]

print(f"PostgreSQL notices: {count}")

cur.close()
conn.close()