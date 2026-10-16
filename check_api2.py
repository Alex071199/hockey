import json

# teams_v2
d = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_teams_v2.json', 'r', encoding='utf-8'))
print('=== TEAMS_V2 type:', type(d).__name__)
if isinstance(d, dict):
    print('keys:', list(d.keys())[:10])
    if 'teams' in d:
        teams = d['teams']
        print(f'Teams count: {len(teams)}')
        if teams:
            t = teams[0]
            print('Team keys:', sorted(t.keys()))
            print('First team:', json.dumps(t, indent=2, ensure_ascii=False)[:500])
elif isinstance(d, list):
    print(f'Teams count: {len(d)}')
    if d:
        t = d[0]
        if isinstance(t, dict) and 'team' in t:
            t = t['team']
        print('Team keys:', sorted(t.keys()))
        print('First team:', json.dumps(t, indent=2, ensure_ascii=False)[:500])

print()
print('=' * 60)
print()

# events_v2
d2 = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_events_v2.json', 'r', encoding='utf-8'))
print('=== EVENTS_V2 type:', type(d2).__name__)
if isinstance(d2, dict):
    print('keys:', list(d2.keys())[:10])
    if 'events' in d2:
        events = d2['events']
        print(f'Events count: {len(events)}')
        if events:
            e = events[0]
            if isinstance(e, dict) and 'event' in e:
                e = e['event']
            print('Event keys:', sorted(e.keys())[:20])
            print('First event name:', e.get('name'))
            print('First event game_state_key:', e.get('game_state_key'))
            print('First event score:', e.get('score'))
elif isinstance(d2, list):
    print(f'Events count: {len(d2)}')
    if d2:
        e = d2[0]
        if isinstance(e, dict) and 'event' in e:
            e = e['event']
        print('Event keys:', sorted(e.keys())[:20])
        print('First event name:', e.get('name'))
