from __future__ import annotations

from dataclasses import dataclass

from maiecho_py.internal.config.models import AppConfig
from maiecho_py.internal.provider.divingfish.client import DivingFishClient
from maiecho_py.internal.provider.yuzuchan.client import YuzuChanClient


@dataclass(slots=True)
class ProviderRegistry:
    divingfish: DivingFishClient
    yuzuchan: YuzuChanClient

    @classmethod
    def from_config(cls, config: AppConfig) -> "ProviderRegistry":
        return cls(
            divingfish=DivingFishClient(),
            yuzuchan=YuzuChanClient(proxy=config.bilibili.proxy or None),
        )

    async def close(self) -> None:
        await self.divingfish.close()
        await self.yuzuchan.close()
