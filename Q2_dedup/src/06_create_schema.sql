CREATE TABLE IF NOT EXISTS notices (notice_id TEXT PRIMARY KEY, portal_id TEXT, published_at DATE, title TEXT, body TEXT, estimated_value NUMERIC, closing_date DATE, normalized_text TEXT);
CREATE TABLE IF NOT EXISTS minhash_signatures (notice_id TEXT PRIMARY KEY REFERENCES notices(notice_id), signature INTEGER[]);
CREATE TABLE IF NOT EXISTS lsh_buckets (band INTEGER NOT NULL, bucket_hash TEXT NOT NULL, notice_id TEXT NOT NULL REFERENCES notices(notice_id), PRIMARY KEY (band, bucket_hash, notice_id));
CREATE INDEX IF NOT EXISTS idx_lsh_lookup ON lsh_buckets (band, bucket_hash);
CREATE TABLE IF NOT EXISTS opportunities (opportunity_id UUID PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, canonical_notice_id TEXT);
CREATE TABLE IF NOT EXISTS opportunity_members (opportunity_id UUID REFERENCES opportunities(opportunity_id), notice_id TEXT REFERENCES notices(notice_id), first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (opportunity_id, notice_id));
