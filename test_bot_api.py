
import asyncio
import logging
import sys
from api import DramaNovaAPI

# Configure logging to see API errors
logging.basicConfig(level=logging.DEBUG)

async def test():
    api = DramaNovaAPI()
    try:
        print("Testing get_home()...")
        dramas = await api.get_home(page=1)
        print(f"Success! Found {len(dramas)} dramas.")
        if dramas:
            print(f"First drama: {dramas[0].get('title')}")
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        await api.close()

if __name__ == "__main__":
    asyncio.run(test())
