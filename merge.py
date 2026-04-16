"""
DramaNova Bot — Merge / Processor (FINAL LOCKED 🔒)
Handles video merging with MANDATORY hardburn subtitles.
NOW ASYNCHRONOUS for non-blocking command execution.
"""
import os
import asyncio
import logging
from natsort import natsorted
from config import (
    CRF,
    PRESET,
    VIDEO_CODEC,
    AUDIO_CODEC,
    SUB_FONT,
    SUB_SIZE,
    SUB_COLOR,
    SUB_BOLD,
    SUB_OUTLINE,
    SUB_OUTLINE_COLOR,
    SUB_MARGIN_V,
    MERGE_DIR,
    TEMP_DIR,
)

log = logging.getLogger("dramanova.merge")


# ═══════════════════════════════════════════════════════════════
# 🚫 SUBTITLE VALIDATION (WAJIB)
# ═══════════════════════════════════════════════════════════════

def validate_subtitle(subtitle_file: str) -> None:
    if not subtitle_file:
        raise Exception("❌ Subtitle tidak ditemukan! Hardsub WAJIB.")
    if not os.path.exists(subtitle_file):
        raise Exception(f"❌ File subtitle tidak ada: {subtitle_file}")
    if os.path.getsize(subtitle_file) == 0:
        raise Exception(f"❌ File subtitle kosong: {subtitle_file}")


def get_subtitle_filter(sub_path: str) -> str:
    # On Windows, FFmpeg subtitles filter needs specific escaping:
    # 1. Backslashes must be forward slashes or escaped.
    # 2. Colons in drive letters (C:) must be escaped (C\:).
    # 3. The entire path must be wrapped in single quotes.
    escaped = sub_path.replace("\\", "/").replace(":", "\\:")
    
    if sub_path.lower().endswith(".ass"):
        return f"ass='{escaped}'"
    elif sub_path.lower().endswith((".srt", ".vtt")):
        style = (
            f"FontName={SUB_FONT},"
            f"FontSize={SUB_SIZE},"
            f"PrimaryColour={SUB_COLOR},"
            f"Bold={SUB_BOLD},"
            f"Outline={SUB_OUTLINE},"
            f"OutlineColour={SUB_OUTLINE_COLOR},"
            f"MarginV={SUB_MARGIN_V}"
        )
        return f"subtitles='{escaped}':force_style='{style}'"
    else:
        raise Exception(f"❌ Format subtitle tidak didukung: {sub_path}")


# ═══════════════════════════════════════════════════════════════
# 🎬 SINGLE VIDEO + HARDSUB (ASYNC)
# ═══════════════════════════════════════════════════════════════

async def merge_video(
    input_file: str, 
    subtitle_file: str, 
    output_file: str,
    progress_callback=None
) -> str:
    """Async merge using subprocess with progress parsing."""
    validate_subtitle(subtitle_file)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    sub_filter = get_subtitle_filter(subtitle_file)

    # Get duration for progress calculation
    duration = await get_video_duration(input_file)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-vf", sub_filter,
        "-c:v", VIDEO_CODEC,
        "-preset", PRESET,
        "-crf", str(CRF),
        "-c:a", AUDIO_CODEC,
        "-stats",  # Force stats output
        output_file,
    ]

    log.info(f"🎬 Merging: {os.path.basename(input_file)}...")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        import re
        # Example stats line: time=00:00:10.50
        time_regex = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

        async def read_stderr(stream):
            while True:
                line = await stream.readline()
                if not line: break
                line_str = line.decode('utf-8', errors='ignore')
                
                # Look for progress
                match = time_regex.search(line_str)
                if match and duration > 0:
                    h, m, s = map(float, match.groups())
                    current_time = h * 3600 + m * 60 + s
                    pct = min(100.0, (current_time / duration) * 100)
                    if progress_callback:
                        await progress_callback(pct)

        # Read stderr in background
        stderr_task = asyncio.create_task(read_stderr(process.stderr))
        await process.wait()
        await stderr_task

        if process.returncode != 0:
            log.error(f"❌ FFmpeg FAIL for {os.path.basename(input_file)}")
            raise Exception(f"FFmpeg failed with code {process.returncode}")
            
    except FileNotFoundError:
        log.error("❌ FFmpeg not found!")
        raise Exception("FFmpeg command not found.")
    except Exception as e:
        log.error(f"❌ Merge exception: {type(e).__name__} - {e}")
        raise

    return output_file


# ═══════════════════════════════════════════════════════════════
# 🎬 BATCH: MERGE ALL EPISODES (ASYNC)
# ═══════════════════════════════════════════════════════════════

async def merge_all_episodes(
    episodes: list[dict],
    drama_title: str,
    output_dir: str = MERGE_DIR,
    progress_callback=None,
) -> str:
    """Batch process all episodes asynchronously with progress."""
    if not episodes:
        raise Exception("❌ Tidak ada episode untuk diproses!")

    episodes = natsorted(episodes, key=lambda e: e.get("number", 0))
    safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in drama_title).strip()
    os.makedirs(output_dir, exist_ok=True)

    hardsubbed_files = []

    for ep in episodes:
        ep_num = ep["number"]
        video = ep["video_path"]
        sub = ep["subtitle_path"]

        temp_out = os.path.join(TEMP_DIR, f"{safe_title}_ep{ep_num:03d}_hardsub.mp4")

        try:
            # Wrap progress callback for specific episode
            async def _ep_progress(pct):
                if progress_callback:
                    await progress_callback(ep_num, pct)

            await merge_video(video, sub, temp_out, progress_callback=_ep_progress)
            hardsubbed_files.append(temp_out)
        except Exception as e:
            log.error(f"❌ Episode {ep_num} merge gagal: {e}")
            if os.path.exists(temp_out):
                os.remove(temp_out)

    if not hardsubbed_files:
        raise Exception("❌ Semua episode gagal di-merge!")

    # 🔗 Concatenate
    if len(hardsubbed_files) == 1:
        final_output = os.path.join(output_dir, f"{safe_title}_final.mp4")
        if os.path.exists(final_output):
            os.remove(final_output)
        os.rename(hardsubbed_files[0], final_output)
        return final_output

    concat_list = os.path.join(TEMP_DIR, f"{safe_title}_concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for fp in hardsubbed_files:
            safe_fp = fp.replace('\\', '/')
            f.write(f"file '{safe_fp}'\n")

    final_output = os.path.join(output_dir, f"{safe_title}_final.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", final_output]

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await process.communicate()

    # Cleanup
    for f in hardsubbed_files:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(concat_list): os.remove(concat_list)

    return final_output


# ═══════════════════════════════════════════════════════════════
# 🛠 METADATA HELPERS (ASYNC)
# ═══════════════════════════════════════════════════════════════

async def get_video_duration(filepath: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await process.communicate()
    try:
        return float(stdout.decode().strip())
    except:
        return 0.0


async def generate_thumbnail(video_path: str, output_path: str = None) -> str:
    if output_path is None:
        output_path = video_path.rsplit(".", 1)[0] + "_thumb.jpg"
    duration = await get_video_duration(video_path)
    timestamp = max(1, int(duration * 0.1))
    cmd = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path, "-vframes", "1", "-q:v", "2", output_path]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await process.communicate()
    return output_path
