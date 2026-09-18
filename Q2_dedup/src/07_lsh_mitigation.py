# Remove high-document-frequency shingles from the LSH retrieval representation; keep the full cleaned representation for exact verification.
from pathlib import Path
import hashlib,re,pandas as pd,numpy as np
from collections import Counter,defaultdict
DATA=Path('../data'); NOTICE_DIR=DATA/'notices'; K,BANDS,ROWS=256,32,8; DF_CUTOFF=.05
def clean(x):
 s=re.sub(r'national procurement aggregation service|state procurement cell|corrigendum',' ',str(x).lower()); s=re.sub(r'\b(?:tender|nit|ref(?:erence)?)[\s:/-]*[a-z0-9./_-]*\b',' ',s); s=re.sub(r'\b\d{1,4}[/-]\d{1,2}[/-]\d{2,4}\b',' ',s); return re.sub(r'\s+',' ',s).strip()
def sh(x):
 t=re.findall(r'\b\w+\b',clean(x)); return set(' '.join(t[i:i+3]) for i in range(len(t)-2))
def h(s,seed): return int.from_bytes(hashlib.blake2b(f'{seed}|{s}'.encode(),digest_size=8).digest(),'little')
def sig(s): return [min(h(x,i) for x in s) for i in range(K)] if s else [2**64-1]*K
notices=pd.concat([pd.read_csv(f) for f in sorted(NOTICE_DIR.glob('*.csv'))],ignore_index=True).fillna(''); print(f'Loaded {len(notices)} notices'); all_sh=[]; df=Counter()
for _,r in notices.iterrows(): s=sh(f"{r['title']} {r['body']}"); all_sh.append(s); df.update(s)
threshold=int(len(notices)*DF_CUTOFF); high={s for s,n in df.items() if n>threshold}; print(f'Total unique shingles: {len(df)}'); print(f'High-frequency shingles: {len(high)}'); print(f'DF threshold: {threshold} notices ({DF_CUTOFF:.0%})')
buckets=defaultdict(list); sigs={}; removed=[]
for r,s in zip(notices.itertuples(),all_sh):
 filtered=s-high; removed.append(len(s)-len(filtered)); sg=sig(filtered); sigs[r.notice_id]=sg
 for band in range(BANDS):
  raw=','.join(map(str,sg[band*ROWS:(band+1)*ROWS])); key=hashlib.blake2b(raw.encode(),digest_size=12).hexdigest(); buckets[(band,key)].append(r.notice_id)
cands={}
for nid,sg in sigs.items():
 c=set()
 for band in range(BANDS):
  raw=','.join(map(str,sg[band*ROWS:(band+1)*ROWS])); key=hashlib.blake2b(raw.encode(),digest_size=12).hexdigest(); c.update(buckets[(band,key)])
 c.discard(nid); cands[nid]=c
pairs=pd.read_csv(DATA/'labelled_pairs.csv').fillna(''); survive=true_survive=true_total=0
for _,p in pairs.iterrows():
 ok=p.notice_id_b in cands[p.notice_id_a] or p.notice_id_a in cands[p.notice_id_b]; survive+=int(ok)
 if p.label=='same': true_total+=1; true_survive+=int(ok)
sizes=np.array([len(x) for x in cands.values()]); print(f'Mitigated LSH buckets: {len(buckets)}'); print(f'Candidate survival: {survive/len(pairs):.4f}'); print(f'TRUE-DUPLICATE candidate survival: {true_survive/true_total:.3f}'); print(f'Median candidates/notice: {np.median(sizes):.0f}'); print(f'P95 candidates/notice: {np.quantile(sizes,.95):.0f}'); print(f'P99 candidates/notice: {np.quantile(sizes,.99):.0f}'); print(f'Maximum candidates/notice: {sizes.max():.0f}')
pd.DataFrame([{'df_cutoff':DF_CUTOFF,'df_threshold':threshold,'unique_shingles':len(df),'high_frequency_shingles':len(high),'avg_shingles_removed':np.mean(removed),'lsh_buckets':len(buckets),'candidate_survival':survive/len(pairs),'true_duplicate_survival':true_survive/true_total,'median_candidates':np.median(sizes),'p95_candidates':np.quantile(sizes,.95),'p99_candidates':np.quantile(sizes,.99),'max_candidates':sizes.max()}]).to_csv('../results/mitigation_results.csv',index=False)
pd.DataFrame({'notice_id':list(cands),'candidate_count':sizes}).to_csv('../results/mitigated_candidate_distribution.csv',index=False)
