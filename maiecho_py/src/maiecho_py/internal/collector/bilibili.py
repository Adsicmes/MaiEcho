from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from maiecho_py.internal.collector.base import Collector
from maiecho_py.internal.model import Comment, Song, Video
from maiecho_py.internal.storage import StorageRepository


class BilibiliCollector(Collector):
    source_name = "bilibili"

    def __init__(
        self,
        storage: StorageRepository,
        *,
        cookie: str = "",
        proxy: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://search.bilibili.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }
        if cookie:
            headers["Cookie"] = cookie
        self._storage = storage
        self._cookie = cookie
        self._client = client or httpx.AsyncClient(
            headers=headers,
            proxy=proxy,
            timeout=30.0,
        )
        self._is_banned = False
        self._last_error = ""
        self._ban_until: datetime | None = None

    async def collect(self, keyword: str, song_id: int | None = None) -> None:
        self._refresh_ban_state()
        if self._is_banned:
            raise RuntimeError(
                self._last_error or "collector is currently banned/rate-limited"
            )

        song = self._storage.get_song(song_id) if song_id is not None else None
        for page in range(1, 4):
            if self._is_banned:
                break
            response = await self._request_with_retry(
                "https://api.bilibili.com/x/web-interface/search/all/v2",
                params={"keyword": keyword, "page": page},
                referer=f"https://search.bilibili.com/all?keyword={keyword}",
            )
            payload = response.json()
            self._validate_api_payload(payload, response)
            self._last_error = ""
            videos = self._extract_videos(payload)
            if not videos:
                break
            for video in videos:
                source_title = self._clean_html(str(video.get("title", "")))
                if song is not None and not self._is_relevant(source_title, song):
                    continue
                bvid = str(video.get("bvid", ""))
                aid = int(video.get("id", 0))
                description = str(video.get("description", ""))
                author = str(video.get("author", ""))

                self._storage.create_comment(
                    Comment(
                        song_id=song_id,
                        source="Bilibili",
                        source_title=source_title,
                        external_id=bvid,
                        content=description or source_title,
                        author=author or None,
                        post_date=datetime.now(timezone.utc),
                        search_tag=keyword,
                    )
                )
                self._storage.create_video(
                    Video(
                        source="Bilibili",
                        external_id=bvid,
                        title=source_title,
                        description=description or None,
                        author=author or None,
                        url=f"https://www.bilibili.com/video/{bvid}",
                        publish_time=datetime.now(timezone.utc),
                    )
                )

                if aid > 0:
                    await self._collect_replies(aid, source_title, keyword, song_id)

            await asyncio.sleep(0.15)

    async def _collect_replies(
        self, aid: int, title: str, keyword: str, song_id: int | None
    ) -> None:
        response = await self._request_with_retry(
            "https://api.bilibili.com/x/v2/reply",
            params={"type": 1, "oid": aid, "sort": 1, "ps": 20},
            referer=f"https://www.bilibili.com/video/{aid}",
        )
        payload = response.json()
        self._validate_api_payload(payload, response)
        replies = payload.get("data", {}).get("replies", [])
        if not isinstance(replies, list):
            return
        for reply in replies:
            content = str(reply.get("content", {}).get("message", ""))
            if not content:
                continue
            external_id = str(reply.get("rpid", ""))
            author = str(reply.get("member", {}).get("uname", "")) or None
            ctime = reply.get("ctime")
            post_date = (
                datetime.fromtimestamp(int(ctime), tz=timezone.utc)
                if isinstance(ctime, (int, float))
                else datetime.now(timezone.utc)
            )
            self._storage.create_comment(
                Comment(
                    song_id=song_id,
                    source="Bilibili",
                    source_title=title,
                    external_id=external_id,
                    content=content,
                    author=author,
                    post_date=post_date,
                    search_tag=keyword,
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

    @staticmethod
    def _clean_html(content: str) -> str:
        return re.sub(r"<[^>]*>", "", content)

    @staticmethod
    def _is_relevant(video_title: str, song: Song) -> bool:
        lowered = video_title.lower()
        if song.title.lower() in lowered:
            return True
        return any(
            len(alias.alias) >= 2 and alias.alias.lower() in lowered
            for alias in song.aliases
        )

    async def _request_with_retry(
        self,
        url: str,
        *,
        params: dict[str, Any],
        referer: str,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.get(
                    url,
                    params=params,
                    headers=self._build_headers(referer),
                )
            except httpx.RequestError as exc:
                last_error = exc
                self._last_error = f"request-error: {exc}"
                await asyncio.sleep(0.4 * (attempt + 1))
                continue

            if response.status_code in {412, 403, 429}:
                self._mark_banned(response)
                response.raise_for_status()
            if response.status_code >= 500:
                last_error = httpx.HTTPStatusError(
                    "server error", request=response.request, response=response
                )
                self._last_error = f"server-error: status={response.status_code} url={response.request.url}"
                await asyncio.sleep(0.4 * (attempt + 1))
                continue

            response.raise_for_status()
            return response

        if last_error is not None:
            raise last_error
        raise RuntimeError("request failed without explicit error")

    def _build_headers(self, referer: str) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
        }
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    def _validate_api_payload(
        self, payload: dict[str, Any], response: httpx.Response
    ) -> None:
        code = payload.get("code", 0)
        if code in (None, 0):
            return
        message = str(payload.get("message", "unknown error"))
        if code == -352 or "风控" in message or "验证码" in message:
            self._mark_banned(response, message=message)
            raise RuntimeError(self._last_error)
        self._last_error = f"api-error: code={code} message={message}"
        raise RuntimeError(self._last_error)

    def health_snapshot(self) -> dict[str, str | bool]:
        self._refresh_ban_state()
        return {
            "source": self.source_name,
            "status": "banned" if self._is_banned else "healthy",
            "banned": self._is_banned,
            "last_error": self._last_error,
            "ban_until": self._ban_until.isoformat() if self._ban_until else "",
        }

    def _mark_banned(self, response: httpx.Response, message: str = "") -> None:
        self._is_banned = True
        retry_after = response.headers.get("Retry-After", "")
        cooldown_seconds = 0
        if retry_after.isdigit():
            cooldown_seconds = int(retry_after)
        elif response.status_code == 429:
            cooldown_seconds = 300
        else:
            cooldown_seconds = 900
        self._ban_until = datetime.now(timezone.utc) + timedelta(
            seconds=cooldown_seconds
        )
        suffix = f" message={message}" if message else ""
        self._last_error = f"rate-limited: status={response.status_code} url={response.request.url} cooldown={cooldown_seconds}s{suffix}"

    def _refresh_ban_state(self) -> None:
        if self._ban_until is None:
            return
        if datetime.now(timezone.utc) >= self._ban_until:
            self._is_banned = False
            self._ban_until = None

    async def close(self) -> None:
        await self._client.aclose()
