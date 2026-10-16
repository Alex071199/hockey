import json, time, datetime

# Read the asc events we already fetched
d = json.load(open(r'C:\Users\kopys\AppData\Local\Temp\ev2_asc.json', 'r', encoding='utf-8'))
print(f"Total events: {len(d)}")
dates = {}
for item in d:
    e = item.get('event', item)
    ts = e.get('start_at', 0)
    if ts > 1e12:
        ts = ts // 1000
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    day = dt.strftime('%Y-%m-%d')
    state = e.get('game_state_key', '?')
    name = e.get('name', '?')
    score = e.get('score', '')
    if day not in dates:
        dates[day] = []
    dates[day].append(f"  {state:20s} {score:6s} {name}")

for day in sorted(dates.keys()):
    print(f"\n{day} ({len(dates[day])} events):")
    for line in dates[day]:
        print(line)
