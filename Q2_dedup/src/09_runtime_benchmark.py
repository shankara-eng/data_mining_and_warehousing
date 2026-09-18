from pathlib import Path
import time,pandas as pd
DATA=Path('../data'); NOTICE_DIR=DATA/'notices'; t=time.perf_counter(); notices=pd.concat([pd.read_csv(f) for f in sorted(NOTICE_DIR.glob('*.csv'))],ignore_index=True); elapsed=time.perf_counter()-t
print(f'Notices: {len(notices)}'); print(f'Corpus loading time: {elapsed:.3f} seconds')
