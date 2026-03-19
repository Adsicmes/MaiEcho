from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from maiecho_py.internal.config.models import PromptConfig
from maiecho_py.internal.config.prompts import render_prompt
from maiecho_py.internal.llm.client import LLMClient


class BinaryDecision(BaseModel):
    decision: Literal["YES", "NO"]
    reason: str = ""


@dataclass(slots=True)
class RelevanceAnalyzer:
    llm: LLMClient
    prompts: PromptConfig

    _generic_aliases = {
        "dx",
        "sd",
        "std",
        "maimai",
        "舞萌",
        "新框",
        "旧框",
        "手元",
    }

    async def check_alias_suitability(
        self, title: str, artist: str | None, alias: str
    ) -> bool:
        normalized_alias = alias.strip().lower()
        if not normalized_alias:
            return False
        if normalized_alias in self._generic_aliases:
            return False
        if normalized_alias.isdigit():
            return False
        if len(alias.strip()) >= 5:
            return True
        system_prompt = self.prompts.agent.relevance.check_alias.system
        user_prompt = render_prompt(
            self.prompts.agent.relevance.check_alias.user,
            {"Title": title, "Artist": artist or "", "Alias": alias},
        )
        response = await self.llm.structured(system_prompt, user_prompt, BinaryDecision)
        return response.decision == "YES"

    async def check_title_relevance(
        self, title: str, artist: str | None, aliases: list[str], video_title: str
    ) -> bool:
        system_prompt = self.prompts.agent.relevance.check_title.system
        user_prompt = render_prompt(
            self.prompts.agent.relevance.check_title.user,
            {
                "Title": title,
                "Artist": artist or "",
                "Aliases": aliases,
                "VideoTitle": video_title,
            },
        )
        response = await self.llm.structured(system_prompt, user_prompt, BinaryDecision)
        return response.decision == "YES"
