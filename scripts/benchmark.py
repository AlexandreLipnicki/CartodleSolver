"""Compare indexed and reference algorithms on identical data, without writing games."""
import json
from collections import Counter
from pathlib import Path
import math
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.catalog import catalog,pokemon_cards,search_cards
from backend.app.engine import filter_cards,recommend,sample,outcome,norm
from backend.app.models import Clues


def measure(fn,repeats=7):
    samples=[]
    for _ in range(repeats):
        start=time.perf_counter();fn();samples.append((time.perf_counter()-start)*1000)
    return round(statistics.median(samples),3)


def reference_recommend(valid,attempts):
    tried={a['card_id'] for a in attempts}
    pool=sorted((c for c in valid if c['id'] not in tried),key=lambda c:c['id'])
    if len(valid)==1:return valid[0]
    if not pool:return None
    if not attempts:return next((c for c in pool if c['id']=='xy10-63'),None)
    targets=sample(sorted(valid,key=lambda c:c['id']),512)
    def score(g):
        counts=Counter(outcome(t,g) for t in targets)
        entropy=-sum(n/len(targets)*math.log2(n/len(targets)) for n in counts.values())
        return entropy,bool(g.get('image_url')),-len(g['name'])
    return max(sample(pool,160),key=score)


def run():
    start=time.perf_counter();by_id=catalog();cards=pokemon_cards()
    cold=round((time.perf_counter()-start)*1000,3)
    clues={f:{'color':'gray','arrow':'down' if f in ('pokedex','hp','set') else None}
           for f in ('pokedex','type','stage','hp','rarity','set','illustrator')}
    attempts=[{'card_id':'xy10-63','clues':Clues.model_validate(clues).model_dump()}]
    start=time.perf_counter();valid,unknown=filter_cards(cards,attempts,by_id)
    first=round((time.perf_counter()-start)*1000,3)
    assert (valid,unknown)==filter_cards(list(cards),attempts,by_id)
    assert recommend(valid,attempts)==reference_recommend(valid,attempts)
    def reference_search():
        return [c for c in cards if 'lucario' in norm(' '.join([c.get('name') or '',c['id'],c.get('set_name') or '',c['number']]))][:40]
    assert search_cards('Lucario')==reference_search()
    result={'pokemon':len(cards),'compatible':len(valid),'uncertain':len(unknown),
            'catalog_cold_ms':cold,'first_index_and_filter_ms':first,'repeats':7,
            'filter_reference_ms':measure(lambda:filter_cards(list(cards),attempts,by_id)),
            'filter_indexed_ms':measure(lambda:filter_cards(cards,attempts,by_id)),
            'recommend_reference_ms':measure(lambda:reference_recommend(valid,attempts)),
            'recommend_optimized_ms':measure(lambda:recommend(valid,attempts)),
            'search_reference_ms':measure(reference_search),
            'search_cached_ms':measure(lambda:search_cards('Lucario'))}
    for key in ('filter','recommend','search'):
        fast={'filter':'filter_indexed_ms','recommend':'recommend_optimized_ms','search':'search_cached_ms'}[key]
        result[key+'_speedup']=round(result[key+'_reference_ms']/max(result[fast],.001),2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':run()
