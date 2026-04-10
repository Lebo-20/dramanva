"""
DramaNova Bot — API Client (sansekai.my.id)
Senior Engineer Optimized Edition - Bypass 403 Forbidden.

Bypass Strategy:
1. Browser Mimicry (Chrome 120 headers)
2. Client Hints (Sec-Ch-Ua)
3. Connection Handling (Keep-alive + session)
4. Forced HTTP/1.1 (Avoid TLS/H2 fingerprint detection)
"""
import httpx
import logging
import asyncio
from typing import Optional
from config import BASE_URL

log = logging.getLogger("dramanova.api")


class DramaNovaAPI:
    """Advanced Async client for DramaNova API via sansekai."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        # Realistic Browser Headers (LOCKED STYLE)
        self._base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://api.sansekai.my.id/",
            "Origin": "https://api.sansekai.my.id",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1"
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Singleton pattern for the client.
        Enforces HTTP/1.1 to bypass advanced bot detection.
        """
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            self._client = httpx.AsyncClient(
                headers=self._base_headers,
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                http2=False, # HTTP/2 is often a trigger for bot detection in Python
                limits=limits,
                verify=True
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Core GET method with improved error logging."""
        client = await self._get_client()
        url = f"{BASE_URL}{path}"
        
        try:
            log.debug(f"API Request: {url} params={params}")
            resp = await client.get(url, params=params)
            
            if resp.status_code == 403:
                log.error("❌ 403 Forbidden — Server detected bot usage or IP is blacklisted.")
                log.debug(f"Response Headers: {resp.headers}")
                
            resp.raise_for_status()
            return resp.json()
            
        except httpx.HTTPStatusError as e:
            log.error(f"HTTP Status Error {e.response.status_code}: {e.response.text[:200]}")
            raise
        except Exception as e:
            log.error(f"API Request Exception: {e}")
            raise

    # ─── Public Endpoints ────────────────────────────────────

    async def get_home(self, page: int = 1) -> list:
        """Get homepage drama list (Latest)."""
        data = await self._get("/home", params={"page": page})
        return data.get("rows", [])

    async def get_drama18(self, page: int = 1) -> list:
        """Get drama 18+ list."""
        data = await self._get("/drama18", params={"page": page})
        return data.get("rows", [])

    async def search(self, query: str) -> list:
        """Search dramas by title."""
        data = await self._get("/search", params={"query": query})
        return data.get("rows", [])

    async def get_detail(self, drama_id: str) -> dict:
        """Get full drama detail (Episodes + Subtitles)."""
        data = await self._get("/detail", params={"dramaId": drama_id})
        return data.get("data", data)

    async def get_video_url(self, file_id: str) -> str:
        """Resolve fileId → direct MP4 download URL."""
        data = await self._get("/getvideo", params={"fileId": file_id})
        result = data.get("Result", data)
        play_list = result.get("PlayInfoList", [])

        if not play_list:
            raise Exception(f"No PlayInfoList for fileId={file_id}")

        # Favor 720p
        chosen = play_list[0]
        for item in play_list:
            if item.get("Definition") == "720p":
                chosen = item
                break

        url = chosen.get("MainPlayUrl") or chosen.get("BackupPlayUrl", "")
        if not url:
            raise Exception(f"No play URL found for fileId={file_id}")

        return url

    # ─── Data Extractors ──────────────────────────────────────

    @staticmethod
    def extract_drama_info(drama: dict) -> dict:
        return {
            "id": drama.get("dramaId", ""),
            "title": drama.get("title", "Unknown"),
            "cover": drama.get("posterImg") or drama.get("posterImgUrl", ""),
            "synopsis": drama.get("synopsis") or drama.get("description", ""),
            "total_episodes": drama.get("totalEpisodes", 0),
            "is_completed": str(drama.get("isCompleted")) == "1",
            "view_count": drama.get("viewCount", 0),
        }

    @staticmethod
    def extract_episode_info(episode: dict) -> dict:
        subtitle_url = ""
        tracks = episode.get("subtitleTracks", [])
        # Indonesian preference
        for track in tracks:
            if track.get("language") == "in":
                subtitle_url = track.get("label", "") or track.get("url", "")
                break
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
