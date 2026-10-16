import json

# Old events (non-v2) — what stage_ids are there?
d = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_events_full.json', 'r', encoding='utf-8'))
stages = {}
for item in d:
    e = item.get('event', item)
    sid = e.get('stage_id')
    sname = e.get('stage_name', '?')
    gsk = e.get('game_state', e.get('game_state_key', '?'))
    if sid not in stages:
        stages[sid] = {'name': sname, 'states': set(), 'count': 0}
    stages[sid]['states'].add(gsk)
    stages[sid]['count'] += 1

print('=== Stages in old events ===')
for sid, info in sorted(stages.items()):
    print(f'  stage_id={sid}: {info["name"]} | states={info["states"]} | count={info["count"]}')

# events_v2 default — what stage_ids?
d2 = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_ev2_default.json', 'r', encoding='utf-8'))
stages2 = {}
for item in d2:
    e = item.get('event', item)
    sid = e.get('stage_id')
    sname = e.get('stage_name', '?')
    gsk = e.get('game_state_key', '?')
    if sid not in stages2:
        stages2[sid] = {'name': sname, 'states': set(), 'count': 0}
    stages2[sid]['states'].add(gsk)
    stages2[sid]['count'] += 1

print('\n=== Stages in events_v2 default ===')
for sid, info in sorted(stages2.items()):
    print(f'  stage_id={sid}: {info["name"]} | states={info["states"]} | count={info["count"]}')

# Try other stage_ids
import subprocess
for sid in [406, 405, 404, 403, 408, 244, 235]:
    r = subprocess.run(
        ['C:\\Windows\\System32\\curl.exe', '-s', '-w', f'\\nHTTP %{{http_code}}',
         f'https://khl.api.webcaster.pro/api/khl_mobile/events_v2.json?stage_id={sid}'],
        capture_output=True, text=True, timeout=15
    )
    lines = r.stdout.strip().split('\n')
    http_code = lines[-1] if lines else '?'
    try:
        data = json.loads('\n'.join(lines[:-1]))
        count = len(data) if isinstance(data, list) else 0
        first_name = ''
        first_state = ''
        first_stage = ''
        if count > 0:
            e = data[0].get('event', data[0])
            first_name = e.get('name', '')
            first_state = e.get('game_state_key', '')
            first_stage = e.get('stage_name', '')
        print(f'  stage_id={sid}: HTTP {http_code} | {count} events | {first_state} | {first_stage} | {first_name}')
    except:
        print(f'  stage_id={sid}: HTTP {http_code} | parse error')
