from pathlib import Path
import numpy as np
import psycopg2

RESULTS = Path("../results")

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "annapurna",
    "user": "annapurna",
    "password": "annapurna",
}

print("Loading saved MinHash signatures...")

data = np.load(
    RESULTS / "minhash_signatures_256.npz",
    allow_pickle=True
)

notice_ids = data.files

print(f"Found {len(notice_ids)} signatures")

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

count = 0

for notice_id in notice_ids:

    signature = data[notice_id]

    cur.execute(
        """
        INSERT INTO minhash_signatures
            (notice_id, signature)
        VALUES
            (%s, %s)
        ON CONFLICT (notice_id)
        DO UPDATE SET
            signature = EXCLUDED.signature
        """,
        (
            notice_id,
            [int(x) for x in signature]
        )
    )

    count += 1

    if count % 1000 == 0:
        conn.commit()
        print(f"Loaded {count}/{len(notice_ids)}")

conn.commit()

cur.close()
conn.close()

print("\nDone.")
print(f"Inserted/updated: {count}")