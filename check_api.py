import json

d = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_event_v2.json', 'r', encoding='utf-8'))
evt = d['event']

print('=== SCORES ===')
print(json.dumps(evt['scores'], indent=2, ensure_ascii=False))
print()

print('=== TEAM_A keys ===')
for k in sorted(evt['team_a'].keys()):
    v = evt['team_a'][k]
    if isinstance(v, (dict, list)):
        print(f'  {k}: {type(v).__name__} ({len(v)} items)')
    else:
        print(f'  {k}: {repr(v)[:100]}')
print()

print('=== TEAM_A stats ===')
for k in ['shots', 'ppg', 'shg', 'ppc', 'pim', 'gf']:
    print(f'  team_a.{k}: {evt["team_a"].get(k)}')
for k in ['shots', 'ppg', 'shg', 'ppc', 'pim', 'gf']:
    print(f'  team_b.{k}: {evt["team_b"].get(k)}')
print()

print('=== THIS PAIR STAT ===')
print(json.dumps(evt['this_pair_stat'], indent=2, ensure_ascii=False)[:1000])
print()

print('=== GOALS ===')
for g in evt['goals'][:5]:
    print(json.dumps(g, indent=2, ensure_ascii=False)[:400])
    print()

print('=== TEXT EVENTS (first 3) ===')
for t in evt.get('text_events', [])[:3]:
    print(json.dumps(t, indent=2, ensure_ascii=False)[:300])
    print()

print('=== VIOLATIONS (first 3) ===')
for v in evt.get('violations', [])[:3]:
    print(json.dumps(v, indent=2, ensure_ascii=False)[:300])
    print()

print('=== HIGHLIGHT ===')
print(json.dumps(evt['highlight'], indent=2, ensure_ascii=False)[:500])
print()

print('=== TEAM_A top_players ===')
for p in evt['team_a'].get('top_players', [])[:3]:
    print(json.dumps(p, indent=2, ensure_ascii=False)[:200])
