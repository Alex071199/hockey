import json, subprocess, time, datetime

results = {}
for page in range(1, 12):
    r = subprocess.run(
        ['C:\\Windows\\System32\\curl.exe', '-s',
         f'https://khl.api.webcaster.pro/api/khl_mobile/events_v2.json?stage_id=407&order_direction=asc&page={page}'],
        capture_output=True, timeout=15
    )
    data = json.loads(r.stdout)
    if not data:
        print(f"Page {page}: empty -> stop")
        break
    for item in data:
        e = item.get('event', item)
        ts = e.get('start_at', 0)
        if ts > 1e12:
            ts = ts // 1000
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        day = dt.strftime('%Y-%m-%d')
        state = e.get('game_state_key', '?')
        name = e.get('name', '?')
        score = e.get('score', '')
        if day not in results:
            results[day] = []
        results[day].append(f"  {state:20s} {score:6s} {name}")
    print(f"Page {page}: {len(data)} events")
    time.sleep(0.3)

print(f"\nTotal dates: {len(results)}")
for day in sorted(results.keys()):
    print(f"\n{day} ({len(results[day])} events):")
    for line in results[day]:
        print(line)
