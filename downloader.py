"""
DramaNova Bot — Downloader (Async Worker)
Downloads video (via getvideo URL) & subtitle files.
Retry, semaphore limiting, validation.
"""
import os
import asyncio
import logging
import httpx
from typing import Optional
from config import (
    DOWNLOAD_DIR,
    MAX_CONCURRENT_DOWNLOADS,
    DOWNLOAD_TIMEOUT,
    MAX_RETRIES,
)
from api import DramaNovaAPI

log = logging.getLogger("dramanova.downloader")


class Downloader:
    """Async download worker with retry + concurrency control."""

    def __init__(self, api: DramaNovaAPI, max_concurrent: int = MAX_CONCURRENT_DOWNLOADS):
        self._sem = asyncio.Semaphore(max_concurrent)
        self._client: Optional[httpx.AsyncClient] = None
        self.api = api

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(DOWNLOAD_TIMEOUT, connect=30.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ─── Download single file ────────────────────────────────
    async def download_file(
        self,
        url: str,
        dest_path: str,
        retries: int = MAX_RETRIES,
        progress_callback=None,
    ) -> str:
        """Download a file from url to dest_path. Returns dest_path on success."""
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        for attempt in range(1, retries + 1):
            try:
                async with self._sem:
                    log.info(f"Download (attempt {attempt}/{retries}): {os.path.basename(dest_path)}")
                    client = await self._get_client()

                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        total = int(resp.headers.get("content-length", 0))
                        downloaded = 0

                        with open(dest_path, "wb") as f:
                            async for chunk in resp.aiter_bytes(chunk_size=65536):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_callback and total:
                                    await progress_callback(downloaded, total)

                if not self._validate(dest_path):
                    raise Exception(f"Validation failed for {dest_path}")

                log.info(f"Downloaded: {os.path.basename(dest_path)} ({os.path.getsize(dest_path)} bytes)")
                return dest_path

            except Exception as e:
                log.warning(f"Attempt {attempt}/{retries} failed: {e}")
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                if attempt == retries:
                    log.error(f"All {retries} attempts failed for {os.path.basename(dest_path)}")
                    raise
                await asyncio.sleep(2 ** attempt)

    # ─── Download video via getvideo endpoint ────────────────
    async def download_video(
        self,
        file_id: str,
        episode_num: int,
        drama_title: str,
        progress_callback=None,
    ) -> str:
        """
        Resolve file_id → direct MP4 URL via API, then download.
        Returns path to saved video file.
        """
        # Get direct URL from getvideo endpoint
        video_url = await self.api.get_video_url(file_id)

        safe_title = self._sanitize(drama_title)
        filename = f"{safe_title}_ep{episode_num:03d}.mp4"
        dest = os.path.join(DOWNLOAD_DIR, safe_title, filename)
        return await self.download_file(video_url, dest, progress_callback=progress_callback)

    # ─── Download subtitle ───────────────────────────────────
    async def download_subtitle(
        self,
        sub_url: str,
        episode_num: int,
        drama_title: str,
    ) -> str:
        """Download subtitle file. Returns path to saved file."""
        safe_title = self._sanitize(drama_title)
        ext = ".srt"
        if ".ass" in sub_url.lower():
            ext = ".ass"
        elif ".vtt" in sub_url.lower():
            ext = ".vtt"
        filename = f"{safe_title}_ep{episode_num:03d}{ext}"
        dest = os.path.join(DOWNLOAD_DIR, safe_title, "subs", filename)
        return await self.download_file(sub_url, dest)

    # ─── Batch download episodes ─────────────────────────────
    async def download_all_episodes(
        self,
        episodes: list[dict],
        drama_title: str,
        progress_callback=None,
    ) -> list[dict]:
        """
        Download all episodes (video + subtitle).
        Returns list of dicts: {number, video_path, subtitle_path}
        HARD RULE: Skips episodes without subtitle.
        """
        results = []

        for ep in episodes:
            ep_num = ep.get("number", 0)
            file_id = ep.get("file_id", "")
            sub_url = ep.get("subtitle", "")

            if not sub_url:
                log.warning(f"Episode {ep_num}: Subtitle tidak tersedia -> SKIP")
                continue

            if not file_id:
                log.warning(f"Episode {ep_num}: No file_id -> SKIP")
                continue

            try:
                # Wrap progress callback to include ep number
                async def _progress(cur, tot):
                    if progress_callback:
                        pct = (cur / tot) * 100
                        await progress_callback(ep_num, pct)

                video_path = await self.download_video(
                    file_id, ep_num, drama_title, progress_callback=_progress
                )
                sub_path = await self.download_subtitle(sub_url, ep_num, drama_title)

                results.append({
                    "number": ep_num,
                    "video_path": video_path,
                    "subtitle_path": sub_path,
                })
            except Exception as e:
                log.error(f"Episode {ep_num} download failed: {e}")

        return results

    @staticmethod
    def _validate(filepath: str) -> bool:
        return os.path.exists(filepath) and os.path.getsize(filepath) > 0

    @staticmethod
    def _sanitize(name: str) -> str:
        return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()
