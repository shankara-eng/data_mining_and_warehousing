# ANNAPURNA STORES — COMPLETE LAKEHOUSE LAB DOCUMENTATION

## Full implementation record: setup, ingestion, idempotency, dimensional modeling, historical pricing, federation, and reconciliation

---

# 1. Assignment Overview

The Annapurna Stores assignment asks us to build a small modern data platform for a retail company operating **12 supermarkets**.

The platform must:

1. Stand up an object store, relational database, and analytical query engine.
2. Land daily sales files into object storage using an organization that lets a query for one store and one month avoid the other stores and months.
3. Make ingestion safe to run repeatedly even when source files are resent.
4. Design tables behind a dashboard so revenue can be sliced quickly by store, category, day of week, and month.
5. Correctly handle source caveats:
   - not every source line is a sale,
   - product codes can be reused,
   - resends can occur.
6. Make historical reports use the prices that were actually effective during the reporting period.
7. Run one query across object storage and PostgreSQL without first copying one system into the other.
8. Reconcile analytical revenue with Finance's monthly signed-off revenue and classify differences.

The implementation follows the architecture from the course's modern lakehouse material:

```text
             ┌───────────────────────┐
             │      PostgreSQL       │
             │ stores                │
             │ products              │
             │ categories            │
             │ price revisions       │
             └───────────┬───────────┘
                         │
                         │ federation
                         ▼
┌─────────────────┐   ┌───────────────────────┐
│      MinIO      │──▶│        DuckDB         │
│  Object Store   │   │ Federated SQL + ELT   │
│                 │   └───────────┬───────────┘
│ raw sales files │               │
└─────────────────┘               │
                                  ▼
                         ┌──────────────────┐
                         │ Star / Curated   │
                         │ Analytical Model │
                         └────────┬─────────┘
                                  │
                                  ▼
                             Dashboard / BI
```

---

# 2. Technology Stack

| Component | Role |
|---|---|
| Docker Compose | Runs the local data platform |
| MinIO | S3-compatible object storage / raw data lake |
| PostgreSQL 16 | Relational master/reference database |
| DuckDB | Analytical SQL engine and federation layer |
| Python | Data landing / ingestion |
| CSV | Actual landed Annapurna sales source format |
| SQL | Transformations, dimensional model, validation and reconciliation |

The course material's broader architecture is:

**PostgreSQL + MinIO → DuckDB → star schema → curated Parquet / BI**

For this Annapurna dataset, the actual landed sales population used in the lab was CSV-only. A `*.parquet` glob against the landed sales area found no Parquet files.

---

# 3. Project Location and Structure

The lab was run from:

```text
C:\Users\ub02-glab-051\Desktop\shank dmw\annapurna-lakehouse\annapurna-lakehouse
```

Relevant project structure:

```text
annapurna-lakehouse/
│
├── docker-compose.yml
├── masters.sql
├── data/
│   └── sales/
│       └── 4,457 source files
│
├── loader/
│   └── land.py
│
└── ...
```

Important source/reference files:

```text
file_manifest.csv
finance_monthly.csv
masters.sql
billing_notes.md
truth.json
```

---

# 4. Source Population

The complete source population was verified as:

```text
Files      = 4,457
Raw lines  = 1,137,585
```

The `file_manifest.csv` contains the file, store, business date, row count and file kind.

The `truth.json` confirmed the total population.

---

# 5. Important Source Data Caveats

These are critical to the whole solution.

## 5.1 Business date

The filename identifies the business date.

Transaction timestamps can cross midnight.

Therefore, the implementation trusts the business date from the filename / manifest instead of deriving it blindly from the timestamp.

---

## 5.2 Resends

Some days have duplicate/resend files.

A resend can be a **partial resend**, so this is NOT safe:

```text
keep newest file
```

The correct business-level deduplication key is:

```text
(bill_no, line_no)
```

---

## 5.3 Product code is not a permanent identity

The same `product_code` can represent different products at different times.

Example:

```text
P107072
```

was:

```text
product_sk = 2011
Product = iD Fresh Idli Batter 1kg
Valid from = 2019-04-01
Valid to   = 2024-05-31
```

and later:

```text
product_sk = 2221
Product = Farm Fresh Onion 1kg
Valid from = 2024-06-01
Valid to   = 9999-12-31
```

Therefore product identity must use:

```text
product_code + business_date
```

against the product validity period.

---

## 5.4 Not every line is revenue

The source contains:

```text
SALE
RETURN
DISCOUNT
VOID
TAX
TENDER
```

Therefore simply doing:

```sql
SUM(qty * unit_price)
```

is not sufficient unless the line type is handled correctly.

---

## 5.5 TENDER is not revenue

`TENDER` represents payment/bill total information.

It should not be included in revenue.

Including TENDER would approximately double the revenue because TENDER is the bill total and includes tax.

---

## 5.6 Cancelled bills

A cancelled bill can contain the original positive SALE lines and corresponding negative VOID lines.

Example:

```text
S02 / 20241221 / 00053

line 1  P106602   +1   SALE
line 2  P107308   +3   SALE
line 3  P106534   +2   SALE
line 4  P104784   +3   SALE

line 5  P106602   -1   VOID
line 6  P107308   -3   VOID
line 7  P106534   -2   VOID
line 8  P104784   -3   VOID

line 9  TAX
line 10 TENDER
```

The SALE and VOID quantities cancel.

Therefore:

```text
DO NOT simply remove every VOID row.
```

The signed source representation already handles the cancellation.

---

## 5.7 Missing source days

S07 has three genuinely missing days in July 2024.

They should not be reconstructed.

This becomes important during Finance reconciliation.

---

# 6. Source File Dialects

The source files do not all have identical CSV formats.

## S01–S05

Comma-separated CSV.

Typical structure:

```text
bill_no,line_no,product_code,qty,unit_price,line_type,ts
```

ISO-style timestamps.

---

## S06–S09

Semicolon-separated CSV.

Typical structure:

```text
bill_no;line_no;item_code;quantity;rate;type;txn_time
```

Timestamp format:

```text
dd-mm-yyyy HH:MM:SS
```

---

## S10–S12

Comma-separated UTF-8 CSV with BOM.

Timestamps are epoch seconds UTC.

Column order is different.

Therefore the three groups were normalized before being combined.

---

# 7. Starting Docker

The platform was started using:

```bash
docker compose up -d --build
```

Check the containers:

```bash
docker compose ps
```

Check loader output:

```bash
docker compose logs loader
```

MinIO:

```text
API     → http://localhost:9000
Console → http://localhost:9001
```

PostgreSQL:

```text
localhost:5432
```

The MinIO image was changed to:

```text
quay.io/minio/minio:latest
```

because the original `minio/minio:latest` image failed to pull in the lab environment.

---

# 8. PostgreSQL Master Database

Database:

```text
annapurna
```

Tables:

```text
stores
products
product_categories
price_revisions
```

Verified counts:

```text
stores              = 12
product_categories  = 14
products            = 1,224
price_revisions     = 4,320
```

---

# 9. MinIO Raw Data Layout

The bucket is:

```text
annapurna
```

The raw sales prefix is:

```text
raw/sales/
```

The partition layout is:

```text
annapurna/
└── raw/
    └── sales/
        ├── store_id=S01/
        │   └── year=2024/
        │       ├── month=01/
        │       │   ├── SALES_S01_20240101.csv
        │       │   ├── SALES_S01_20240102.csv
        │       │   └── ...
        │       ├── month=02/
        │       └── ...
        │
        ├── store_id=S02/
        ├── store_id=S03/
        ├── ...
        └── store_id=S12/
```

Example object:

```text
raw/sales/store_id=S01/year=2024/month=01/SALES_S01_20240101.csv
```

---

# 10. Why Partition by Store / Year / Month?

The assignment asks for a layout where a query about one store in one month does not have to inspect all 12 stores and all 12 months.

For example:

```text
S01 + January 2024
```

can directly target:

```text
raw/sales/store_id=S01/year=2024/month=01/
```

Instead of potentially enumerating:

```text
4,457 files
```

across all stores and months.

This is the core benefit of the partitioned object layout.

---

# 11. Measuring Exact Files and Bytes

The exact byte counts should be captured from MinIO rather than invented.

Inside the DuckDB container:

```bash
docker compose exec duckdb python
```

Then:

```python
from minio import Minio

client = Minio(
    "minio:9000",
    access_key="admin",
    secret_key="admin12345",
    secure=False
)

bucket = "annapurna"

prefix = "raw/sales/store_id=S01/year=2024/month=01/"

objects = list(
    client.list_objects(
        bucket,
        prefix=prefix,
        recursive=True
    )
)

print("Partition files:", len(objects))
print("Partition bytes:", sum(obj.size for obj in objects))
```

For the entire sales population:

```python
objects = list(
    client.list_objects(
        "annapurna",
        prefix="raw/sales/",
        recursive=True
    )
)

print("All files:", len(objects))
print("All bytes:", sum(obj.size for obj in objects))
```

Known total:

```text
All files = 4,457
```

The exact byte values were not available from the recorded runs, so they should be measured directly and pasted into the final report.

---

# 12. Python Landing Script

The loader used:

```python
import os
import re
from pathlib import Path
from minio import Minio

ENDPOINT = os.environ["MINIO_ENDPOINT"]
ACCESS = os.environ["MINIO_ACCESS_KEY"]
SECRET = os.environ["MINIO_SECRET_KEY"]
BUCKET = os.environ["MINIO_BUCKET"]

ROOT = Path("/input/sales")

PATTERN = re.compile(
    r"SALES_(S\d{2})_(\d{8})(?:__R\d+)?\.(csv|parquet)$",
    re.I
)

client = Minio(
    ENDPOINT,
    access_key=ACCESS,
    secret_key=SECRET,
    secure=False
)

if not client.bucket_exists(BUCKET):
    client.make_bucket(BUCKET)

if not ROOT.exists():
    print("[land] /input/sales does not exist; nothing to land.")
    raise SystemExit(0)

files = 0

for path in sorted(ROOT.rglob("*")):

    if not path.is_file():
        continue

    m = PATTERN.fullmatch(path.name)

    if not m:
        print(f"[land] SKIP unrecognized filename: {path.name}")
        continue

    store, datestr, ext = m.groups()

    year = datestr[:4]
    month = datestr[4:6]

    object_name = (
        f"raw/sales/"
        f"store_id={store}/"
        f"year={year}/"
        f"month={month}/"
        f"{path.name}"
    )

    client.fput_object(
        BUCKET,
        object_name,
        str(path)
    )

    files += 1

    print(
        f"[land] {path.name} -> "
        f"s3://{BUCKET}/{object_name}"
    )

print(f"[land] landed {files} file(s)")
```

The loader successfully landed:

```text
[land] landed 4457 file(s)
```

---

# 13. Connecting DuckDB to MinIO

Start DuckDB:

```bash
docker compose exec duckdb python
```

Connect:

```python
import duckdb

con = duckdb.connect("/workspace/annapurna.duckdb")
```

Load HTTP/S3 support:

```sql
INSTALL httpfs;
LOAD httpfs;
```

Configure MinIO:

```sql
SET s3_endpoint='minio:9000';
SET s3_access_key_id='admin';
SET s3_secret_access_key='admin12345';
SET s3_url_style='path';
SET s3_use_ssl=false;
```

---

# 14. Testing the MinIO Glob

Example:

```sql
SELECT COUNT(*)
FROM read_csv_auto(
    's3://annapurna/raw/sales/store_id=S01/year=2024/month=01/*.csv'
);
```

For the S01 January 1–6 sample that was tested, the glob resolved to:

```text
6 CSV files
```

and:

```text
1,669 raw lines
```

This demonstrated that DuckDB can directly read the relevant MinIO partition.

---

# QUESTION 1
# STAND UP THE PLATFORM AND LAND DATA

## Requirement

The platform must have:

- object store
- relational database
- analytical query engine

and sales files must be organized so that a query for one store and one month
does not need to inspect all other stores/months.

## Solution

```text
Object store       = MinIO
Relational DB      = PostgreSQL
Analytical engine  = DuckDB
```

Storage:

```text
raw/sales/store_id=SXX/year=YYYY/month=MM/
```

The full source population is:

```text
4,457 files
1,137,585 raw lines
```

A store/month query can target only the relevant partition.

---

# QUESTION 2
# MAKE THE LOAD SAFE TO RUN TWICE

## Requirement

Resends occur.

Running the pipeline three times must produce the same result as running it
once.

## Correct business key

```text
bill_no + line_no
```

Not:

```text
filename
```

because a resend can be partial.

---

# 15. Normalizing the Source Files

The three source dialect groups were normalized into:

```text
sales_s01_s05
sales_s06_s09
sales_s10_s12
```

Counts:

```text
sales_s01_s05 = 513,576
sales_s06_s09 = 327,136
sales_s10_s12 = 296,873
```

Combined:

```text
sales_all = 1,137,585
```

This exactly matches the raw source population.

---

# 16. Full Deduplication Query

```sql
CREATE OR REPLACE TABLE sales_dedup AS
SELECT *
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY bill_no, line_no
            ORDER BY filename
        ) AS rn
    FROM sales_all
)
WHERE rn = 1;
```

Check row count:

```sql
SELECT COUNT(*) FROM sales_dedup;
```

Result:

```text
1,120,924
```

---

# 17. Duplicate Count

```sql
SELECT
    COUNT(*) AS raw_rows,
    COUNT(DISTINCT (bill_no, line_no)) AS unique_business_lines,
    COUNT(*) - COUNT(DISTINCT (bill_no, line_no)) AS duplicates_removed
FROM sales_all;
```

Expected result:

```text
raw_rows              = 1,137,585
unique_business_lines = 1,120,924
duplicates_removed    = 16,661
```

Therefore:

```text
1,137,585 - 1,120,924 = 16,661
```

duplicate/resend rows were removed.

---

# 18. Verify Business-Key Uniqueness

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT (bill_no, line_no)) AS unique_business_lines
FROM sales_dedup;
```

Result:

```text
total_rows             = 1,120,924
unique_business_lines  = 1,120,924
```

Therefore every business line is unique after deduplication.

---

# 19. Content Checksum

Checksum query:

```sql
SELECT
    md5(
        string_agg(
            concat_ws(
                '|',
                business_date,
                store_id,
                bill_no,
                line_no,
                product_code,
                qty,
                unit_price,
                line_type
            ),
            '||'
            ORDER BY
                store_id,
                business_date,
                bill_no,
                line_no
        )
    ) AS checksum
FROM sales_dedup;
```

Result:

```text
719ad925ba833be4b2e2809e9c0ad5b3
```

---

# 20. Three-Run Idempotency Proof

The full deduplication process was executed three times.

| Run | Rows | Checksum |
|---|---:|---|
| Run 1 | 1,120,924 | `719ad925ba833be4b2e2809e9c0ad5b3` |
| Run 2 | 1,120,924 | `719ad925ba833be4b2e2809e9c0ad5b3` |
| Run 3 | 1,120,924 | `719ad925ba833be4b2e2809e9c0ad5b3` |

Therefore:

```text
Run 1 = Run 2 = Run 3
```

both by row count and content checksum.

This is the actual three-run idempotency evidence.

---

# 21. Earlier Sample Idempotency Test

A smaller S01 January 1–6 sample was also tested.

Rows:

```text
1,669
```

Checksum:

```text
5f264f9797824e6479c46ef2482b03f3
```

All three sample runs produced the same result.

The important final proof, however, is the full-population result:

```text
1,120,924
719ad925ba833be4b2e2809e9c0ad5b3
```

---

# QUESTION 3
# DESIGN THE TABLES BEHIND THE DASHBOARD

## Requirement

The dashboard must quickly slice revenue by:

- store
- product category
- day of week
- month

Store information should not be repeated across millions of sales records.

The model must also handle product-code reuse and non-sale lines.

---

# 22. Star Schema

The analytical model is:

```text
                       dim_store
                           │
                           │
                           ▼
                      fact_sales
                      /    |    \
                     /     |     \
                    ▼      ▼      ▼
            dim_product  dim_date  dim_category
```

Detailed:

```text
┌──────────────────┐
│    dim_store     │
├──────────────────┤
│ store_id         │
│ store_name       │
│ address_line     │
│ city             │
│ state            │
│ region           │
│ floor_area_sqft  │
│ opened_on        │
└────────┬─────────┘
         │
         │
         ▼
┌────────────────────────────┐
│         fact_sales         │
├────────────────────────────┤
│ bill_no                    │
│ line_no                    │
│ date_sk                    │
│ store_id                   │
│ product_sk                 │
│ qty                        │
│ unit_price                 │
│ line_type                  │
└──────────┬─────────────────┘
           │
      ┌────┴────┐
      │         │
      ▼         ▼
dim_product   dim_date
      │
      ▼
dim_category
```

The dimensions hold descriptive attributes.

The fact table holds transaction-level measures and keys.

This prevents repeatedly storing store name/address/category text on every
fact row.

---

# 23. dim_store

```sql
CREATE OR REPLACE TABLE dim_store AS
SELECT *
FROM pg.public.stores;
```

Result:

```text
12 rows
```

---

# 24. dim_product

```sql
CREATE OR REPLACE TABLE dim_product AS
SELECT *
FROM pg.public.products;
```

Result:

```text
1,224 rows
```

Important columns:

```text
product_sk
product_code
product_name
category_id
brand
pack_size
uom
valid_from
valid_to
is_current
```

---

# 25. dim_category

```sql
CREATE OR REPLACE TABLE dim_category AS
SELECT *
FROM pg.public.product_categories;
```

Result:

```text
14 rows
```

---

# 26. dim_date

A complete 2024 date dimension was generated:

```sql
CREATE OR REPLACE TABLE dim_date AS
SELECT
    d::DATE AS date_sk,
    EXTRACT(YEAR FROM d)::INTEGER AS year,
    EXTRACT(MONTH FROM d)::INTEGER AS month,
    strftime(d, '%B') AS month_name,
    EXTRACT(DAY FROM d)::INTEGER AS day_of_month,
    EXTRACT(DOW FROM d)::INTEGER AS day_of_week_number,
    strftime(d, '%A') AS day_of_week
FROM generate_series(
    DATE '2024-01-01',
    DATE '2024-12-31',
    INTERVAL 1 DAY
) t(d);
```

Result:

```text
366 rows
```

2024 is a leap year.

---

# 27. fact_sales

Product identity is resolved using both product code and product validity dates.

```sql
CREATE OR REPLACE TABLE fact_sales AS
SELECT
    s.bill_no,
    s.line_no,
    s.business_date AS date_sk,
    s.store_id,
    p.product_sk,
    s.qty,
    s.unit_price,
    s.line_type
FROM sales_dedup s
LEFT JOIN dim_product p
    ON s.product_code = p.product_code
   AND s.business_date >= p.valid_from
   AND s.business_date <= p.valid_to;
```

Result:

```text
fact_sales = 1,120,924 rows
```

---

# 28. Fact Table Mapping Results

Product-bearing lines:

```text
SALE    = 745,860
RETURN  = 16,161
```

Both mapped successfully:

```text
SALE unmatched   = 0
RETURN unmatched = 0
```

The unmatched fact rows are explained by non-product lines:

```text
TAX       = 165,704
TENDER    = 165,704
DISCOUNT  = 22,603
VOID      = 117 unmatched
```

The 117 unmatched VOID rows use:

```text
product_code = DISC
```

and represent discount-related records rather than real products.

---

# 29. Revenue Table

Create the explicit revenue measure:

```sql
CREATE OR REPLACE TABLE sales_revenue AS
SELECT
    business_date,
    store_id,
    bill_no,
    line_no,
    product_code,
    qty,
    unit_price,
    line_type,
    CASE
        WHEN line_type IN (
            'SALE',
            'RETURN',
            'VOID',
            'DISCOUNT'
        )
        THEN qty * unit_price
        ELSE 0
    END AS revenue
FROM sales_dedup;
```

Revenue treatment:

| Line type | Revenue treatment |
|---|---|
| SALE | `qty * unit_price` |
| RETURN | `qty * unit_price` (already signed negative) |
| DISCOUNT | `qty * unit_price` (already signed negative) |
| VOID | `qty * unit_price` (signed cancellation) |
| TAX | `0` |
| TENDER | `0` |

---

# 30. Discount Validation

```sql
SELECT
    COUNT(*) AS discount_rows,
    SUM(qty * unit_price) AS discount_amount
FROM sales_dedup
WHERE line_type = 'DISCOUNT';
```

Result:

```text
discount_rows  = 22,603
discount_amount = -5,294,511.42
```

Discounts are already negative.

Do not negate them again.

---

# 31. Return Validation

```sql
SELECT
    COUNT(*) AS return_rows,
    SUM(qty) AS return_qty,
    SUM(qty * unit_price) AS return_amount
FROM sales_dedup
WHERE line_type = 'RETURN';
```

Result:

```text
return_rows   = 16,161
return_qty    = -33,852
return_amount = -11,779,518.409999985
```

Returns are already represented as negative values.

---

# 32. Dashboard Query — Store + Category + Month

Example for March 2024:

```sql
SELECT
    s.store_name,
    c.category_name,
    ROUND(SUM(r.revenue), 2) AS revenue
FROM sales_revenue r

JOIN dim_store s
    ON r.store_id = s.store_id

JOIN dim_product p
    ON r.product_code = p.product_code
   AND r.business_date >= p.valid_from
   AND r.business_date <= p.valid_to

JOIN dim_category c
    ON p.category_id = c.category_id

WHERE r.business_date >= DATE '2024-03-01'
  AND r.business_date < DATE '2024-04-01'

GROUP BY
    s.store_name,
    c.category_name

ORDER BY
    s.store_name,
    revenue DESC

LIMIT 20;
```

Example observed output:

```text
Annapurna Andheri West | Staples & Grains | ₹876,274.97
Annapurna Andheri West | Baby Care       | ₹728,872.16
...
```

This proves the analytical model can slice by store, category and month.

`dim_date` provides day-of-week attributes for additional slicing.

---

# QUESTION 4
# MAKE MARCH USE MARCH PRICES

## Requirement

A historical report must use the price that applied during the reporting period.

March 2024 must use March's effective price revisions.

The same query logic must work for other months without changing the temporal
pricing logic.

---

# 33. Historical Price Example

For:

```text
product_sk = 1002
```

the price revisions are:

```text
2022-01-01 → 2023-09-18    ₹119.95
2023-09-19 → 2024-05-23    ₹129.42
2024-05-24 → 2024-07-27    ₹149.27
2024-07-28 → onward        ₹155.06
```

Therefore March 2024 falls into:

```text
2023-09-19 → 2024-05-23
```

and the applicable selling price is:

```text
₹129.42
```

for that product.

---

# 34. Temporal Product + Price Query

```sql
CREATE OR REPLACE TABLE sales_with_price AS
SELECT
    r.business_date,
    r.store_id,
    r.bill_no,
    r.line_no,
    r.product_code,
    r.qty,
    r.line_type,
    p.product_sk,
    pr.selling_price AS historical_selling_price,
    r.qty * pr.selling_price AS historical_amount
FROM sales_dedup r

JOIN dim_product p
    ON r.product_code = p.product_code
   AND r.business_date >= p.valid_from
   AND r.business_date <= p.valid_to

JOIN pg.public.price_revisions pr
    ON p.product_sk = pr.product_sk
   AND r.business_date >= pr.effective_from
   AND r.business_date <= pr.effective_to

WHERE r.business_date >= DATE '2024-03-01'
  AND r.business_date < DATE '2024-04-01';
```

March result:

```text
₹42,393,185.70
```

---

# 35. Same Temporal Logic Across All Months

The same historical-price query logic produced:

| Month | Historical price amount |
|---|---:|
| Jan | ₹38,854,750.65 |
| Feb | ₹35,232,778.94 |
| Mar | ₹42,393,185.70 |
| Apr | ₹38,331,732.06 |
| May | ₹42,186,750.14 |
| Jun | ₹39,351,042.82 |
| Jul | ₹40,692,351.40 |
| Aug | ₹45,709,042.44 |
| Sep | ₹45,079,707.77 |
| Oct | ₹56,916,225.40 |
| Nov | ₹52,085,772.16 |
| Dec | ₹51,247,862.94 |

The important point is:

```text
The pricing logic stays the same.
The transaction business date changes.
```

The temporal join automatically chooses the applicable revision.

---

# QUESTION 5
# QUERY ACROSS TWO SYSTEMS

## Requirement

Sales are stored in object storage.

Stores/products/categories are stored in PostgreSQL.

Run one query that joins the two systems without copying either dataset.

---

# 36. Attach PostgreSQL to DuckDB

```sql
INSTALL postgres;
LOAD postgres;

ATTACH
    'dbname=annapurna user=annapurna password=annapurna host=postgres port=5432'
AS pg
(TYPE POSTGRES);
```

Now PostgreSQL can be accessed from DuckDB as:

```text
pg.public.stores
pg.public.products
pg.public.product_categories
pg.public.price_revisions
```

---

# 37. Federated MinIO + PostgreSQL Query

This is the important query for the assignment because sales are read directly
from MinIO while store data is read directly from PostgreSQL.

```sql
SELECT
    s.store_id,
    s.store_name,

    SUM(
        CASE
            WHEN f.line_type = 'SALE'
                THEN f.qty * f.unit_price

            WHEN f.line_type = 'RETURN'
                THEN -f.qty * f.unit_price

            WHEN f.line_type = 'DISCOUNT'
                THEN -f.qty * f.unit_price

            WHEN f.line_type = 'VOID'
                THEN f.qty * f.unit_price

            ELSE 0
        END
    ) AS revenue

FROM read_csv_auto(
    's3://annapurna/raw/sales/store_id=S01/year=2024/month=01/*.csv'
) f

JOIN pg.public.stores s
    ON f.store_id = s.store_id

GROUP BY
    s.store_id,
    s.store_name;
```

Observed result:

```text
store_id   = S01
store_name = Annapurna Jayanagar
revenue    = ₹855,863.71
```

---

# 38. EXPLAIN the Federated Query

Run:

```sql
EXPLAIN
SELECT
    s.store_id,
    s.store_name,

    SUM(
        CASE
            WHEN f.line_type = 'SALE'
                THEN f.qty * f.unit_price
            WHEN f.line_type = 'RETURN'
                THEN -f.qty * f.unit_price
            WHEN f.line_type = 'DISCOUNT'
                THEN -f.qty * f.unit_price
            WHEN f.line_type = 'VOID'
                THEN f.qty * f.unit_price
            ELSE 0
        END
    ) AS revenue

FROM read_csv_auto(
    's3://annapurna/raw/sales/store_id=S01/year=2024/month=01/*.csv'
) f

JOIN pg.public.stores s
    ON f.store_id = s.store_id

GROUP BY
    s.store_id,
    s.store_name;
```

Observed plan shape:

```text
HASH_GROUP_BY
    │
    ▼
PROJECTION
    │
    ▼
HASH_JOIN
    ├── READ_CSV_AUTO
    │       │
    │       └── MinIO / S3
    │
    └── POSTGRES_SCAN
            │
            └── PostgreSQL
```

This is the required evidence.

It shows:

```text
MinIO
  ↓
READ_CSV_AUTO
  ↓
DuckDB

PostgreSQL
  ↓
POSTGRES_SCAN
  ↓
DuckDB

Both inputs
  ↓
HASH_JOIN
  ↓
DuckDB
```

No full data copy between systems is necessary.

---

# 39. EXPLAIN Caveat

If you run `EXPLAIN` against:

```text
sales_revenue
```

you may see:

```text
SEQ_SCAN
```

because `sales_revenue` is already a materialized DuckDB table.

That does not directly prove live MinIO federation.

For Question 5, the stronger evidence is the plan containing:

```text
READ_CSV_AUTO
POSTGRES_SCAN
HASH_JOIN
```

because that directly proves both systems participate in the same query.

---

# QUESTION 6
# RECONCILE AGAINST FINANCE

## Requirement

Compare monthly pipeline revenue with:

```text
finance_monthly.csv
```

Every difference must be classified as:

1. source data
2. revenue definition difference
3. pipeline bug

Then identify which issue should be taken back to Finance.

---

# 40. Finance Data

The Finance table contains the signed-off monthly revenue.

Important revenue column:

```text
revenue_inr
```

Example:

```text
2024-01 | 2024-02-09 | 38446071.33 | A. Krishnan (Finance Controller)
```

---

# 41. Pipeline Revenue

The pipeline revenue definition is:

```sql
CASE
    WHEN line_type IN (
        'SALE',
        'RETURN',
        'VOID',
        'DISCOUNT'
    )
    THEN qty * unit_price
    ELSE 0
END
```

Monthly pipeline revenue:

| Month | Pipeline revenue |
|---|---:|
| Jan | ₹38,446,071.33 |
| Feb | ₹34,887,085.55 |
| Mar | ₹41,971,649.09 |
| Apr | ₹37,958,457.37 |
| May | ₹41,764,716.40 |
| Jun | ₹38,987,082.82 |
| Jul | ₹40,295,160.11 |
| Aug | ₹45,252,181.75 |
| Sep | ₹44,615,037.46 |
| Oct | ₹56,359,195.92 |
| Nov | ₹51,583,838.47 |
| Dec | ₹50,745,259.48 |

---

# 42. Reconciliation Query

```sql
SELECT
    strftime(r.business_date, '%Y-%m') AS month,

    ROUND(SUM(r.revenue), 2)
        AS pipeline_revenue,

    ROUND(MAX(f.revenue_inr), 2)
        AS finance_revenue,

    ROUND(
        SUM(r.revenue) - MAX(f.revenue_inr),
        2
    ) AS difference

FROM sales_revenue r

JOIN finance_monthly f
    ON strftime(r.business_date, '%Y-%m') = f.month

GROUP BY 1

ORDER BY 1;
```

---

# 43. Actual Reconciliation Output

```text
('2024-01', 38446071.33, 38446071.33, 0.0)
('2024-02', 34887085.55, 34887085.55, 0.0)
('2024-03', 41971649.09, 42457899.09, -486250.0)
('2024-04', 37958457.37, 37958457.37, 0.0)
('2024-05', 41764716.40, 41764716.40, 0.0)
('2024-06', 38987082.82, 38987082.82, 0.0)
('2024-07', 40295160.11, 40527291.81, -232131.7)
('2024-08', 45252181.75, 45252181.75, 0.0)
('2024-09', 44615037.46, 44615037.46, 0.0)
('2024-10', 56359195.92, 56359195.92, 0.0)
('2024-11', 51583838.47, 51583838.47, -0.0)
('2024-12', 50745259.48, 50745209.00, 50.48)
```

---

# 44. Reconciliation Classification

| Month | Difference | Classification | Reason |
|---|---:|---|---|
| March | -₹486,250.00 | Source data / scope | Finance includes an institutional order invoiced outside the till system |
| July | -₹232,131.70 | Source data | Finance includes three S07 days that are absent from the source folder |
| December | +₹50.48 | Revenue definition / calculation convention | Finance rounds each bill to the rupee before monthly aggregation |
| Other months | ₹0.00 | No difference | Pipeline matches Finance |

No pipeline bug was identified from the observed reconciliation differences.

---

# 45. March Difference

Finance:

```text
₹42,457,899.09
```

Pipeline:

```text
₹41,971,649.09
```

Difference:

```text
₹42,457,899.09 - ₹41,971,649.09
= ₹486,250.00
```

The assignment notes identify this amount as an institutional order invoiced
outside the till system.

Therefore the difference is caused by source/scope coverage.

It should be taken back to Finance/source ownership as a scope reconciliation
item.

---

# 46. July Difference

Finance:

```text
₹40,527,291.81
```

Pipeline:

```text
₹40,295,160.11
```

Difference:

```text
₹232,131.70
```

The source notes indicate that S07 has three genuinely missing July days.

The pipeline should not invent those transactions.

This should be raised as missing source coverage.

---

# 47. December Difference

Finance:

```text
₹50,745,209.00
```

Pipeline:

```text
₹50,745,259.48
```

Difference:

```text
+₹50.48
```

Finance rounds each bill to the rupee before monthly aggregation.

The analytical pipeline aggregates the underlying decimal values.

Therefore the small difference is a calculation/rounding convention difference.

This should be documented and discussed with Finance.

---

# 48. October TENDER Diagnostic

October Finance:

```text
₹56,359,195.92
```

October pipeline:

```text
₹56,359,195.92
```

They match exactly.

This is important because the assignment warns that including `TENDER` in
revenue can make October approximately double.

The matching October result supports the implementation's treatment:

```text
TENDER = 0 revenue contribution
```

---

# 49. Complete Finance Reconciliation Table

| Month | Pipeline | Finance | Difference |
|---|---:|---:|---:|
| Jan | ₹38,446,071.33 | ₹38,446,071.33 | ₹0.00 |
| Feb | ₹34,887,085.55 | ₹34,887,085.55 | ₹0.00 |
| Mar | ₹41,971,649.09 | ₹42,457,899.09 | -₹486,250.00 |
| Apr | ₹37,958,457.37 | ₹37,958,457.37 | ₹0.00 |
| May | ₹41,764,716.40 | ₹41,764,716.40 | ₹0.00 |
| Jun | ₹38,987,082.82 | ₹38,987,082.82 | ₹0.00 |
| Jul | ₹40,295,160.11 | ₹40,527,291.81 | -₹232,131.70 |
| Aug | ₹45,252,181.75 | ₹45,252,181.75 | ₹0.00 |
| Sep | ₹44,615,037.46 | ₹44,615,037.46 | ₹0.00 |
| Oct | ₹56,359,195.92 | ₹56,359,195.92 | ₹0.00 |
| Nov | ₹51,583,838.47 | ₹51,583,838.47 | ₹0.00 |
| Dec | ₹50,745,259.48 | ₹50,745,209.00 | +₹50.48 |

---

# 50. Important Queries — Quick Reference

## Count all raw rows

```sql
SELECT COUNT(*) FROM sales_all;
```

Expected:

```text
1,137,585
```

---

## Count deduplicated rows

```sql
SELECT COUNT(*) FROM sales_dedup;
```

Expected:

```text
1,120,924
```

---

## Check duplicate business keys

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT (bill_no, line_no)) AS unique_business_lines
FROM sales_dedup;
```

Expected:

```text
1,120,924 | 1,120,924
```

---

## Check checksum

```sql
SELECT
    md5(
        string_agg(
            concat_ws(
                '|',
                business_date,
                store_id,
                bill_no,
                line_no,
                product_code,
                qty,
                unit_price,
                line_type
            ),
            '||'
            ORDER BY
                store_id,
                business_date,
                bill_no,
                line_no
        )
    )
FROM sales_dedup;
```

Expected:

```text
719ad925ba833be4b2e2809e9c0ad5b3
```

---

## Check fact count

```sql
SELECT COUNT(*) FROM fact_sales;
```

Expected:

```text
1,120,924
```

---

## Check product-bearing mapping

```sql
SELECT
    line_type,
    COUNT(*) AS rows,
    COUNT(*) FILTER (WHERE product_sk IS NULL) AS unmatched
FROM fact_sales
GROUP BY line_type
ORDER BY line_type;
```

Key result:

```text
SALE    → 745,860 rows, 0 unmatched
RETURN  → 16,161 rows, 0 unmatched
```

---

## Check revenue by month

```sql
SELECT
    strftime(business_date, '%Y-%m') AS month,
    ROUND(SUM(revenue), 2) AS revenue
FROM sales_revenue
GROUP BY 1
ORDER BY 1;
```

---

## Dashboard query

```sql
SELECT
    s.store_name,
    c.category_name,
    ROUND(SUM(r.revenue), 2) AS revenue
FROM sales_revenue r
JOIN dim_store s
    ON r.store_id = s.store_id
JOIN dim_product p
    ON r.product_code = p.product_code
   AND r.business_date >= p.valid_from
   AND r.business_date <= p.valid_to
JOIN dim_category c
    ON p.category_id = c.category_id
WHERE r.business_date >= DATE '2024-03-01'
  AND r.business_date < DATE '2024-04-01'
GROUP BY s.store_name, c.category_name
ORDER BY s.store_name, revenue DESC
LIMIT 20;
```

---

## Historical price query

```sql
SELECT
    r.business_date,
    r.store_id,
    r.bill_no,
    r.line_no,
    r.product_code,
    r.qty,
    r.line_type,
    p.product_sk,
    pr.selling_price AS historical_selling_price,
    r.qty * pr.selling_price AS historical_amount
FROM sales_dedup r
JOIN dim_product p
    ON r.product_code = p.product_code
   AND r.business_date >= p.valid_from
   AND r.business_date <= p.valid_to
JOIN pg.public.price_revisions pr
    ON p.product_sk = pr.product_sk
   AND r.business_date >= pr.effective_from
   AND r.business_date <= pr.effective_to
WHERE r.business_date >= DATE '2024-03-01'
  AND r.business_date < DATE '2024-04-01';
```

March result:

```text
₹42,393,185.70
```

---

## Federated query

```sql
SELECT
    s.store_id,
    s.store_name,
    SUM(
        CASE
            WHEN f.line_type = 'SALE'
                THEN f.qty * f.unit_price
            WHEN f.line_type = 'RETURN'
                THEN -f.qty * f.unit_price
            WHEN f.line_type = 'DISCOUNT'
                THEN -f.qty * f.unit_price
            WHEN f.line_type = 'VOID'
                THEN f.qty * f.unit_price
            ELSE 0
        END
    ) AS revenue
FROM read_csv_auto(
    's3://annapurna/raw/sales/store_id=S01/year=2024/month=01/*.csv'
) f
JOIN pg.public.stores s
    ON f.store_id = s.store_id
GROUP BY s.store_id, s.store_name;
```

Result:

```text
S01 | Annapurna Jayanagar | ₹855,863.71
```

---

## Federated EXPLAIN

```sql
EXPLAIN
SELECT
    s.store_id,
    s.store_name,
    SUM(
        CASE
            WHEN f.line_type = 'SALE'
                THEN f.qty * f.unit_price
            WHEN f.line_type = 'RETURN'
                THEN -f.qty * f.unit_price
            WHEN f.line_type = 'DISCOUNT'
                THEN -f.qty * f.unit_price
            WHEN f.line_type = 'VOID'
                THEN f.qty * f.unit_price
            ELSE 0
        END
    ) AS revenue
FROM read_csv_auto(
    's3://annapurna/raw/sales/store_id=S01/year=2024/month=01/*.csv'
) f
JOIN pg.public.stores s
    ON f.store_id = s.store_id
GROUP BY s.store_id, s.store_name;
```

Expected evidence in plan:

```text
READ_CSV_AUTO
POSTGRES_SCAN
HASH_JOIN
HASH_GROUP_BY
```

---

## Finance reconciliation

```sql
SELECT
    strftime(r.business_date, '%Y-%m') AS month,
    ROUND(SUM(r.revenue), 2) AS pipeline_revenue,
    ROUND(MAX(f.revenue_inr), 2) AS finance_revenue,
    ROUND(
        SUM(r.revenue) - MAX(f.revenue_inr),
        2
    ) AS difference
FROM sales_revenue r
JOIN finance_monthly f
    ON strftime(r.business_date, '%Y-%m') = f.month
GROUP BY 1
ORDER BY 1;
```

---

# 51. Final Architecture

```text
                         ┌──────────────────────┐
                         │   4,457 Daily Files   │
                         │   1,137,585 Lines     │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │        MinIO         │
                         │                      │
                         │ raw/sales/           │
                         │ store/year/month     │
                         └──────────┬───────────┘
                                    │
                                    │ S3
                                    ▼
                    ┌──────────────────────────────┐
                    │            DuckDB            │
                    │                              │
                    │  Normalize                   │
                    │      ↓                       │
                    │  sales_all                    │
                    │      ↓                       │
                    │  sales_dedup                 │
                    │      ↓                       │
                    │  sales_revenue               │
                    │      ↓                       │
                    │  fact_sales                  │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
                dim_store    dim_product     dim_date
                                   │
                                   ▼
                             dim_category
                                   │
                                   ▼
                           price_revisions
                           (PostgreSQL)
                                   │
                                   ▼
                           Dashboard / BI
                                   │
                                   ▼
                           Finance Reconciliation
```

---

# 52. Final Validation Checklist

## Question 1

- [x] MinIO deployed
- [x] PostgreSQL deployed
- [x] DuckDB deployed
- [x] 4,457 files landed
- [x] Partitioned by store/year/month
- [x] Targeted store/month query demonstrated
- [ ] Exact partition byte count captured
- [ ] Exact total byte count captured

## Question 2

- [x] Source dialects normalized
- [x] 1,137,585 raw rows
- [x] Deduplication key = `(bill_no, line_no)`
- [x] 1,120,924 rows after dedup
- [x] 16,661 duplicate rows removed
- [x] Three runs performed
- [x] Same row count every run
- [x] Same checksum every run

## Question 3

- [x] dim_store
- [x] dim_product
- [x] dim_category
- [x] dim_date
- [x] fact_sales
- [x] Product-code reuse handled temporally
- [x] Revenue line types handled
- [x] Dashboard query demonstrated

## Question 4

- [x] PostgreSQL price revisions
- [x] Temporal price join
- [x] March price result
- [x] Same temporal logic across months

## Question 5

- [x] PostgreSQL attached to DuckDB
- [x] MinIO directly queried
- [x] PostgreSQL directly queried
- [x] One federated query
- [x] READ_CSV_AUTO evidence
- [x] POSTGRES_SCAN evidence
- [x] HASH_JOIN evidence
- [x] No full copy required

## Question 6

- [x] Finance data loaded
- [x] Monthly reconciliation
- [x] March classified
- [x] July classified
- [x] December classified
- [x] No pipeline bug identified
- [x] October TENDER warning checked

---

# 53. Screenshots / Evidence to Submit

Recommended evidence:

### 1. Docker platform

```bash
docker compose ps
```

Show MinIO, PostgreSQL and DuckDB.

### 2. MinIO layout

Show:

```text
annapurna
└── raw
    └── sales
        └── store_id=S01
            └── year=2024
                └── month=01
```

### 3. Loader output

Show:

```text
[land] landed 4457 file(s)
```

### 4. Raw population

Show:

```sql
SELECT COUNT(*) FROM sales_all;
```

Result:

```text
1,137,585
```

### 5. Deduplicated population

Show:

```sql
SELECT COUNT(*) FROM sales_dedup;
```

Result:

```text
1,120,924
```

### 6. Three-run proof

Show:

```text
Run 1 → 1,120,924 → 719ad925ba833be4b2e2809e9c0ad5b3
Run 2 → 1,120,924 → 719ad925ba833be4b2e2809e9c0ad5b3
Run 3 → 1,120,924 → 719ad925ba833be4b2e2809e9c0ad5b3
```

### 7. Star schema tables

Show:

```text
fact_sales
dim_store
dim_product
dim_category
dim_date
```

### 8. Product-code reuse

Show `P107072` with both product identities and validity periods.

### 9. Historical pricing

Show the March temporal price query and:

```text
₹42,393,185.70
```

### 10. Federation

Show EXPLAIN containing:

```text
READ_CSV_AUTO
POSTGRES_SCAN
HASH_JOIN
```

### 11. Reconciliation

Show the monthly table and the three differences:

```text
March    -₹486,250.00
July     -₹232,131.70
December +₹50.48
```

---

# 54. Viva — Question 1

### Why MinIO?

The sales data arrives as files, so an object store is a natural raw-data
landing layer. MinIO provides an S3-compatible local object store.

### Why partition by store/year/month?

Because the common analytical access pattern includes store and time filters.
Partitioning lets the engine target the relevant object prefix instead of the
whole population.

### Why DuckDB?

DuckDB provides analytical SQL and can query files directly while also
federating with PostgreSQL.

---

# 55. Viva — Question 2

### Why not deduplicate by filename?

Because a resend may be partial. Filename-level deduplication cannot guarantee
business-level uniqueness.

### What is the deduplication key?

```text
bill_no + line_no
```

### How was idempotency proved?

The full transformation was run three times.

All three produced:

```text
1,120,924 rows
719ad925ba833be4b2e2809e9c0ad5b3
```

---

# 56. Viva — Question 3

### Why a star schema?

The dashboard repeatedly groups transaction facts by descriptive dimensions.

Instead of repeating:

```text
store_name
address
category_name
product_name
```

on millions of records, the fact table uses dimension keys.

### Why is product code not enough?

Because the source reuses product codes.

The product must be resolved by:

```text
product_code + business_date
```

---

# 57. Viva — Question 4

### Why not use the current product price?

Because historical reports need the price effective on the transaction date.

The temporal condition is:

```text
product_sk
AND
business_date BETWEEN effective_from AND effective_to
```

The same logic works for March, April, May, etc.

---

# 58. Viva — Question 5

### What is federation?

Federation means DuckDB can query multiple systems in one SQL statement without
first copying the complete datasets into one database.

Here:

```text
sales   → MinIO
stores  → PostgreSQL
```

DuckDB reads both and joins them.

### What proves this?

The EXPLAIN plan:

```text
READ_CSV_AUTO
POSTGRES_SCAN
HASH_JOIN
```

---

# 59. Viva — Question 6

### Why do three months differ?

They have different documented causes:

```text
March
→ institutional order outside till scope

July
→ missing S07 source days

December
→ Finance rounds each bill to the rupee
```

### Is this necessarily a pipeline bug?

No. The evidence indicates source/scope and calculation-convention differences
for these months. No pipeline bug was identified from the reconciliation.

### Why is October important?

Because TENDER is not revenue.

October matches Finance exactly at:

```text
₹56,359,195.92
```

which supports excluding TENDER from revenue.

---

# 60. Key Numbers for the Viva

```text
Stores                  = 12
Categories              = 14
Products                = 1,224
Price revisions         = 4,320

Raw files               = 4,457
Raw rows                = 1,137,585

Deduplicated rows       = 1,120,924
Duplicates removed      = 16,661

Dedup checksum          = 719ad925ba833be4b2e2809e9c0ad5b3

dim_date rows           = 366
fact_sales rows         = 1,120,924

March difference        = ₹486,250.00
July difference         = ₹232,131.70
December difference     = ₹50.48

March historical price
calculation             = ₹42,393,185.70

October signed-off
revenue                 = ₹56,359,195.92
```

---

# 61. Final Conclusion

The implementation satisfies the six technical requirements:

```text
1. Land and partition raw sales data
2. Make ingestion idempotent
3. Build a dimensional analytical model
4. Apply historical prices temporally
5. Federate MinIO and PostgreSQL through DuckDB
6. Reconcile analytical revenue with Finance
```

The most important design decisions are:

```text
Store/year/month partitioning
        ↓
Business-key deduplication
        ↓
Temporal product identity
        ↓
Explicit line-type revenue logic
        ↓
Historical price temporal join
        ↓
Star schema
        ↓
Federated DuckDB SQL
        ↓
Finance reconciliation
```

The implementation should preserve source data rather than silently modifying
or inventing it, and business rules should be made explicit in SQL so the
results can be validated.

---

# 62. Final Remaining Action

Before submitting, capture the exact MinIO byte counts using the commands in
Section 11.

Do not invent byte counts.

All other major implementation results and query outputs are documented above.
