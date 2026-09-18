# Q2 — Twelve Thousand Tenders, Wearing Disguise

## Deduplicating Public Procurement Notices into Stable Opportunity Cards

**Dataset:** 12,000 notices from 260 portals  
**Nightly budget:** 20 minutes  
**Similarity:** Jaccard over cleaned word 3-shingles  
**Estimator:** 256-value MinHash  
**Retrieval:** 32 LSH bands × 8 rows  
**Final merge threshold:** exact Jaccard ≥ 0.56  
**Asymmetric cost policy:** false merge = 20, missed merge = 1

---

## 1. Executive Summary

The problem is to collapse many portal notices that represent the same underlying procurement opportunity into stable opportunity cards. A notice ID is portal-specific; the same tender may be republished by another portal with a different reference number, different formatting, additional boilerplate, or a corrigendum.

The implemented architecture is:

```text
Raw notices
    ↓
Canonicalization / noise removal
    ↓
Word 3-shingle sets
    ↓
256-value MinHash signatures
    ↓
32 × 8 LSH candidate retrieval
    ↓
Exact Jaccard verification
    ↓
Opportunity assignment
    ↓
Persistent UUID opportunity IDs
    ↓
PostgreSQL
```

The system separates **retrieval** from the **final merge decision**. MinHash and LSH reduce the number of pairs requiring exact comparison; exact cleaned 3-shingle Jaccard makes the final decision. This is important because a false merge is much more costly than a missed merge.

Key measured results:

- 12,000 notices processed.
- 71,994,000 possible unordered pairs avoided by candidate retrieval.
- 256 MinHash values per notice.
- 32 bands × 8 rows.
- Exact merge threshold = 0.56.
- False-merge cost = 20; false-non-merge cost = 1.
- Baseline full run = 92.14 min.
- High-frequency-shingle mitigation = 20.18 min.
- Mitigated candidate survival for true duplicates = 69.53%.
- Final labelled-pair validation: 153/279 SAME correctly merged; 620/621 DIFFERENT correctly separated.
- Stable-ID rerun: 12,000/12,000 IDs unchanged; 100% stability.

The supplied truth metadata contains 5,776 underlying opportunities; the implemented clustering produced 6,747. This discrepancy is explicitly reported as a limitation rather than hidden.

---

# 2. Dataset and Problem Context

The supplied truth metadata reports:

| Quantity | Value |
|---|---:|
| Notices | 12,000 |
| Portals | 260 |
| Ground-truth opportunities | 5,776 |
| True duplicate pairs | 15,049 |
| Possible unordered pairs | 71,994,000 |
| Labelled pairs | 900 |
| Labelled SAME | 279 |
| Labelled DIFFERENT | 621 |
| Corpus duplicate-pair base rate | 0.0002090313 |
| Labelled-pair SAME rate | 0.31 |

The labelled sample is therefore not representative of the full pair base rate; it is an evaluation set containing 31% SAME pairs.

Truth cluster sizes:

| Size | Opportunities |
|---:|---:|
| 1 | 3,350 |
| 2 | 901 |
| 3 | 604 |
| 4 | 321 |
| 5 | 247 |
| 6 | 139 |
| 7 | 95 |
| 8 | 53 |
| 9 | 66 |

The dataset analysis script is `src/01_dataset_analysis.py`. Its observed output included:

```text
Files: 8
Notices: 12000
Pairs: 900
different    621
same         279
Expected notices: 12000
Opportunities: 5776
True duplicate pairs: 15049
Possible pairs: 71994000
Corpus duplicate rate: 0.00020903130816456926
```

---

# 3. Why Simple Exact Matching Does Not Work

The portal profile documents several sources of disguise:

- P001/P002/P005 add approximately 1,400 characters of repeated `NATIONAL PROCUREMENT AGGREGATION SERVICE` boilerplate.
- P003/P004/P006 use a repeated `STATE PROCUREMENT CELL` block.
- P001/P002/P005 append disclaimer footers.
- Portals invent unrelated reference numbers for the same tender.
- Dates appear in many formats.
- Monetary values appear as rupees, lakh, crore, comma-separated values, etc.
- Some portals use uppercase.
- At least two portals truncate long notices.
- Corrigenda are new notices and may repeat the original tender plus a correction section and a new closing date.
- Nodal portals can republish notices days or weeks after the original.

Therefore, portal references and raw text cannot be treated as stable opportunity identifiers.

---

# 4. Complete Project Architecture

## 4.1 Ingestion

All CSV notice files under `data/notices/` are concatenated. Each notice contains fields such as:

```text
notice_id
portal_id
published_at
title
body
estimated_value
closing_date
```

## 4.2 Canonicalization

The implementation lowercases text and removes known portal scaffolding. It also normalizes reference-number patterns, dates and money expressions.

The intent is to remove **portal noise**, not tender semantics. Work descriptions, location, procuring entity, scope and other substantive terms remain available to the similarity representation.

## 4.3 Feature representation

The cleaned text is tokenized into word 3-shingles. A shingle is a consecutive sequence of three words.

## 4.4 Exact similarity

The final verification metric is Jaccard similarity:

\[
J(A,B)=\frac{|A\cap B|}{|A\cup B|}
\]

## 4.5 MinHash

Each shingle set is compressed into 256 MinHash values. Equal MinHash positions estimate Jaccard similarity.

## 4.6 LSH

The 256-value signature is divided into 32 bands of 8 rows. Each band is hashed into a bucket. Notices sharing a bucket become candidates.

## 4.7 Exact verification

Each candidate is compared with exact Jaccard over the cleaned 3-shingle sets. A similarity of at least 0.56 is required for merging.

## 4.8 Persistence

PostgreSQL stores notice data, signatures, LSH buckets, opportunities and opportunity memberships. Opportunity IDs are UUIDs and are kept stable across reruns.

---

# 5. A(a) — Mechanical Similarity Representation

## 5.1 Alternatives tested

Three representations were compared:

1. raw words
2. cleaned words
3. cleaned word 3-shingles

Measured labelled-pair results:

| Representation | SAME median | SAME mean | DIFFERENT median | DIFFERENT mean |
|---|---:|---:|---:|---:|
| Raw words | 0.7347 | 0.7352 | 0.4505 | 0.4473 |
| Cleaned words | 0.7372 | 0.7415 | 0.4670 | 0.4622 |
| Cleaned 3-shingles | 0.6586 | 0.6661 | **0.2807** | **0.2870** |

Median separation was:

| Representation | SAME median − DIFFERENT median |
|---|---:|
| Raw words | 0.2842 |
| Cleaned words | 0.2702 |
| Cleaned 3-shingles | **0.3779** |

The adopted representation is therefore **cleaned word 3-shingles** because it gave the strongest observed separation in this corpus.

## 5.2 Required SAME example

`N010018` and `N010020` are the same underlying check-dam opportunity.

| Representation | Jaccard |
|---|---:|
| Raw words | 0.3036 |
| Cleaned words | 0.3255 |
| Cleaned 3-shingles | 0.2513 |

The example is useful because one notice is a corrigendum, showing that even true duplicates can have surprisingly low textual overlap.

## 5.3 Required DIFFERENT example

`N007876` concerns CCTV maintenance in Shivamogga; `N008565` concerns solar street lighting in Karur.

| Representation | Jaccard |
|---|---:|
| Raw words | 0.4274 |
| Cleaned words | 0.4502 |
| Cleaned 3-shingles | **0.2206** |

The 3-shingle representation reduces accidental similarity caused by generic procurement language.

---

# 6. A(b) — Similarity Estimator: MinHash

## 6.1 Why exact all-pairs comparison is infeasible

\[
\binom{12000}{2}=71,994,000
\]

Exact comparison of all pairs is unnecessary and incompatible with the nightly budget.

## 6.2 MinHash principle

For a random MinHash function:

\[
P[h(A)=h(B)] = J(A,B)
\]

With `k=256` independent signature positions, the fraction of equal positions estimates the true Jaccard similarity.

## 6.3 Signature-size derivation

Using the binomial approximation:

\[
SE=\sqrt{\frac{s(1-s)}{k}}
\]

The maximum occurs near `s=0.5`:

\[
SE_{max}\approx\sqrt{\frac{0.25}{256}}=0.03125
\]

Approximate 95% half-width:

\[
1.96(0.03125)\approx0.061
\]

Thus 256 hashes give an approximate worst-case 95% half-width of 0.061.

## 6.4 Realized error

| Metric | Result |
|---|---:|
| Mean absolute error | **0.02252** |
| Median absolute error | **0.01772** |
| 95th percentile | **0.05499** |
| Maximum | **0.10633** |

Worst pair: `N009834/N009835`.

```text
Exact Jaccard: 0.620232
MinHash estimate: 0.726562
Absolute error: 0.106330
```

By label:

| Label | Mean abs. error | Median | Max |
|---|---:|---:|---:|
| DIFFERENT | 0.022088 | 0.017999 | 0.080478 |
| SAME | 0.023468 | 0.016555 | 0.106330 |

The system therefore uses MinHash for approximate retrieval, while exact Jaccard remains the final verification metric.

---

# 7. A(c) — Sublinear Candidate Retrieval

## 7.1 LSH configuration

```text
256 MinHash values
        ↓
32 bands × 8 rows
```

The bucket construction is implemented in `src/05_lsh_experiment.py` and reproduced in `src/13_assign_opportunity_ids.py`.

## 7.2 Candidate probability mathematics

For true similarity `s`, one 8-row band matches with probability:

\[
s^8
\]

No band matches with probability:

\[
(1-s^8)^{32}
\]

Therefore:

\[
P(candidate)=1-(1-s^8)^{32}
\]

| Similarity | Candidate probability |
|---:|---:|
| 0.2 | 0.0001 |
| 0.3 | 0.0021 |
| 0.4 | 0.0208 |
| 0.5 | 0.1177 |
| 0.6 | 0.4184 |
| **0.7** | **0.8504** |
| 0.8 | 0.9972 |
| 0.9 | ~1.0000 |

`src/03_lsh_curve.py` generates `results/lsh_candidate_curve.csv` and `plots/lsh_candidate_curve.png`. The selected operating point is 0.7.

## 7.3 Asymmetric cost

The design policy is:

\[
C_{FP}=20,\qquad C_{FN}=1
\]

A false merge is therefore treated as 20 times as costly as a missed merge. This drives a conservative final merge rule while retrieval is tuned separately for candidate survival.

## 7.4 Final exact threshold

Exact cleaned-3-shingle Jaccard distributions:

| Label | Median | Mean | Min | Max |
|---|---:|---:|---:|---:|
| SAME | 0.6257 | 0.6491 | 0.2070 | 1.0000 |
| DIFFERENT | 0.2928 | 0.2974 | 0.1034 | 0.5938 |

At threshold `0.56`:

```text
TP = 177
FP = 1
FN = 102
TN = 620
```

Cost:

\[
20(1)+102=122
\]

The adopted final rule is therefore:

```text
candidate from LSH
    AND
exact cleaned 3-shingle Jaccard >= 0.56
    → merge
```

---

# 8. B(d) — Persistent Retrieval Structure

## 8.1 PostgreSQL schema

The project uses five main tables.

### `notices`

Stores source notice information and normalized text.

### `minhash_signatures`

Stores one 256-value signature per notice. The PostgreSQL type was changed to `BIGINT[]` because 32-bit integer storage overflowed for some signature values.

### `lsh_buckets`

```sql
PRIMARY KEY (band, bucket_hash, notice_id)
```

with:

```sql
CREATE INDEX idx_lsh_lookup
ON lsh_buckets (band, bucket_hash);
```

### `opportunities`

Stores the stable UUID and canonical notice.

### `opportunity_members`

Maps notices to opportunity IDs and stores first/last seen timestamps.

## 8.2 Physical access path

Retrieval knows `band` and the band hash, so `(band, bucket_hash)` is the natural lookup key. The notice ID is retained in the primary key because many notices can occupy the same bucket.

## 8.3 Measurement

Indexed lookup:

```text
Index Only Scan using lsh_buckets_pkey
Heap Fetches: 0
Buffers hit: 8
Planning Time: 1.533 ms
Execution Time: 0.401 ms
```

Forced sequential scan:

```text
Parallel sequential scan
2 workers
Buffers ≈ 3200
Execution Time: 67.055 ms
```

The indexed path avoids scanning the full 384,000-row LSH table for each bucket lookup.

## 8.4 Why not the rejected sequential path?

The sequential scan repeatedly examines a large fraction of the LSH table even though the retrieval predicate is selective. The measured 0.401 ms indexed lookup versus 67.055 ms forced sequential scan demonstrates why the indexed physical layout was selected.

---

# 9. B(e) — Full-Corpus Runtime and Pathology

## 9.1 Baseline

Original full-corpus run:

```text
Runtime:            5528.607 s
Runtime:            92.14 min
Candidate survival: 56.27%
Median candidates:  4
P95:                180
P99:                300
Maximum:            488
```

The baseline exceeded the 20-minute budget by a large margin. The MinHash stage alone consumed 5416.963 seconds.

## 9.2 Pathological subset

The top pathological notices were concentrated in P001, P002 and P005. Nine of the top 20 were P005; most of the remainder were P001/P002.

Examples:

```text
N005589  632  P005
N010943  627  P005
N007704  626  P001
N000200  623  P002
N002634  621  P005
N011667  615  P005
N009077  611  P005
N007560  602  P002
N002290  595  P005
N004053  594  P001
```

The portal profile provides the mechanical explanation: these portals attach large repeated aggregation-service preambles and, for some, repeated disclaimer footers. Those repeated blocks create high-frequency 3-shingles, which create broad LSH collisions.

## 9.3 Mitigation

Shingles appearing in more than 5% of the 12,000 notices were excluded from the **retrieval index**:

\[
0.05\times12000=600
\]

Measured:

```text
Unique shingles: 444841
High-frequency shingles: 1637
Average shingles removed/notice: 443.2
```

The complete cleaned shingle representation remains available for exact verification; only the retrieval representation is filtered.

## 9.4 Before/after

| Metric | Baseline | Mitigated |
|---|---:|---:|
| Runtime | 92.14 min | **20.18 min** |
| True-duplicate candidate survival | 56.27% | **69.53%** |
| Median candidates | 4 | **1** |
| P95 candidates | 180 | **6** |
| P99 candidates | 300 | **7** |
| Maximum | 488 | **8** |

Mitigated runtime was 1210.579 seconds = 20.18 minutes. This is approximately 11 seconds above the nominal 20-minute target and should be reported honestly.

A cached-signature rerun completed in 49.588 seconds, but this is not the main full-pipeline runtime because signature generation was already done.

---

# 10. Persistent Opportunity IDs

## 10.1 Original persistence bug

The first persistence implementation loaded existing assignments but still allowed already-assigned notices to proceed through candidate matching and UUID creation. A notice could therefore acquire a second opportunity membership on a rerun.

The database was restored from `results/opportunity_ids_before_rerun.csv` using `src/15_restore_ids.py`.

## 10.2 Corrected rule

```text
Notice already assigned?
       |
       +-- YES → preserve existing opportunity_id
       |
       +-- NO → retrieve LSH candidates
                    |
                    +-- exact match → reuse opportunity_id
                    |
                    +-- no match → create new UUID
```

The corrected implementation is `src/13_assign_opportunity_ids.py`.

## 10.3 Rerun result

The corrected script produced:

```text
Notices processed:       12000
Existing assignments:    12000
New notices matched:     0
New opportunities:       0
Average candidates:      0.00
```

The zero candidate count is expected because all notices already had authoritative assignments and were intentionally skipped from re-matching.

## 10.4 Stability validation

`src/15_snapshot_ids.py` saved the pre-rerun mapping and `src/15_compare_ids.py` compared it with the post-rerun database.

```text
============================================================
STABLE ID VALIDATION
============================================================
Notices compared:       12000
IDs unchanged:          12000
IDs changed:            0
ID stability:           1.0000

Unique opportunities:
Before rerun:           6747
After rerun:            6747
```

Thus:

\[
\frac{12000}{12000}=1.0000=100\%
\]

The stable opportunity/card identity requirement is therefore demonstrated directly by a complete rerun.

---

# 11. End-to-End Labelled-Pair Validation

The final clustering contained:

```text
12000 notice assignments
6747 unique opportunities
```

Against the 900 labelled pairs:

### SAME

```text
Correctly merged: 153
Missed:            126
```

\[
Recall_{SAME}=153/279=0.5484
\]

### DIFFERENT

```text
Correctly separated: 620
Incorrectly merged:    1
```

\[
Separation=620/621=0.9984
\]

Asymmetric validation cost:

\[
20(1)+126=146
\]

This differs from the threshold-only cost of 122 because the complete pipeline adds LSH candidate misses and assignment behavior. The threshold experiment evaluates the final classifier conditional on a pair being evaluated; end-to-end validation evaluates whether the pair actually survives retrieval and is assigned together.

---

# 12. Ground Truth vs Produced Clusters

The supplied truth metadata contains 5,776 opportunities. The final implementation contains 6,747.

```text
6747 - 5776 = 971
```

The system therefore does not perfectly reproduce the supplied hidden truth partition.

This is consistent with the labelled-pair results: it strongly separates DIFFERENT pairs (620/621) but misses many SAME pairs (153/279). The conservative behavior is consistent with the selected 20:1 false-merge cost policy, but it also identifies a clear area for future improvement: candidate recall and cluster recovery.

---

# 13. Code and Artifact Map

The following filenames were explicitly used during the implementation and should be referenced from the report rather than duplicating code inside the report.

| File | Purpose |
|---|---|
| `src/01_dataset_analysis.py` | Corpus, labels, truth metadata and representative pair inspection |
| `src/03_lsh_curve.py` | LSH candidate-probability curve and operating point |
| `src/05_lsh_experiment.py` | MinHash/LSH experiment and exact bucket construction |
| `src/13_assign_opportunity_ids.py` | Final opportunity assignment, exact verification and persistent UUID logic |
| `src/15_snapshot_ids.py` | Save clean pre-rerun notice→opportunity mapping |
| `src/15_compare_ids.py` | Validate ID stability before/after full rerun |
| `src/15_restore_ids.py` | Restore opportunity tables from the clean snapshot after the diagnosed persistence bug |

The MinHash database loader used during the PostgreSQL phase loads `results/minhash_signatures_256.npz` into `minhash_signatures`. Keep that loader in `src/` under its actual filename in the repository.

If the working tree contains additional experimental scripts from the earlier representation/threshold experiments, keep them in GitHub and add their exact filenames to this table rather than inventing names in the report.

---

# 14. Important Generated Artifacts

```text
results/
├── minhash_signatures_256.npz
├── lsh_candidate_curve.csv
└── opportunity_ids_before_rerun.csv

plots/
└── lsh_candidate_curve.png
```

These artifacts provide reproducible evidence for the estimator, LSH curve and stable-ID experiment.

---

# 15. Final Requirement-to-Evidence Map

| Assignment requirement | Answer / evidence |
|---|---|
| A(a) representation | Cleaned word 3-shingles; measured against raw words and cleaned words |
| A(a) similarity | Exact Jaccard |
| A(a) corpus evidence | SAME/DIFFERENT medians, means, representative pairs |
| A(b) estimator | 256-value MinHash |
| A(b) estimator sizing | SE ≈ 0.03125; 95% half-width ≈ 0.061 |
| A(b) realized error | MAE 0.02252; median 0.01772; P95 0.05499; max 0.10633 |
| A(c) sublinear retrieval | 32×8 LSH |
| A(c) candidate curve | `1-(1-s^8)^32`; operating point 0.7 |
| A(c) asymmetric cost | FP=20, FN=1 |
| A(c) final threshold | 0.56; threshold-only cost 122 |
| B(d) persistence structure | PostgreSQL notices/signatures/buckets/opportunities/members |
| B(d) physical access | `(band,bucket_hash)` B-tree index |
| B(d) rejected path | Forced sequential scan |
| B(d) measurement | 0.401 ms indexed vs 67.055 ms sequential |
| B(e) full-corpus pathology | P001/P002/P005 high-candidate notices |
| B(e) mechanical explanation | Repeated portal boilerplate/footer shingles |
| B(e) mitigation | >600-document-frequency shingle filtering |
| B(e) runtime | 92.14 → 20.18 min |
| B(e) retrieval effect | Candidate survival 56.27% → 69.53%; P95 180 → 6 |
| Stable IDs | 12,000/12,000 unchanged = 100% |

---

# 16. Limitations and Future Improvements

1. **20-minute budget:** 20.18 minutes is slightly above target. The next optimization target should be the MinHash/signature-generation stage.
2. **SAME recall:** end-to-end labelled SAME recall is 54.84%. Candidate retrieval or clustering logic needs improvement if higher duplicate recall is required.
3. **Ground-truth recovery:** 6,747 produced clusters versus 5,776 truth opportunities shows incomplete cluster consolidation.
4. **Corpus-specific DF threshold:** the 600-shingle cutoff should be recomputed or monitored as the corpus and portal mix change.
5. **Corrigenda:** explicit temporal/version-aware handling could improve recall for notices where the corrigendum changes a large part of the text.
6. **Portal-aware canonicalization:** portal-specific repeated blocks could be identified from document frequency or portal profiles rather than relying only on global DF.
7. **Stable IDs:** the persistence rule deliberately prevents existing IDs from changing. Future incremental clustering must preserve this invariant while handling genuinely new notices carefully.

---

# 17. Conclusion

The project demonstrates a complete, measured deduplication pipeline for noisy public procurement notices rather than relying on a single similarity score.

The representation was selected experimentally. Cleaned word 3-shingles gave the strongest observed separation between labelled SAME and DIFFERENT pairs. MinHash reduced each document to a compact 256-value estimator, with a measured MAE of 0.02252. LSH reduced the search space using 32 bands of 8 rows, with the candidate probability derived mathematically as `1-(1-s^8)^32`.

The final merge rule is conservative: exact cleaned 3-shingle Jaccard must reach 0.56, under an explicit cost policy of 20 for a false merge versus 1 for a missed merge. PostgreSQL provides persistent retrieval structures and an indexed `(band,bucket_hash)` access path measured at 0.401 ms compared with 67.055 ms for a forced sequential scan.

The full-corpus experiment exposed a real engineering failure mode. Repeated aggregation-service boilerplate from P001/P002/P005 generated high-frequency shingles and pathological LSH buckets. Filtering shingles appearing in more than 600 notices reduced runtime from 92.14 minutes to 20.18 minutes and improved true-duplicate candidate survival from 56.27% to 69.53% while reducing the P95 candidate count from 180 to 6.

Finally, persistent opportunity identity was implemented explicitly. Existing notice-to-opportunity assignments are now authoritative. The complete rerun test produced 12,000 unchanged IDs out of 12,000, giving 100% observed ID stability and leaving the opportunity count at 6,747.

The system is therefore a functioning end-to-end prototype with measured representation quality, estimator accuracy, candidate retrieval, database access, runtime pathology analysis, mitigation, asymmetric error handling and persistent identities. Its main remaining technical gap is duplicate recall: the final labelled-pair pipeline correctly separates 620/621 DIFFERENT pairs but merges only 153/279 SAME pairs. That limitation is measurable and provides a clear direction for future improvement without weakening the demonstrated protection against false merges or the stable-ID guarantee.

---

## GitHub note

Do not commit database passwords or local connection credentials. Put secrets in environment variables/local configuration and include them in `.gitignore`. Commit the source code, SQL schema/migrations, plots, CSV result summaries and this report.
