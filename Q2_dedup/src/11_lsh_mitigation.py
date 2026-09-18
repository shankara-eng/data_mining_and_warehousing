from pathlib import Path
import re
import unicodedata
import hashlib
import time

import pandas as pd
import numpy as np


# =========================================================
# CONFIGURATION
# =========================================================

DATA = Path("../data")
RESULTS = Path("../results")

K = 256
BANDS = 32
ROWS = 8

FREQUENCY_CUTOFF = 0.05

TOTAL_START = time.perf_counter()


# =========================================================
# TEXT CLEANING
# =========================================================

def clean_text(text):
    s = unicodedata.normalize("NFKC", str(text)).lower()

    s = re.sub(
        r"national procurement aggregation service|state procurement cell",
        " ",
        s,
    )

    s = re.sub(r"corrigendum", " ", s)

    s = re.sub(
        r"\b(?:tender|nit|ref(?:erence)?)[\s:/-]*[a-z0-9./_-]*\b",
        " ",
        s,
    )

    s = re.sub(
        r"\b\d{1,4}[/-]\d{1,2}[/-]\d{2,4}\b",
        " ",
        s,
    )

    s = re.sub(
        r"\b(?:rs|inr|rupees?)\s*[\d,.-]+"
        r"(?:\s*(?:lakh|crore|cr))?\b",
        " ",
        s,
    )

    s = re.sub(
        r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
        " ",
        s,
    )

    return re.sub(r"\s+", " ", s).strip()


def shingles(text):
    tokens = re.findall(
        r"\b\w+\b",
        clean_text(text)
    )

    return {
        " ".join(tokens[i:i + 3])
        for i in range(len(tokens) - 2)
    }


# =========================================================
# HASH FUNCTION
# =========================================================

def hash64(shingle, seed):
    return int.from_bytes(
        hashlib.blake2b(
            f"{seed}|{shingle}".encode(),
            digest_size=8
        ).digest(),
        "little",
    )


# =========================================================
# LOAD CORPUS
# =========================================================

stage_start = time.perf_counter()

files = sorted(
    (DATA / "notices").glob("*.csv")
)

notices = pd.concat(
    [pd.read_csv(f) for f in files],
    ignore_index=True
).fillna("")

print(f"Loaded {len(notices)} notices")

corpus_time = time.perf_counter() - stage_start

print(
    f"Corpus loading time: "
    f"{corpus_time:.3f} seconds"
)


# =========================================================
# BUILD SHINGLE SETS
# =========================================================

stage_start = time.perf_counter()

print("Building shingle sets...")

shingle_sets = {}

for row in notices.itertuples(index=False):

    text = f"{row.title} {row.body}"

    shingle_sets[row.notice_id] = shingles(text)

print("Shingle sets built.")

shingle_time = time.perf_counter() - stage_start

print(
    f"Shingle construction time: "
    f"{shingle_time:.3f} seconds"
)


# =========================================================
# SHINGLE DOCUMENT FREQUENCY
# =========================================================

stage_start = time.perf_counter()

print("Calculating shingle document frequencies...")

df = {}

for shs in shingle_sets.values():

    for shingle in shs:

        df[shingle] = df.get(shingle, 0) + 1


cutoff = int(
    len(notices) * FREQUENCY_CUTOFF
)

common_shingles = {
    shingle
    for shingle, count in df.items()
    if count > cutoff
}

print(
    f"Unique shingles: {len(df)}"
)

print(
    f"Frequency cutoff: >{cutoff} notices"
)

print(
    f"High-frequency shingles removed: "
    f"{len(common_shingles)}"
)

df_time = time.perf_counter() - stage_start

print(
    f"Document-frequency calculation time: "
    f"{df_time:.3f} seconds"
)


# =========================================================
# FILTER SHINGLE SETS
# =========================================================

stage_start = time.perf_counter()

print("Filtering high-frequency shingles...")

filtered_sets = {}

removed_counts = []

for notice_id, shs in shingle_sets.items():

    filtered = shs - common_shingles

    filtered_sets[notice_id] = filtered

    removed_counts.append(
        len(shs) - len(filtered)
    )

print(
    f"Average shingles removed/notice: "
    f"{np.mean(removed_counts):.1f}"
)

filter_time = time.perf_counter() - stage_start

print(
    f"Filtering time: "
    f"{filter_time:.3f} seconds"
)


# =========================================================
# BUILD MINHASH SIGNATURES
# =========================================================

stage_start = time.perf_counter()

print(
    f"Building {K}-hash signatures "
    "on filtered shingles..."
)

signatures = {}

for count, (notice_id, shs) in enumerate(
    filtered_sets.items(),
    start=1
):

    if not shs:

        signature = np.full(
            K,
            np.iinfo(np.uint64).max,
            dtype=np.uint64
        )

    else:

        signature = np.array(
            [
                min(
                    hash64(s, seed)
                    for s in shs
                )
                for seed in range(K)
            ],
            dtype=np.uint64
        )

    signatures[notice_id] = signature

    if count % 1000 == 0:

        print(
            f"  signatures: "
            f"{count}/{len(filtered_sets)}"
        )

minhash_time = time.perf_counter() - stage_start

print(
    f"Filtered MinHash construction time: "
    f"{minhash_time:.3f} seconds"
)


# =========================================================
# BUILD LSH BUCKETS
# =========================================================

stage_start = time.perf_counter()

print("Building LSH buckets...")

buckets = {}

for notice_id, signature in signatures.items():

    for band in range(BANDS):

        start = band * ROWS
        end = start + ROWS

        bucket_hash = hashlib.blake2b(
            signature[start:end].tobytes(),
            digest_size=12
        ).hexdigest()

        key = (band, bucket_hash)

        if key not in buckets:
            buckets[key] = []

        buckets[key].append(notice_id)

print(
    f"LSH buckets: "
    f"{len(buckets)}"
)

lsh_time = time.perf_counter() - stage_start

print(
    f"LSH bucket construction time: "
    f"{lsh_time:.3f} seconds"
)


# =========================================================
# GENERATE CANDIDATE SETS
# =========================================================

stage_start = time.perf_counter()

print("Generating candidate sets...")

candidate_sets = {}

for count, (notice_id, signature) in enumerate(
    signatures.items(),
    start=1
):

    candidates = set()

    for band in range(BANDS):

        start = band * ROWS
        end = start + ROWS

        bucket_hash = hashlib.blake2b(
            signature[start:end].tobytes(),
            digest_size=12
        ).hexdigest()

        candidates.update(
            buckets[
                (band, bucket_hash)
            ]
        )

    candidates.discard(notice_id)

    candidate_sets[notice_id] = candidates

    if count % 1000 == 0:

        print(
            f"  candidates: "
            f"{count}/{len(signatures)}"
        )

candidate_time = time.perf_counter() - stage_start

print(
    f"Candidate generation time: "
    f"{candidate_time:.3f} seconds"
)


# =========================================================
# EVALUATE LABELLED PAIRS
# =========================================================

stage_start = time.perf_counter()

pairs = pd.read_csv(
    DATA / "labelled_pairs.csv"
).fillna("")

survived = 0
true_survived = 0
true_total = 0

for pair in pairs.itertuples(index=False):

    a = pair.notice_id_a
    b = pair.notice_id_b

    survives = (
        b in candidate_sets.get(a, set())
        or
        a in candidate_sets.get(b, set())
    )

    survived += int(survives)

    if pair.label == "same":

        true_total += 1
        true_survived += int(survives)

evaluation_time = time.perf_counter() - stage_start


# =========================================================
# CANDIDATE DISTRIBUTION
# =========================================================

sizes = np.array([
    len(x)
    for x in candidate_sets.values()
])


# =========================================================
# RESULTS
# =========================================================

print()
print("=" * 60)
print("MITIGATION RESULTS")
print("=" * 60)

print(
    f"Candidate survival: "
    f"{survived / len(pairs):.4f}"
)

print(
    "TRUE-DUPLICATE candidate survival: "
    f"{true_survived / true_total:.4f}"
)

print(
    f"Median candidates/notice: "
    f"{np.median(sizes):.0f}"
)

print(
    f"P95 candidates/notice: "
    f"{np.quantile(sizes, .95):.0f}"
)

print(
    f"P99 candidates/notice: "
    f"{np.quantile(sizes, .99):.0f}"
)

print(
    f"Maximum candidates/notice: "
    f"{sizes.max():.0f}"
)


# =========================================================
# SAVE DISTRIBUTION
# =========================================================

distribution = pd.DataFrame({
    "notice_id": list(candidate_sets.keys()),
    "candidate_count": sizes,
})

distribution = distribution.merge(
    notices[
        ["notice_id", "portal_id"]
    ],
    on="notice_id",
)

RESULTS.mkdir(
    parents=True,
    exist_ok=True
)

output = (
    RESULTS /
    "candidate_distribution_mitigated.csv"
)

distribution.to_csv(
    output,
    index=False
)

print()
print(f"Saved: {output}")


# =========================================================
# RUNTIME SUMMARY
# =========================================================

total_time = (
    time.perf_counter()
    - TOTAL_START
)

print()
print("=" * 60)
print("MITIGATION RUNTIME SUMMARY")
print("=" * 60)

print(
    f"Corpus loading:              "
    f"{corpus_time:.3f} seconds"
)

print(
    f"Shingle construction:        "
    f"{shingle_time:.3f} seconds"
)

print(
    f"Document-frequency analysis: "
    f"{df_time:.3f} seconds"
)

print(
    f"Shingle filtering:           "
    f"{filter_time:.3f} seconds"
)

print(
    f"Filtered MinHash:            "
    f"{minhash_time:.3f} seconds"
)

print(
    f"LSH bucket construction:     "
    f"{lsh_time:.3f} seconds"
)

print(
    f"Candidate generation:        "
    f"{candidate_time:.3f} seconds"
)

print(
    f"Label evaluation:            "
    f"{evaluation_time:.3f} seconds"
)

print(
    f"TOTAL MITIGATION TIME:       "
    f"{total_time:.3f} seconds"
)

print(
    f"TOTAL MITIGATION TIME:       "
    f"{total_time / 60:.2f} minutes"
)

print("=" * 60)