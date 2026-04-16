
import asyncio
import os
import logging
from merge import merge_video

logging.basicConfig(level=logging.INFO)

async def test():
    video = r"c:\BOT FLAFORM\DramaNova V1 sapimu\downloads\Rahasia Keluarga\Rahasia Keluarga_ep001.mp4"
    sub = r"c:\BOT FLAFORM\DramaNova V1 sapimu\downloads\Rahasia Keluarga\subs\Rahasia Keluarga_ep001.srt"
    output = r"c:\BOT FLAFORM\DramaNova V1 sapimu\temp\test_hardsub_debug.mp4"
    
    if os.path.exists(output):
        os.remove(output)
        
    try:
        print(f"Testing merge for {video}")
        res = await merge_video(video, sub, output)
        print(f"Success! Output: {res}")
    except Exception as e:
        print(f"Failed with exception: {e}")

if __name__ == "__main__":
    asyncio.run(test())
