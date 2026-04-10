"""
DramaNova Bot — API Client (sansekai.my.id)
No authentication needed.

Endpoints:
  GET /home?page=1           → Homepage drama list
  GET /drama18?page=1        → Drama 18+
  GET /search?query=xxx      → Search by title
  GET /detail?dramaId=xxx    → Detail + episodes + subtitles + fileIds
  GET /getvideo?fileId=xxx   → Video play info (direct MP4 URLs)
"""
import httpx
import logging
from typing import Optional
from config import BASE_URL

log = logging.getLogger("dramanova.api")


class DramaNovaAPI:
    """Async client for DramaNova API via sansekai."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "accept": "*/*",
                }
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        client = await self._get_client()
        url = f"{BASE_URL}{path}"
        log.debug(f"GET {url} params={params}")
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    # ─── Home (Latest Dramas) ────────────────────────────────
    async def get_home(self, page: int = 1) -> list:
        """Get homepage drama list."""
        data = await self._get("/home", params={"page": page})
        return data.get("rows", [])

    # ─── Drama 18+ ───────────────────────────────────────────
    async def get_drama18(self, page: int = 1) -> list:
        """Get drama 18+ list."""
        data = await self._get("/drama18", params={"page": page})
        return data.get("rows", [])

    # ─── Search ──────────────────────────────────────────────
    async def search(self, query: str) -> list:
        """Search dramas by title."""
        data = await self._get("/search", params={"query": query})
        return data.get("rows", [])

    # ─── Detail (includes episodes + subtitles + fileIds) ────
    async def get_detail(self, drama_id: str) -> dict:
        """
        Get full drama detail.
        Response includes:
          - title, synopsis, posterImg, totalEpisodes
          - episodes[] with fileId, subtitleTracks[], episodeNumber
        """
        data = await self._get("/detail", params={"dramaId": drama_id})
        return data.get("data", data)

    # ─── Get Video URL ───────────────────────────────────────
    async def get_video_url(self, file_id: str) -> str:
        """
        Get direct MP4 download URL from fileId.
        Picks the best quality available (720p preferred).
        """
        data = await self._get("/getvideo", params={"fileId": file_id})

        # Navigate: Result → PlayInfoList → pick best
        result = data.get("Result", data)
        play_list = result.get("PlayInfoList", [])

        if not play_list:
            raise Exception(f"No PlayInfoList for fileId={file_id}")

        # Prefer 720p, fallback to first available
        chosen = play_list[0]
        for item in play_list:
            if item.get("Definition") == "720p":
                chosen = item
                break

        url = chosen.get("MainPlayUrl") or chosen.get("BackupPlayUrl", "")
        if not url:
            raise Exception(f"No play URL for fileId={file_id}")

        return url

    # ─── Extract drama info ──────────────────────────────────
    @staticmethod
    def extract_drama_info(drama: dict) -> dict:
        """Extract standardised info from a drama object."""
        return {
            "id": drama.get("dramaId", ""),
            "title": drama.get("title", "Unknown"),
            "cover": drama.get("posterImg") or drama.get("posterImgUrl", ""),
            "synopsis": drama.get("synopsis") or drama.get("description", ""),
            "total_episodes": drama.get("totalEpisodes", 0),
            "is_completed": drama.get("isCompleted") == "1",
            "view_count": drama.get("viewCount", 0),
        }

    # ─── Extract episode info ────────────────────────────────
    @staticmethod
    def extract_episode_info(episode: dict) -> dict:
        """
        Extract standardised info from an episode object.
        Subtitle URL is in subtitleTracks[].label (for lang=in).
        """
        # Find Indonesian subtitle
        subtitle_url = ""
        tracks = episode.get("subtitleTracks", [])
        for track in tracks:
            if track.get("language") == "in":
                subtitle_url = track.get("label", "") or track.get("url", "")
                break
        # Fallback: take any subtitle
        if not subtitle_url and tracks:
            subtitle_url = tracks[0].get("label", "") or tracks[0].get("url", "")

        return {
            "id": episode.get("id", ""),
            "number": episode.get("episodeNumber", 0),
            "title": episode.get("episodeTitle", ""),
            "file_id": episode.get("fileId", ""),
            "subtitle": subtitle_url,
            "duration": episode.get("previewDuration", 0),
        }
