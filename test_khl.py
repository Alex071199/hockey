import asyncio
import sys
sys.path.insert(0, r'C:\Users\kopys\Desktop\scrap — livetv\backend')
from app.khl_api import get_standings

data = asyncio.run(get_standings())
print('League:', data['league'])
print('Season:', data['season'])
print('Groups:', len(data['groups']))
for g in data['groups']:
    print(f'  {g["name"]}: {len(g["rows"])} teams')
    for r in g['rows'][:3]:
        print(f'    {r["position"]}. {r["team_name"]} - {r["points"]} pts ({r["wins"]}W {r["losses"]}L {r["played"]}GP)')
