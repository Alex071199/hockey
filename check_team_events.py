import json

# Team events for team_id=26 (Lokomotiv)
d = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_team_events.json', 'r', encoding='utf-8'))
print(f'Team events: {len(d)}')
for item in d[:5]:
    e = item.get('event', item)
    print(f'  {e.get("name")} | state={e.get("game_state_key")} | score={e.get("score")} | start={e.get("start_at")} | stage_id={e.get("stage_id")}')

# stage_id=407 desc
d2 = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\khl_ev2_s407_desc.json', 'r', encoding='utf-8'))
print(f'\nStage 407 desc: {len(d2)}')
for item in d2[:3]:
    e = item.get('event', item)
    print(f'  {e.get("name")} | state={e.get("game_state_key")} | score={e.get("score")} | start={e.get("start_at")} | stage={e.get("stage_name")}')
