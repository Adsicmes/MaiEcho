from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Collector(Protocol):
    source_name: str

    async def collect(self, keyword: str, song_id: int | None = None) -> None: ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class CollectionTask:
    keyword: str
    source: str = ""
    song_id: int | None = None
