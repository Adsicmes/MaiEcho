from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from maiecho_py.internal.collector.base import Collector
from maiecho_py.internal.model import Comment, Video
from maiecho_py.internal.storage import StorageRepository


class BilibiliDiscoveryCollector(Collector):
    source_name = "bilibili_discovery"

    def __init__(
        self, storage: StorageRepository, client: httpx.AsyncClient | None = None
    ) -> None:
        self._storage = storage
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def collect(self, keyword: str, song_id: int | None = None) -> None:
        _ = song_id
        response = await self._client.get(
            "https://api.bilibili.com/x/web-interface/search/all/v2",
            params={"keyword": keyword, "order": "pubdate"},
        )
        response.raise_for_status()
        payload = response.json()
        for video in self._extract_videos(payload):
            bvid = str(video.get("bvid", ""))
            title = str(video.get("title", ""))
            description = str(video.get("description", ""))
            author = str(video.get("author", ""))
            now = datetime.now(timezone.utc)
            self._storage.create_comment(
                Comment(
                    source="Bilibili_Discovery",
                    source_title=title or None,
                    external_id=bvid,
                    content=description or title,
                    author=author or None,
                    post_date=now,
                    search_tag=keyword,
                )
            )
            self._storage.create_video(
                Video(
                    source="Bilibili_Discovery",
                    external_id=bvid,
                    title=title,
                    description=description or None,
                    author=author or None,
                    url=f"https://www.bilibili.com/video/{bvid}",
                    publish_time=now,
                )
            )

    @staticmethod
    def _extract_videos(payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = payload.get("data", {}).get("result", [])
        if not isinstance(results, list):
            return []
        for section in results:
            if isinstance(section, dict) and section.get("result_type") == "video":
                videos = section.get("data", [])
                return [item for item in videos if isinstance(item, dict)]
        return []

    async def close(self) -> None:
        await self._client.aclose()
