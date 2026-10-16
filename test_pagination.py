import asyncio
import httpx
import json

async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        for page in range(2, 5):
            r = await c.get(
                'https://khl.api.webcaster.pro/api/khl_mobile/events_v2.json',
                params={'stage_id': '407', 'order_direction': 'asc', 'page': str(page)}
            )
            data = r.json()
            print(f'Page {page}: HTTP {r.status_code}, {len(data)} events')
            if data:
                e = data[0].get('event', data[0])
                print(f'  First: {e.get("name")} | {e.get("game_state_key")} | {e.get("start_at")}')
            if not data:
                break

asyncio.run(main())
