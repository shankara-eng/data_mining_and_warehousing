from pathlib import Path
from collections import defaultdict
import hashlib
import uuid
import re

import numpy as np
import pandas as pd
import psycopg2


DATA = Path("../data")
RESULTS = Path("../results")

JACCARD_THRESHOLD = 0.56

BANDS = 32
ROWS = 8

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "annapurna",
    "user": "annapurna",
    "password": "annapurna",
}


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def clean_text(text):

    text = str(text).lower()

    boilerplate = [
        "national procurement aggregation service",
        "state procurement cell",
    ]

    for phrase in boilerplate:
        text = text.replace(phrase, " ")

    text = re.sub(
        r'\b(?:tender|nit|ref(?:erence)?|bid)[\s:/-]*[a-z0-9/-]+\b',
        ' ',
        text
    )

    text = re.sub(
        r'\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b',
        ' DATE ',
        text
    )

    text = re.sub(
        r'(?:rs\.?|inr|â‚¹)\s*[\d,]+(?:\.\d+)?',
        ' MONEY ',
        text
    )

    text = re.sub(r'\s+', ' ', text).strip()

    return text


def make_shingles(text, n=3):

    words = clean_text(text).split()

    return {
        " ".join(words[i:i+n])
        for i in range(len(words) - n + 1)
    }


def jaccard(a, b):

    union = a | b

    if not union:
        return 0.0

    return len(a & b) / len(union)


# =========================================================
# LOAD NOTICES
# =========================================================

print("Loading notices...")

files = sorted((DATA / "notices").glob("*.csv"))

df = pd.concat(
    [pd.read_csv(f) for f in files],
    ignore_index=True
)

print(f"Loaded {len(df)} notices")


# =========================================================
# BUILD SHINGLES
# =========================================================

print("Building shingle sets...")

shingles = {}

for _, row in df.iterrows():

    notice_id = row["notice_id"]

    text = (
        str(row.get("title", "")) +
        " " +
        str(row.get("body", ""))
    )

    shingles[notice_id] = make_shingles(text)

print("Shingle sets ready.")


# =========================================================
# LOAD SAVED MINHASH SIGNATURES
# =========================================================

print("Loading saved MinHash signatures...")

npz = np.load(
    RESULTS / "minhash_signatures_256.npz",
    allow_pickle=True
)

signatures = {
    notice_id: npz[notice_id]
    for notice_id in npz.files
}

print(f"Loaded {len(signatures)} signatures")


# =========================================================
# BUILD LSH LOOKUP IN MEMORY
# =========================================================

print("Building LSH lookup...")

buckets = defaultdict(set)

for notice_id, signature in signatures.items():

    for band in range(BANDS):

        start = band * ROWS
        end = start + ROWS

        band_bytes = signature[start:end].tobytes()

        bucket_hash = hashlib.blake2b(
            band_bytes,
            digest_size=12
        ).hexdigest()

        buckets[
            (band, bucket_hash)
        ].add(notice_id)

print(f"LSH buckets: {len(buckets)}")


# =========================================================
# CONNECT TO DATABASE
# =========================================================

print("Connecting to PostgreSQL...")

conn = psycopg2.connect(**DB_CONFIG)

cur = conn.cursor()

print("Connected.")


# =========================================================
# LOAD EXISTING ASSIGNMENTS
# =========================================================

notice_to_opportunity = {}

cur.execute(
    """
    SELECT notice_id, opportunity_id
    FROM opportunity_members
    """
)

existing_rows = cur.fetchall()

for notice_id, opportunity_id in existing_rows:

    if notice_id in notice_to_opportunity:
        raise RuntimeError(
            f"Notice {notice_id} already belongs to multiple "
            f"opportunities."
        )

    notice_to_opportunity[notice_id] = opportunity_id

print(
    f"Existing notice assignments: "
    f"{len(notice_to_opportunity)}"
)


# =========================================================
# PROCESS NOTICES
# =========================================================

print("\nAssigning opportunity IDs...")

created = 0
matched = 0
existing = 0
total_candidates = 0


for count, notice_id in enumerate(
    df["notice_id"],
    start=1
):

    # -----------------------------------------------------
    # EXISTING NOTICE
    # -----------------------------------------------------
    # The existing opportunity ID is authoritative.
    # Never reassign an existing notice.
    # -----------------------------------------------------

    existing_opportunity = notice_to_opportunity.get(
        notice_id
    )

    if existing_opportunity is not None:

        existing += 1

        cur.execute(
            """
            UPDATE opportunity_members
            SET last_seen_at = CURRENT_TIMESTAMP
            WHERE opportunity_id = %s
              AND notice_id = %s
            """,
            (
                existing_opportunity,
                notice_id
            )
        )

        if count % 500 == 0:

            conn.commit()

            print(
                f"Processed {count}/{len(df)} "
                f"| existing={existing} "
                f"| matched_new={matched} "
                f"| created_new={created}"
            )

        continue


    # -----------------------------------------------------
    # NEW NOTICE
    # -----------------------------------------------------

    signature = signatures[notice_id]

    candidates = set()

    # -----------------------------------------------------
    # LSH CANDIDATE RETRIEVAL
    # -----------------------------------------------------

    for band in range(BANDS):

        start = band * ROWS
        end = start + ROWS

        band_bytes = signature[start:end].tobytes()

        bucket_hash = hashlib.blake2b(
            band_bytes,
            digest_size=12
        ).hexdigest()

        candidates.update(
            buckets.get(
                (band, bucket_hash),
                set()
            )
        )

    candidates.discard(notice_id)

    total_candidates += len(candidates)


    # -----------------------------------------------------
    # EXACT VERIFICATION
    # -----------------------------------------------------

    current_shingles = shingles[notice_id]

    best_opportunity = None
    best_similarity = 0.0

    for candidate_id in candidates:

        candidate_shingles = shingles[candidate_id]

        similarity = jaccard(
            current_shingles,
            candidate_shingles
        )

        if similarity < JACCARD_THRESHOLD:
            continue

        candidate_opportunity = (
            notice_to_opportunity.get(candidate_id)
        )

        if candidate_opportunity is not None:

            if similarity > best_similarity:

                best_similarity = similarity
                best_opportunity = candidate_opportunity


    # -----------------------------------------------------
    # ASSIGN / CREATE OPPORTUNITY
    # -----------------------------------------------------

    if best_opportunity is not None:

        opportunity_id = best_opportunity

        matched += 1

    else:

        opportunity_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO opportunities
                (opportunity_id, canonical_notice_id)
            VALUES
                (%s, %s)
            """,
            (
                opportunity_id,
                notice_id
            )
        )

        created += 1


    # -----------------------------------------------------
    # STORE IN-MEMORY ASSIGNMENT
    # -----------------------------------------------------

    notice_to_opportunity[notice_id] = opportunity_id


    # -----------------------------------------------------
    # STORE MEMBERSHIP
    # -----------------------------------------------------

    cur.execute(
        """
        INSERT INTO opportunity_members
            (opportunity_id, notice_id)
        VALUES
            (%s, %s)
        ON CONFLICT (opportunity_id, notice_id)
        DO UPDATE SET
            last_seen_at = CURRENT_TIMESTAMP
        """,
        (
            opportunity_id,
            notice_id
        )
    )


    # -----------------------------------------------------
    # PROGRESS
    # -----------------------------------------------------

    if count % 500 == 0:

        conn.commit()

        print(
            f"Processed {count}/{len(df)} "
            f"| existing={existing} "
            f"| matched_new={matched} "
            f"| created_new={created}"
        )


# =========================================================
# FINAL COMMIT
# =========================================================

conn.commit()

cur.close()
conn.close()


# =========================================================
# SUMMARY
# =========================================================

print("\n" + "=" * 60)
print("OPPORTUNITY ASSIGNMENT COMPLETE")
print("=" * 60)

print(f"Notices processed:       {len(df)}")
print(f"Existing assignments:    {existing}")
print(f"New notices matched:     {matched}")
print(f"New opportunities:       {created}")
print(f"Jaccard threshold:       {JACCARD_THRESHOLD}")
print(
    f"Average candidates:      "
    f"{total_candidates / len(df):.2f}"
)