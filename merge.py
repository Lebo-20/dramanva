"""
DramaNova Bot — Merge / Processor (FINAL LOCKED 🔒)
Handles video merging with MANDATORY hardburn subtitles.

🔒 ENCODING SETTINGS ARE LOCKED:
   CRF = 23, PRESET = ultrafast

🔒 SUBTITLE STYLE IS LOCKED:
   Font: Standard Symbols PS, Size: 10, Bold, White on Black outline

❌ HARD RULES:
   - No subtitle → PROCESS STOPS (exception raised)
   - No softsub allowed — EVER
   - No bypass of merge step
   - All output MUST be hardsubbed
"""
import os
import subprocess
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
# 🚫 SUBTITLE VALIDATION (WAJIB — NON-NEGOTIABLE)
# ═══════════════════════════════════════════════════════════════

def validate_subtitle(subtitle_file: str) -> None:
    """
    Validate that a subtitle file exists and is non-empty.
    Raises Exception if validation fails — this halts the entire process.
    """
    if not subtitle_file:
        raise Exception("❌ Subtitle tidak ditemukan! Hardsub WAJIB. Proses dihentikan.")
    if not os.path.exists(subtitle_file):
        raise Exception(f"❌ File subtitle tidak ada: {subtitle_file}. Hardsub WAJIB.")
    if os.path.getsize(subtitle_file) == 0:
        raise Exception(f"❌ File subtitle kosong: {subtitle_file}. Hardsub WAJIB.")
    log.info(f"✅ Subtitle valid: {subtitle_file}")


# ═══════════════════════════════════════════════════════════════
# 🔥 SUBTITLE FILTER (LOCKED STYLE)
# ═══════════════════════════════════════════════════════════════

def get_subtitle_filter(sub_path: str) -> str:
    """
    Build FFmpeg subtitle filter string.
    .ass files: use their own styling.
    .srt files: apply locked force_style.
    """
    # Escape backslashes and colons for FFmpeg filter syntax on Windows
    escaped = sub_path.replace("\\", "/").replace(":", "\\:")

    if sub_path.endswith(".ass"):
        return f"ass='{escaped}'"

    elif sub_path.endswith(".srt"):
        return (
            f"subtitles='{escaped}':force_style='"
            f"FontName={SUB_FONT},"
            f"FontSize={SUB_SIZE},"
            f"PrimaryColour={SUB_COLOR},"
            f"Bold={SUB_BOLD},"
            f"Outline={SUB_OUTLINE},"
            f"OutlineColour={SUB_OUTLINE_COLOR},"
            f"MarginV={SUB_MARGIN_V}'"
        )

    else:
        raise Exception(f"❌ Format subtitle tidak didukung: {sub_path}")


# ═══════════════════════════════════════════════════════════════
# 🎬 SINGLE VIDEO + HARDSUB MERGE
# ═══════════════════════════════════════════════════════════════

def merge_video(input_file: str, subtitle_file: str, output_file: str) -> str:
    """
    Merge a single video with hardburned subtitle.
    Returns path to output file.

    ❌ HARD RULES:
       - subtitle_file MUST exist → or exception
       - Output is ALWAYS hardsubbed
       - No softsub fallback
    """
    # 🚫 MANDATORY validation
    validate_subtitle(subtitle_file)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    sub_filter = get_subtitle_filter(subtitle_file)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-vf", sub_filter,
        "-c:v", VIDEO_CODEC,
        "-preset", PRESET,
        "-crf", str(CRF),
        "-c:a", AUDIO_CODEC,
        output_file,
    ]

    log.info(f"🎬 Merging: {os.path.basename(input_file)} + subtitle → {os.path.basename(output_file)}")
    log.debug(f"CMD: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log.error(f"❌ FFmpeg error:\n{result.stderr}")
        raise Exception(f"FFmpeg merge failed (code {result.returncode})")

    if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
        raise Exception(f"❌ Output file kosong/tidak ada: {output_file}")

    log.info(f"✅ Merge selesai: {output_file} ({os.path.getsize(output_file)} bytes)")
    return output_file


# ═══════════════════════════════════════════════════════════════
# 🎬 BATCH: MERGE ALL EPISODES → SINGLE FILE
# ═══════════════════════════════════════════════════════════════

def merge_all_episodes(
    episodes: list[dict],
    drama_title: str,
    output_dir: str = MERGE_DIR,
) -> str:
    """
    Process all episodes:
      1. Hardsub each episode individually
      2. Concatenate all hardsubbed videos into one file

    episodes: list of {number, video_path, subtitle_path}
    Returns path to final merged file.
    """
    if not episodes:
        raise Exception("❌ Tidak ada episode untuk diproses!")

    # Sort episodes naturally by number
    episodes = natsorted(episodes, key=lambda e: e.get("number", 0))

    safe_title = _sanitize(drama_title)
    os.makedirs(output_dir, exist_ok=True)

    hardsubbed_files = []

    # ─── Step 1: Hardsub each episode ────────────────────────
    for ep in episodes:
        ep_num = ep["number"]
        video = ep["video_path"]
        sub = ep["subtitle_path"]

        log.info(f"📝 Processing episode {ep_num}...")

        # ❌ CANNOT proceed without subtitle
        if not sub:
            log.error(f"❌ Episode {ep_num}: Subtitle TIDAK ADA → SKIP TOTAL")
            continue

        temp_out = os.path.join(TEMP_DIR, f"{safe_title}_ep{ep_num:03d}_hardsub.mp4")

        try:
            merge_video(video, sub, temp_out)
            hardsubbed_files.append(temp_out)
        except Exception as e:
            log.error(f"❌ Episode {ep_num} merge gagal: {e}")
            # Clean up failed temp file
            if os.path.exists(temp_out):
                os.remove(temp_out)

    if not hardsubbed_files:
        raise Exception("❌ Semua episode gagal di-merge! Tidak ada output.")

    # ─── Step 2: Concatenate if multiple episodes ────────────
    if len(hardsubbed_files) == 1:
        final_output = os.path.join(output_dir, f"{safe_title}_final.mp4")
        os.rename(hardsubbed_files[0], final_output)
        log.info(f"✅ Single episode → {final_output}")
        return final_output

    # Create concat list file
    concat_list = os.path.join(TEMP_DIR, f"{safe_title}_concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for fp in hardsubbed_files:
            escaped = fp.replace("\\", "/")
            f.write(f"file '{escaped}'\n")

    final_output = os.path.join(output_dir, f"{safe_title}_final.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        final_output,
    ]

    log.info(f"🔗 Concatenating {len(hardsubbed_files)} episodes...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log.error(f"❌ Concat error:\n{result.stderr}")
        raise Exception(f"FFmpeg concat failed (code {result.returncode})")

    # Cleanup temp hardsub files
    for f in hardsubbed_files:
        if os.path.exists(f):
            os.remove(f)
    if os.path.exists(concat_list):
        os.remove(concat_list)

    log.info(f"✅ Final merge selesai: {final_output} ({os.path.getsize(final_output)} bytes)")
    return final_output


# ═══════════════════════════════════════════════════════════════
# 🛠 Helpers
# ═══════════════════════════════════════════════════════════════

def _sanitize(name: str) -> str:
    """Sanitize filename."""
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()


def get_video_duration(filepath: str) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath,
            ],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def generate_thumbnail(video_path: str, output_path: str = None) -> str:
    """Extract a thumbnail frame from the video at 10% mark."""
    if output_path is None:
        output_path = video_path.rsplit(".", 1)[0] + "_thumb.jpg"

    duration = get_video_duration(video_path)
    timestamp = max(1, int(duration * 0.1))

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_path,
    ]

    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path
