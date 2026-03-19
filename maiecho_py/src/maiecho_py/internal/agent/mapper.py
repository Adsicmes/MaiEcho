from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Sequence
from typing import NamedTuple

from maiecho_py.internal.config.models import PromptConfig
from maiecho_py.internal.config.prompts import render_prompt
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import Song
from maiecho_py.internal.storage import StorageRepository


@dataclass(slots=True)
class CommentMapper:
    storage: StorageRepository
    llm: LLMClient
    prompts: PromptConfig

    async def map_comments_to_songs(self) -> int:
        songs = self.storage.get_all_songs()
        comments = self.storage.get_unmapped_comments()
        updated = 0
        song_keywords = [(song, self._build_keywords(song)) for song in songs]

        for comment in comments:
            if comment.song_id is not None:
                continue
            candidate = await self._select_song_candidate(
                song_keywords,
                comment.source_title or "",
                comment.content,
            )
            if candidate is None:
                continue
            comment.song_id = candidate.song.id
            _ = self.storage.update_comment(comment)
            updated += 1
        return updated

    def _build_keywords(self, song: Song) -> list[str]:
        keywords = [song.title] + [alias.alias for alias in song.aliases if alias.alias]
        normalized_keywords: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            lowered = keyword.lower()
            if len(keyword) < 2 or lowered in seen:
                continue
            seen.add(lowered)
            normalized_keywords.append(keyword)
        return normalized_keywords

    async def _select_song_candidate(
        self,
        song_keywords: Sequence[tuple[Song, list[str]]],
        source_title: str,
        content: str,
    ) -> "SongCandidate | None":
        candidates: list[SongCandidate] = []
        for song, keywords in song_keywords:
            candidate = await self._match_song_candidate(
                song,
                keywords,
                source_title,
                content,
            )
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return None
        candidates.sort(key=lambda item: item.score, reverse=True)
        if len(candidates) >= 2 and candidates[0].score == candidates[1].score:
            return None
        return candidates[0]

    async def _match_song_candidate(
        self,
        song: Song,
        keywords: list[str],
        source_title: str,
        content: str,
    ) -> "SongCandidate | None":
        best_score = 0
        haystacks = f"{source_title}\n{content}".lower()
        for keyword in keywords:
            if not self._keyword_present(keyword, haystacks):
                continue
            score = self._keyword_score(keyword, song.title)
            if len(keyword) <= 4:
                verified = await self._verify_match(keyword, source_title, content)
                if not verified:
                    continue
                score += 1
            if score > best_score:
                best_score = score

        if best_score == 0:
            return None
        return SongCandidate(song=song, score=best_score)

    @staticmethod
    def _keyword_score(keyword: str, title: str) -> int:
        if keyword == title:
            return 4
        if len(keyword) >= 5:
            return 3
        if keyword.isascii() and keyword.isalnum():
            return 1
        return 2

    @staticmethod
    def _keyword_present(keyword: str, haystacks: str) -> bool:
        lowered = keyword.lower()
        if lowered not in haystacks:
            return False
        if keyword.isascii() and keyword.isalnum() and len(keyword) <= 4:
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])")
            return pattern.search(haystacks) is not None
        return True

    async def _verify_match(
        self, keyword: str, source_title: str, content: str
    ) -> bool:
        system_prompt = self.prompts.agent.mapper.verify_match.system
        user_prompt = render_prompt(
            self.prompts.agent.mapper.verify_match.user,
            {"Keyword": keyword, "SourceTitle": source_title, "Content": content},
        )
        response = await self.llm.chat(system_prompt, user_prompt)
        return "YES" in response.strip().upper()


class SongCandidate(NamedTuple):
    song: Song
    score: int
