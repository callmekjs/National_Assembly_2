import json, glob

files = sorted(glob.glob('eval/results/results_*.json'))
latest = files[-1]
print('Latest:', latest)
prev_file = files[-2]
print('Previous:', prev_file)

with open(latest, encoding='utf-8') as f:
    data = json.load(f)
with open(prev_file, encoding='utf-8') as f:
    prev_data = json.load(f)

prev = {r['id']: r.get('grounding_level') for r in prev_data}
curr = {r['id']: r for r in data}

fulls = [r for r in data if r.get('grounding_level') == 'FULL']
parts = [r for r in data if r.get('grounding_level') == 'PARTIAL']
nones = [r for r in data if r.get('grounding_level') == 'NONE']
print(f'FULL={len(fulls)} PARTIAL={len(parts)} NONE={len(nones)} total={len(data)}')
print()

print('== 개선: 이전 NONE -> 현재 FULL/PARTIAL ==')
improved = []
for r in data:
    pid = prev.get(r['id'])
    cur = r.get('grounding_level')
    if pid == 'NONE' and cur in ('FULL', 'PARTIAL'):
        improved.append(r)
        print(f"  {r['id']}: NONE->{cur} cit={r.get('citation_count')} | {r['query'][:50]}")

print()
print('== 퇴행: 이전 FULL/PARTIAL -> 현재 NONE ==')
regressed = []
for r in data:
    pid = prev.get(r['id'])
    cur = r.get('grounding_level')
    if pid in ('FULL', 'PARTIAL') and cur == 'NONE':
        regressed.append(r)
        print(f"  {r['id']}: {pid}->NONE cit={r.get('citation_count')} | {r['query'][:50]}")

print()
print(f'개선: {len(improved)}건, 퇴행: {len(regressed)}건')
print(f'순증감: {len(improved) - len(regressed)}')
