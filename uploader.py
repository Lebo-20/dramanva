"""
DramaNova Bot — Uploader (Telegram Distributor)
Uploads merged+hardsubbed video to Telegram channel via Telethon.
"""
import os
import time
import logging
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
from config import CHANNEL_ID
from merge import generate_thumbnail, get_video_duration

log = logging.getLogger("dramanova.uploader")


class Uploader:
    """Telegram uploader with split messages (Detail + Video)."""

    def __init__(self, client: TelegramClient):
        self.client = client

    # ─── Validate before upload ──────────────────────────────
    @staticmethod
    def validate_before_upload(file_path: str) -> None:
        """Ensure the file exists and is not empty before uploading."""
        if not file_path:
            raise Exception("❌ File path kosong!")
        if not os.path.exists(file_path):
            raise Exception(f"❌ File tidak ditemukan: {file_path}")
        if os.path.getsize(file_path) == 0:
            raise Exception(f"❌ File kosong (0 bytes): {file_path}")

    # ─── 1. Send Details (Photo + Title + Synopsis) ─────────
    async def send_details(
        self,
        drama_info: dict,
        channel_id: int = CHANNEL_ID,
    ) -> None:
        """Send the poster image with title and synopsis."""
        poster_url = drama_info.get("cover")
        title = drama_info.get("title", "Unknown")
        synopsis = drama_info.get("synopsis", "")

        # Build caption
        caption = f"🎬 <b>{title}</b>\n\n"
        if synopsis:
            caption += f"📝 <b>Sinopsis:</b>\n{synopsis}"
        
        # Truncate for photo caption limit (1024)
        if len(caption) > 1024:
            caption = caption[:1021] + "..."

        try:
            log.info(f"🖼️  Sending details for: {title}")
            await self.client.send_file(
                entity=channel_id,
                file=poster_url,
                caption=caption,
                parse_mode="html"
            )
        except Exception as e:
            log.error(f"❌ Gagal mengirim detail: {e}")
            # If photo fails, send as text
            await self.client.send_message(channel_id, caption, parse_mode="html")

    # ─── 2. Upload Video (Video + Simple Caption) ──────────
    async def upload_video(
        self,
        file_path: str,
        drama_title: str,
        channel_id: int = CHANNEL_ID,
        progress_callback=None,
    ) -> None:
        """
        Upload the merged video file.
        """
        # Validate
        self.validate_before_upload(file_path)

        # Generate thumbnail
        thumb_path = None
        try:
            thumb_path = await generate_thumbnail(file_path)
            log.info(f"🖼️  Thumbnail generated: {thumb_path}")
        except Exception as e:
            log.warning(f"⚠️  Thumbnail generation failed: {e}")

        # Get video duration
        duration = int(await get_video_duration(file_path))

        # Build video attributes
        attributes = [
            DocumentAttributeVideo(
                duration=duration,
                w=1280,
                h=720,
                supports_streaming=True,
            )
        ]

        # Caption style: 📽️ Full Episode: Title
        caption = f"📽️ <b>Full Episode: {drama_title}</b>"

        file_size = os.path.getsize(file_path)
        log.info(f"📤 Uploading: {os.path.basename(file_path)} ({file_size / 1024 / 1024:.1f} MB)")

        start = time.time()

        async def _progress(current, total):
            if progress_callback:
                await progress_callback(current, total)

        try:
            await self.client.send_file(
                entity=channel_id,
                file=file_path,
                caption=caption,
                thumb=thumb_path,
                attributes=attributes,
                supports_streaming=True,
                progress_callback=_progress,
                parse_mode="html",
            )
            elapsed = time.time() - start
            log.info(f"✅ Upload selesai dalam {elapsed:.1f}s")

        except Exception as e:
            log.error(f"❌ Upload gagal: {e}")
            raise

        finally:
            # Cleanup thumbnail
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
