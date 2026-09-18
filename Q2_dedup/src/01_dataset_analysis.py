from pathlib import Path
import json, pandas as pd
DATA=Path('../data'); NOTICE_DIR=DATA/'notices'
files=sorted(NOTICE_DIR.glob('*.csv')); notices=pd.concat([pd.read_csv(f) for f in files],ignore_index=True)
pairs=pd.read_csv(DATA/'labelled_pairs.csv'); truth=json.loads((DATA/'_truth'/'truth.json').read_text())
print('NOTICE CORPUS'); print(f'Files: {len(files)}'); print(f'Notices: {len(notices)}'); print(f'Columns: {list(notices.columns)}')
print('\nLABELLED PAIRS'); print(f'Pair columns: {list(pairs.columns)}'); print(f'Pairs: {len(pairs)}'); print(pairs['label'].value_counts().to_string()); print(f"Labelled SAME rate: {(pairs['label']=='same').mean():.2f}")
print('\nTRUTH METADATA'); print(f"Expected notices: {truth.get('notices')}"); print(f"Opportunities: {truth.get('opportunities')}"); print(f"True duplicate pairs: {truth.get('true_duplicate_pairs')}"); print(f"Possible pairs: {truth.get('total_possible_pairs')}")
if truth.get('total_possible_pairs'): print(f"Corpus duplicate rate: {truth['true_duplicate_pairs']/truth['total_possible_pairs']}")
