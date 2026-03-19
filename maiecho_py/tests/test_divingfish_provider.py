from __future__ import annotations

import asyncio
import json

import httpx

from maiecho_py.internal.provider.divingfish.client import DivingFishClient


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chart_stats"):
            return httpx.Response(
                200,
                json={
                    "charts": {
                        "12345": [
                            {
                                "cnt": 77,
                                "diff": "14+",
                                "fit_diff": 14.7,
                                "avg": 99.1,
                                "avg_dx": 2345.0,
                                "std_dev": 0.31,
                            }
                        ]
                    }
                },
            )

        if request.url.path.endswith("/music_data"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "12345",
                        "title": "Test Song",
                        "type": "DX",
                        "ds": [3.0, 6.0, 10.2, 14.4],
                        "level": ["3", "6", "10+", "14+"],
                        "charts": [
                            {"notes": [10, 2, 1, 3, 1], "charter": "A"},
                            {"notes": [20, 4, 2, 6, 2], "charter": "B"},
                            {"notes": [40, 8, 4, 12, 4], "charter": "C"},
                            {"notes": [80, 16, 8, 24, 8], "charter": "D"},
                        ],
                        "basic_info": {
                            "artist": "Composer",
                            "genre": "POPS",
                            "bpm": 180,
                            "release_date": "2025-01-01",
                            "from": "PRISM",
                            "is_new": True,
                        },
                    },
                    {
                        "id": "10023",
                        "title": "Legacy Cover Id",
                        "type": "DX",
                        "ds": [12.3],
                        "level": ["12+"],
                        "charts": [{"notes": [1, 2, 3, 4, 5], "charter": "Legacy"}],
                        "basic_info": {
                            "artist": "Old",
                            "genre": "GAME",
                            "bpm": 150,
                            "release_date": "2020-01-01",
                            "from": "UNIVERSE",
                            "is_new": False,
                        },
                    },
                ],
            )

        raise AssertionError(f"unexpected path: {request.url.path}")

    return httpx.MockTransport(handler)


def test_fetch_songs_maps_chart_stats_and_cover_url() -> None:
    async def run() -> None:
        client = DivingFishClient(
            client=httpx.AsyncClient(
                base_url="https://www.diving-fish.com", transport=_mock_transport()
            )
        )

        songs = await client.fetch_songs()
        await client.close()

        assert len(songs) == 2
        song = songs[0]
        assert song.game_id == 12345
        assert song.title == "Test Song"
        assert song.cover_url == "https://www.diving-fish.com/covers/12345.png"
        assert len(song.charts) == 4
        assert song.charts[-1].difficulty == "Master"
        assert song.charts[-1].fit == 14.7
        assert song.charts[-1].sample_count == 77
        assert json.loads(song.charts[-1].notes or "[]") == [80, 16, 8, 24, 8]

        legacy_song = songs[1]
        assert legacy_song.cover_url == "https://www.diving-fish.com/covers/00023.png"

    asyncio.run(run())


def test_fetch_songs_raises_on_invalid_payload() -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"invalid": True})

        client = DivingFishClient(
            client=httpx.AsyncClient(
                base_url="https://www.diving-fish.com",
                transport=httpx.MockTransport(handler),
            )
        )

        try:
            raised = False
            try:
                await client.fetch_songs()
            except ValueError:
                raised = True
            assert raised
        finally:
            await client.close()

    asyncio.run(run())
