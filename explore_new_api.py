
import httpx
import asyncio
import json

BASE_URL = "https://captain.sapimu.au/dramanova"
TOKEN = "5cf419a4c7fb1c8585314b9f797bf77e7b10a705f32c91aac65b901559780e12"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

async def explore():
    async with httpx.AsyncClient(timeout=30) as client:
        print("=== EXPLORING /api/v1/dramas ===")
        r = await client.get(f"{BASE_URL}/api/v1/dramas", headers=HEADERS, params={"lang": "in", "page": 1, "size": 5})
        dramas = r.json()
        print(json.dumps(dramas, indent=2)[:2000])
        
        if isinstance(dramas, list) and len(dramas) > 0:
            # Check structure of first drama
            drama_id = dramas[0].get("id") or dramas[0].get("dramaId")
            print(f"\n=== EXPLORING /api/v1/drama/{drama_id} ===")
            r = await client.get(f"{BASE_URL}/api/v1/drama/{drama_id}", headers=HEADERS, params={"lang": "in"})
            detail = r.json()
            print(json.dumps(detail, indent=2)[:3000])

if __name__ == "__main__":
    asyncio.run(explore())
