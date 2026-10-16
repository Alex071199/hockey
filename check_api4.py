import json
import time

# events_v2 with stage_id=407
d = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_events_v2_s407.json', 'r', encoding='utf-8'))
print(f'Events with stage_id=407: {len(d)}')
for e in d[:5]:
    evt = e.get('event', e)
    print(f'  {evt.get("name")} | state={evt.get("game_state_key")} | score={evt.get("score")} | start={evt.get("start_at")} | stage={evt.get("stage_name")}')

# Show game_state_keys distribution
states = {}
for e in d:
    evt = e.get('event', e)
    s = evt.get('game_state_key', 'unknown')
    states[s] = states.get(s, 0) + 1
print(f'\nGame states: {states}')

# Get current time for filtering
now = int(time.time())
print(f'\nCurrent unix time: {now}')
print(f'Current time UTC: {time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}')
