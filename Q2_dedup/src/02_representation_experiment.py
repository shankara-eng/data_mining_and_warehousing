from pathlib import Path
import re, unicodedata, pandas as pd
DATA=Path('../data'); NOTICE_DIR=DATA/'notices'
def raw_words(x): return re.findall(r'\b\w+\b',str(x).lower())
def clean_text(x):
 s=unicodedata.normalize('NFKC',str(x)).lower(); s=re.sub(r'national procurement aggregation service|state procurement cell',' ',s); s=re.sub(r'corrigendum',' ',s); s=re.sub(r'\b(?:tender|nit|ref(?:erence)?)[\s:/-]*[a-z0-9./_-]*\b',' ',s); s=re.sub(r'\b\d{1,4}[/-]\d{1,2}[/-]\d{2,4}\b',' ',s); s=re.sub(r'\b(?:rs|inr|rupees?)\.?\s*[\d,.\-]+(?:\s*(?:lakh|crore|cr))?\b',' ',s); s=re.sub(r'\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b',' ',s); return re.sub(r'\s+',' ',s).strip()
def cleaned_words(x): return re.findall(r'\b\w+\b',clean_text(x))
def shingles(t,n=3): return set(' '.join(t[i:i+n]) for i in range(len(t)-n+1))
def jac(a,b): a,b=set(a),set(b); return len(a&b)/len(a|b) if a|b else 1.0
def scores(a,b):
 aw,bw=raw_words(a),raw_words(b); ac,bc=cleaned_words(a),cleaned_words(b)
 return {'raw_words':jac(aw,bw),'cleaned_words':jac(ac,bc),'cleaned_3_shingles':jac(shingles(ac),shingles(bc))}
notices=pd.concat([pd.read_csv(f) for f in sorted(NOTICE_DIR.glob('*.csv'))],ignore_index=True).fillna(''); pairs=pd.read_csv(DATA/'labelled_pairs.csv').fillna(''); lookup=notices.set_index('notice_id'); rows=[]
for _,p in pairs.iterrows():
 a=f"{lookup.loc[p.notice_id_a,'title']} {lookup.loc[p.notice_id_a,'body']}"; b=f"{lookup.loc[p.notice_id_b,'title']} {lookup.loc[p.notice_id_b,'body']}"; r={'notice_id_a':p.notice_id_a,'notice_id_b':p.notice_id_b,'label':p.label}; r.update(scores(a,b)); rows.append(r)
out=pd.DataFrame(rows)
for c in ['raw_words','cleaned_words','cleaned_3_shingles']:
 print('\n'+c)
 for lab in ['same','different']:
  x=out.loc[out.label==lab,c]; print(f'  {lab:10s} median={x.median():.4f} mean={x.mean():.4f}')
print('\nEXAMPLE PAIRS')
for lab,a_id,b_id in [('SAME','N010018','N010020'),('DIFFERENT','N007876','N008565')]:
 r=scores(f"{lookup.loc[a_id,'title']} {lookup.loc[a_id,'body']}",f"{lookup.loc[b_id,'title']} {lookup.loc[b_id,'body']}"); print(f'{lab} {a_id} vs {b_id}:'); [print(f'  {k} {v:.4f}') for k,v in r.items()]
out.to_csv('../results/representation_scores.csv',index=False)
