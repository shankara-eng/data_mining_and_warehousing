from pathlib import Path
import hashlib,re,unicodedata,pandas as pd,numpy as np
DATA=Path('../data'); NOTICE_DIR=DATA/'notices'; K=256
def clean(x):
 s=unicodedata.normalize('NFKC',str(x)).lower(); s=re.sub(r'national procurement aggregation service|state procurement cell|corrigendum',' ',s); s=re.sub(r'\b(?:tender|nit|ref(?:erence)?)[\s:/-]*[a-z0-9./_-]*\b',' ',s); s=re.sub(r'\b\d{1,4}[/-]\d{1,2}[/-]\d{2,4}\b',' ',s); s=re.sub(r'\b(?:rs|inr|rupees?)\.?\s*[\d,.\-]+(?:\s*(?:lakh|crore|cr))?\b',' ',s); s=re.sub(r'\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b',' ',s); return re.sub(r'\s+',' ',s).strip()
def sh(x):
 t=re.findall(r'\b\w+\b',clean(x)); return set(' '.join(t[i:i+3]) for i in range(len(t)-2))
def h(s,seed): return int.from_bytes(hashlib.blake2b(f'{seed}|{s}'.encode(),digest_size=8).digest(),'little')
def sig(s): return np.array([min(h(x,i) for x in s) for i in range(K)],dtype=np.uint64) if s else np.full(K,2**64-1,dtype=np.uint64)
def jac(a,b): return len(a&b)/len(a|b) if a|b else 1.0
notices=pd.concat([pd.read_csv(f) for f in sorted(NOTICE_DIR.glob('*.csv'))],ignore_index=True).fillna(''); lookup=notices.set_index('notice_id'); pairs=pd.read_csv(DATA/'labelled_pairs.csv').fillna(''); rows=[]
for _,p in pairs.iterrows():
 a=f"{lookup.loc[p.notice_id_a,'title']} {lookup.loc[p.notice_id_a,'body']}"; b=f"{lookup.loc[p.notice_id_b,'title']} {lookup.loc[p.notice_id_b,'body']}"; sa,sb=sh(a),sh(b); exact=jac(sa,sb); est=float(np.mean(sig(sa)==sig(sb))); rows.append({'notice_id_a':p.notice_id_a,'notice_id_b':p.notice_id_b,'label':p.label,'exact':exact,'estimate':est,'abs_error':abs(exact-est)})
out=pd.DataFrame(rows); print(f'K = {K}'); print(f'Mean absolute error: {out.abs_error.mean():.5f}'); print(f'Median absolute error: {out.abs_error.median():.5f}'); print(f'95th percentile absolute error: {out.abs_error.quantile(.95):.5f}'); print(f'Maximum absolute error: {out.abs_error.max():.5f}')
for lab in ['different','same']:
 x=out[out.label==lab].abs_error; print(f'\n{lab} mean {x.mean():.6f} median {x.median():.6f} max {x.max():.6f}')
print('\nWORST 5:'); print(out.nlargest(5,'abs_error').to_string(index=False)); out.to_csv('../results/minhash_results.csv',index=False)
