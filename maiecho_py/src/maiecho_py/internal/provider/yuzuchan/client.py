from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt


@dataclass(slots=True)
class AliasItem:
    song_id: int
    name: str
    aliases: list[str]


class YuzuChanClient:
    def __init__(
        self, proxy: str | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        self._client = client or httpx.AsyncClient(
            proxy=proxy,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True,
    )
    async def fetch_aliases(self) -> dict[int, list[str]]:
        response = await self._client.get(
            "https://www.yuzuchan.moe/api/maimaidx/maimaidxalias"
        )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content", []) if isinstance(payload, dict) else []
        grouped: defaultdict[int, list[str]] = defaultdict(list)
        for item in content:
            alias_item = self._map_alias_item(item)
            grouped[alias_item.song_id].extend(alias_item.aliases)
        return dict(grouped)

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True,
    )
    async def fetch_alias_by_song_id(self, song_id: int) -> AliasItem | None:
        response = await self._client.get(
            "https://www.yuzuchan.moe/api/maimaidx/getsongsalias",
            params={"song_id": song_id},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("YuzuChan 响应格式不正确")
        content = payload.get("content")
        if not isinstance(content, dict):
            return None
        return self._map_alias_item(content)

    @staticmethod
    def _map_alias_item(payload: dict[str, Any]) -> AliasItem:
        aliases_raw = payload.get("Alias", [])
        aliases = (
            [str(alias) for alias in aliases_raw]
            if isinstance(aliases_raw, list)
            else []
        )
        return AliasItem(
            song_id=int(payload.get("SongID", 0)),
            name=str(payload.get("Name", "")),
            aliases=aliases,
        )

    async def close(self) -> None:
        await self._client.aclose()
