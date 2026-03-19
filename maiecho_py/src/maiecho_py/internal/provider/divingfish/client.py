from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from maiecho_py.internal.model import Chart, Song


@dataclass(slots=True)
class ChartStat:
    count: float
    diff: str
    fit_diff: float
    avg: float
    avg_dx: float
    std_dev: float


class DivingFishClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str = "https://www.diving-fish.com",
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True,
    )
    async def fetch_songs(self) -> list[Song]:
        chart_stats = await self._fetch_chart_stats()
        response = await self._client.get("/api/maimaidxprober/music_data")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Diving-Fish music_data 响应格式不正确")
        return [self._map_song(item, chart_stats) for item in payload]

    async def _fetch_chart_stats(self) -> dict[str, list[ChartStat]]:
        response = await self._client.get("/api/maimaidxprober/chart_stats")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Diving-Fish chart_stats 响应格式不正确")

        charts = payload.get("charts", {})
        if not isinstance(charts, dict):
            return {}

        result: dict[str, list[ChartStat]] = {}
        for song_id, stats in charts.items():
            if not isinstance(song_id, str) or not isinstance(stats, list):
                continue
            result[song_id] = [self._map_chart_stat(item) for item in stats]
        return result

    @staticmethod
    def _map_chart_stat(payload: dict[str, Any]) -> ChartStat:
        return ChartStat(
            count=float(payload.get("cnt", 0)),
            diff=str(payload.get("diff", "")),
            fit_diff=float(payload.get("fit_diff", 0)),
            avg=float(payload.get("avg", 0)),
            avg_dx=float(payload.get("avg_dx", 0)),
            std_dev=float(payload.get("std_dev", 0)),
        )

    @classmethod
    def _map_song(
        cls, payload: dict[str, Any], chart_stats: dict[str, list[ChartStat]]
    ) -> Song:
        song_id = int(str(payload.get("id", "0")))
        basic_info = payload.get("basic_info", {})
        if not isinstance(basic_info, dict):
            raise ValueError("Diving-Fish basic_info 响应格式不正确")

        song = Song(
            game_id=song_id,
            title=str(payload.get("title", "")),
            type=str(payload.get("type", "")),
            artist=cls._optional_str(basic_info.get("artist")),
            genre=cls._optional_str(basic_info.get("genre")),
            bpm=cls._optional_float(basic_info.get("bpm")),
            release_date=cls._optional_str(basic_info.get("release_date")),
            version=cls._optional_str(basic_info.get("from")),
            is_new=bool(basic_info.get("is_new", False)),
            cover_url=cls._cover_url(song_id),
        )

        levels = payload.get("level", [])
        ds_values = payload.get("ds", [])
        charts = payload.get("charts", [])
        difficulties = ["Basic", "Advanced", "Expert", "Master", "Re:Master"]
        stats_for_song = chart_stats.get(str(song_id), [])

        if (
            not isinstance(levels, list)
            or not isinstance(ds_values, list)
            or not isinstance(charts, list)
        ):
            raise ValueError("Diving-Fish chart 数据格式不正确")

        for index, level in enumerate(levels):
            if (
                index >= len(difficulties)
                or index >= len(ds_values)
                or index >= len(charts)
            ):
                break

            chart_payload = charts[index]
            if not isinstance(chart_payload, dict):
                continue
            stat = cls._match_chart_stat(stats_for_song, str(level))
            notes_payload = chart_payload.get("notes", [])
            notes = json.dumps(notes_payload, ensure_ascii=False)

            song.charts.append(
                Chart(
                    difficulty=difficulties[index],
                    level=str(level),
                    ds=cls._optional_float(ds_values[index]),
                    fit=stat.fit_diff if stat is not None else 0.0,
                    notes=notes,
                    charter=cls._optional_str(chart_payload.get("charter")),
                    avg_achievement=stat.avg if stat is not None else 0.0,
                    avg_dx=stat.avg_dx if stat is not None else 0.0,
                    std_dev=stat.std_dev if stat is not None else 0.0,
                    sample_count=int(stat.count) if stat is not None else 0,
                )
            )

        return song

    @staticmethod
    def _match_chart_stat(
        stats_for_song: list[ChartStat], level: str
    ) -> ChartStat | None:
        for stat in stats_for_song:
            if stat.diff == level:
                return stat
        return None

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    @staticmethod
    def _cover_url(song_id: int) -> str:
        cover_id = song_id
        if 10000 < song_id <= 11000:
            cover_id -= 10000
        return f"https://www.diving-fish.com/covers/{cover_id:05d}.png"

    async def close(self) -> None:
        await self._client.aclose()
