import json

# events_v2 - wrapped
d2 = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_events_v2.json', 'r', encoding='utf-8'))
e = d2[0].get('event', d2[0]) if isinstance(d2, list) else d2.get('event', d2)
print('=== EVENTS_V2[0] ALL KEYS ===')
for k in sorted(e.keys()):
    v = e[k]
    if isinstance(v, (dict, list)):
        print(f'  {k}: {type(v).__name__} ({len(v)} items)')
    else:
        print(f'  {k}: {repr(v)[:100]}')

print()
print('=== team_a keys ===')
ta = e.get('team_a', {})
if isinstance(ta, dict):
    for k in sorted(ta.keys()):
        v = ta[k]
        if isinstance(v, (dict, list)):
            print(f'  {k}: {type(v).__name__} ({len(v)} items)')
        else:
            print(f'  {k}: {repr(v)[:100]}')

print()
print('=== team_b keys ===')
tb = e.get('team_b', {})
if isinstance(tb, dict):
    for k in sorted(tb.keys()):
        v = tb[k]
        if isinstance(v, (dict, list)):
            print(f'  {k}: {type(v).__name__} ({len(v)} items)')
        else:
            print(f'  {k}: {repr(v)[:100]}')

print()
print('=== scores ===')
print(json.dumps(e.get('scores', {}), indent=2, ensure_ascii=False))

print()
print('=== game_state_key ===')
print(e.get('game_state_key'))
print('=== period ===')
print(e.get('period'))
print('=== score ===')
print(e.get('score'))

print()
print('=== goals count ===')
goals = e.get('goals', [])
print(f'{len(goals)} goals')
if goals:
    print(json.dumps(goals[0], indent=2, ensure_ascii=False)[:400])

print()
print('=== violations count ===')
violations = e.get('violations', [])
print(f'{len(violations)} violations')
if violations:
    print(json.dumps(violations[0], indent=2, ensure_ascii=False)[:400])
