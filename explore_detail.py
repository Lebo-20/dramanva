
import httpx
import asyncio
import json

BASE_URL = "https://captain.sapimu.au/dramanova"
TOKEN = "5cf419a4c7fb1c8585314b9f797bf77e7b10a705f32c91aac65b901559780e12"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

async def explore():
    async with httpx.AsyncClient(timeout=30) as client:
        # Get first drama ID
        r = await client.get(f"{BASE_URL}/api/v1/dramas", headers=HEADERS, params={"lang": "in", "page": 1, "size": 1})
        dramas = r.json()
        drama_id = dramas["rows"][0]["id"]
        
        print(f"\n=== EXPLORING /api/v1/drama/{drama_id} ===")
        r = await client.get(f"{BASE_URL}/api/v1/drama/{drama_id}", headers=HEADERS, params={"lang": "in"})
        detail = r.json()
        print(json.dumps(detail, indent=2))

if __name__ == "__main__":
    asyncio.run(explore())
