from pathlib import Path
import hashlib
import numpy as np
import psycopg2

RESULTS = Path("results")

K = 256
BANDS = 32
ROWS = 8

SIGNATURE_CACHE = RESULTS / "minhash_signatures_256.npz"

DB = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "annapurna",
    "user": "annapurna",
    "password": "annapurna",
}


print("Loading cached MinHash signatures...")

cached = np.load(
    SIGNATURE_CACHE,
    allow_pickle=False
)

print(f"Loaded {len(cached.files)} signatures")


print("Building LSH rows...")

rows = []

for notice_id in cached.files:

    signature = cached[notice_id]

    for band in range(BANDS):

        start = band * ROWS
        end = start + ROWS

        bucket_hash = hashlib.blake2b(
            signature[start:end].tobytes(),
            digest_size=12
        ).hexdigest()

        rows.append(
            (
                band,
                bucket_hash,
                notice_id
            )
        )

print(f"LSH rows to insert: {len(rows)}")


print("Connecting to PostgreSQL...")

conn = psycopg2.connect(**DB)
cur = conn.cursor()


print("Clearing existing LSH rows...")

cur.execute(
    "TRUNCATE TABLE lsh_buckets"
)

conn.commit()


print("Inserting LSH rows...")

cur.executemany(
    """
    INSERT INTO lsh_buckets
    (
        band,
        bucket_hash,
        notice_id
    )
    VALUES (%s, %s, %s)
    ON CONFLICT DO NOTHING
    """,
    rows
)

conn.commit()


cur.execute(
    "SELECT COUNT(*) FROM lsh_buckets"
)

count = cur.fetchone()[0]

print()
print(f"PostgreSQL LSH rows: {count}")

cur.close()
conn.close()