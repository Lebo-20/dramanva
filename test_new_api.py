
import httpx
import asyncio
import json

BASE_URL = "https://captain.sapimu.au/dramanova"
TOKEN = "5cf419a4c7fb1c8585314b9f797bf77e7b10a705f32c91aac65b901559780e12"

async def test_api():
    async with httpx.AsyncClient(timeout=30) as client:
        # Try different ways to send token
        headers_list = [
            {"Authorization": f"Bearer {TOKEN}"},
            {"x-api-key": TOKEN},
            {"token": TOKEN},
            {"Authorization": TOKEN}
        ]
        
        for headers in headers_list:
            print(f"\nTesting with headers: {headers}")
            try:
                # Test languages endpoint as it's simple
                r = await client.get(f"{BASE_URL}/api/v1/languages", headers=headers)
                print(f"Status: {r.status_code}")
                if r.status_code == 200:
                    print(f"Success! Response: {r.text[:200]}")
                    return headers
                else:
                    print(f"Failed: {r.text[:200]}")
            except Exception as e:
                print(f"Error: {e}")
        
        # Try as param
        print("\nTesting as query param 'token'...")
        try:
            r = await client.get(f"{BASE_URL}/api/v1/languages", params={"token": TOKEN})
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                print(f"Success! Response: {r.text[:200]}")
                return "param"
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())
