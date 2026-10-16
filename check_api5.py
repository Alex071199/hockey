import json
import time

now = int(time.time())

# Default events (no params)
d = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_ev2_default.json', 'r', encoding='utf-8'))
print(f'Default events: {len(d)}')
for e in d[:5]:
    evt = e.get('event', e)
    start_ts = evt.get('start_at', 0) // 1000
    days_from_now = (start_ts - now) / 86400
    print(f'  {evt.get("name")} | state={evt.get("game_state_key")} | stage_id={evt.get("stage_id")} | start={evt.get("start_at")} ({days_from_now:+.1f}d)')

# Page 2
d2 = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_ev2_p2.json', 'r', encoding='utf-8'))
print(f'\nPage 2 events: {len(d2)}')
for e in d2[:5]:
    evt = e.get('event', e)
    start_ts = evt.get('start_at', 0) // 1000
    days_from_now = (start_ts - now) / 86400
    print(f'  {evt.get("name")} | state={evt.get("game_state_key")} | stage_id={evt.get("stage_id")} | start={evt.get("start_at")} ({days_from_now:+.1f}d)')

# Desc
d3 = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_ev2_desc.json', 'r', encoding='utf-8'))
print(f'\nDesc events: {len(d3)}')
for e in d3[:5]:
    evt = e.get('event', e)
    start_ts = evt.get('start_at', 0) // 1000
    days_from_now = (start_ts - now) / 86400
    print(f'  {evt.get("name")} | state={evt.get("game_state_key")} | stage_id={evt.get("stage_id")} | start={evt.get("start_at")} ({days_from_now:+.1f}d)')
