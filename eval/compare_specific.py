import json, sys

f1 = 'eval/results/backend_fixes_eval_20260630_121731.json'
f2 = 'eval/results/results_20260630_141646.json'

with open(f1, encoding='utf-8') as f:
    prev_data = json.load(f)
with open(f2, encoding='utf-8') as f:
    curr_data = json.load(f)

prev = {r['id']: r for r in prev_data}
curr = {r['id']: r for r in curr_data}

improved = []
regressed = []
unchanged = []

for rid, cr in curr.items():
    pr = prev.get(rid)
    if not pr:
        continue
    p_level = pr.get('grounding_level')
    c_level = cr.get('grounding_level')
    if p_level == 'NONE' and c_level in ('FULL', 'PARTIAL'):
        improved.append((rid, p_level, c_level, cr.get('citation_count', 0), cr.get('query', '')[:50]))
    elif p_level in ('FULL', 'PARTIAL') and c_level == 'NONE':
        regressed.append((rid, p_level, c_level, cr.get('citation_count', 0), cr.get('query', '')[:50]))
    else:
        unchanged.append((rid, p_level, c_level))

print(f'기준: {f1}')
print(f'비교: {f2}')
pf = sum(1 for r in prev_data if r.get('grounding_level') == 'FULL')
pp = sum(1 for r in prev_data if r.get('grounding_level') == 'PARTIAL')
cf = sum(1 for r in curr_data if r.get('grounding_level') == 'FULL')
cp = sum(1 for r in curr_data if r.get('grounding_level') == 'PARTIAL')
print(f'기준: FULL={pf} PARTIAL={pp} => {pf+pp}/{len(prev_data)}')
print(f'현재: FULL={cf} PARTIAL={cp} => {cf+cp}/{len(curr_data)}')
print()
print(f'== 개선 ({len(improved)}건): 이전 NONE → 현재 FULL/PARTIAL ==')
for r in improved:
    print(f'  {r[0]}: {r[1]}->{r[2]} cit={r[3]} | {r[4]}')
print()
print(f'== 퇴행 ({len(regressed)}건): 이전 FULL/PARTIAL → 현재 NONE ==')
for r in regressed:
    print(f'  {r[0]}: {r[1]}->{r[2]} cit={r[3]} | {r[4]}')
print()
print(f'순증감: {len(improved)-len(regressed)}')
