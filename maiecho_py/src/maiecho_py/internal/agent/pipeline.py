from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field
from maiecho_py.internal.config.models import PromptConfig
from maiecho_py.internal.config.prompts import render_prompt
from maiecho_py.internal.llm.client import LLMClient
from maiecho_py.internal.model import AnalysisResult, Chart, Song
from maiecho_py.internal.storage import StorageRepository


class CleanedComments(BaseModel):
    comments: list[str] = Field(default_factory=list)


class AnalystOutput(BaseModel):
    difficulty_tags: list[str] = Field(default_factory=list)
    key_patterns: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    sentiment: str = "Neutral"
    version_analysis: str = ""
    reasoning: str = ""


class AdvisorOutput(BaseModel):
    summary: str = ""
    rating_advice: str = ""
    difficulty_analysis: str = ""


@dataclass(slots=True)
class AnalysisPipeline:
    storage: StorageRepository
    llm: LLMClient
    prompts: PromptConfig

    _noise_keywords = {
        "拼车",
        "排队",
        "机况",
        "出勤",
        "打卡",
        "机器",
        "按键",
        "屏幕",
        "第一",
        "前排",
        "沙发",
        "围观",
        "吃瓜",
        "求好友",
        "互粉",
        "扩列",
        "不可发送单个标点符号",
        "258元回答你的问题",
    }
    _valid_short_terms = {
        "AP",
        "FC",
        "SSS",
        "SSS+",
        "FDX",
        "FDX+",
        "鸟",
        "鸟加",
        "全连",
        "收了",
        "理论值",
        "越级",
        "诈称",
        "逆诈称",
        "手癖",
        "局所难",
        "个人差",
    }
    _knowledge_terms = {
        "鸟": "SSS评价 (100.0000% - 100.4999%)",
        "鸟加": "SSS+评价 (100.5000%及以上)",
        "AP": "All Perfect (所有Note均为Perfect判定)",
        "FC": "Full Combo (全连)",
        "理论值": "101.0000% (所有Note均为Perfect，其中所有Break Note均为Critical判定)",
        "越级": "挑战超过自己当前水平的谱面",
        "诈称": "实际难度高于标定等级",
        "逆诈称": "实际难度低于标定等级",
        "手癖": "由于错误的肌肉记忆导致的习惯性失误",
        "纵连": "连续的纵向按键配置",
        "交互": "左右手交替点击",
        "海底潭": "指乐曲《海底潭》的红谱，以特定的配置闻名",
        "流星雨": "指乐曲《PANDORA PARADOXXX》中的一段密集Note下落",
        "转圈": "需要沿着屏幕边缘滑动的Slide或Tap配置",
        "蹭键": "利用判定区特性，用非正规的手法触发Note",
        "糊": "指玩家看不清谱面，乱拍",
        "底力": "玩家的基础实力（如读谱速度、手速、耐力）",
        "位移": "需要身体或手部大幅度移动的配置",
        "出张": "手部跨越到屏幕另一侧去处理Note",
    }
    _chunk_size = 50

    async def analyze_song(self, song_id: int) -> bool:
        song = self.storage.get_song(song_id)
        if song is None:
            raise ValueError(f"歌曲不存在: {song_id}")

        comments = self.storage.get_comments_by_song_id(song.id)
        if not comments:
            comments = self.storage.get_comments_by_keyword(song.title)
            for alias in song.aliases:
                comments.extend(self.storage.get_comments_by_keyword(alias.alias))

        prepared_comments = self._prepare_comments(comments)
        cleaned_comments = await self._clean_comments_with_llm(
            [comment for _, comment in prepared_comments]
        )
        if not cleaned_comments:
            return False

        chart_buckets = self._bucket_comments(song, prepared_comments)
        song_result = await self._run_song_analysis(song, cleaned_comments)
        self.storage.create_analysis_result(song_result)

        for chart_id, bucket_comments in chart_buckets.items():
            if not bucket_comments:
                continue
            chart = next((item for item in song.charts if item.id == chart_id), None)
            if chart is None:
                continue
            chart_result = await self._run_chart_analysis(song, bucket_comments, chart)
            chart_result.target_type = "chart"
            chart_result.target_id = chart.id
            self.storage.create_analysis_result(chart_result)

        return True

    async def _run_song_analysis(
        self, song: Song, comments: list[str]
    ) -> AnalysisResult:
        analyst_outputs: list[AnalystOutput] = []
        reasoning_logs: list[str] = []

        for start in range(0, len(comments), self._chunk_size):
            end = min(start + self._chunk_size, len(comments))
            chunk = comments[start:end]
            analyst_output = await self._run_analyst(song, chunk, None)
            analyst_outputs.append(analyst_output)
            if analyst_output.reasoning:
                reasoning_logs.append(
                    f"--- Chunk {start}-{end} Analysis ---\n{analyst_output.reasoning}"
                )

        if not analyst_outputs:
            raise ValueError("所有分析块均失败")

        merged_analyst = self._merge_analyst_outputs(analyst_outputs)
        advisor_output = await self._run_advisor(song, merged_analyst)
        return AnalysisResult(
            target_type="song",
            target_id=song.id,
            summary=self._optional_str(advisor_output.summary),
            rating_advice=self._optional_str(advisor_output.rating_advice),
            difficulty_analysis=self._optional_str(advisor_output.difficulty_analysis),
            reasoning_log="\n\n".join(reasoning_logs) or None,
            payload_json=json.dumps(
                {
                    "analyst": merged_analyst.model_dump(),
                    "advisor": advisor_output.model_dump(),
                    "chunk_count": len(analyst_outputs),
                },
                ensure_ascii=False,
            ),
        )

    async def _run_chart_analysis(
        self, song: Song, comments: list[str], chart: Chart
    ) -> AnalysisResult:
        analyst_output = await self._run_analyst(song, comments, chart)
        advisor_output = await self._run_advisor(song, analyst_output)
        return AnalysisResult(
            target_type="song",
            target_id=song.id,
            summary=self._optional_str(advisor_output.summary),
            rating_advice=self._optional_str(advisor_output.rating_advice),
            difficulty_analysis=self._optional_str(advisor_output.difficulty_analysis),
            reasoning_log=analyst_output.reasoning or None,
            payload_json=json.dumps(
                {
                    "analyst": analyst_output.model_dump(),
                    "advisor": advisor_output.model_dump(),
                },
                ensure_ascii=False,
            ),
        )

    async def _run_analyst(
        self, song: Song, comments: list[str], chart: Chart | None
    ) -> AnalystOutput:
        aliases = ", ".join(alias.alias for alias in song.aliases)
        chart_info = self._format_chart_info(
            [chart] if chart is not None else song.charts
        )
        term_guide = self._format_relevant_terms("\n".join(comments))
        analyst_system = render_prompt(
            self.prompts.agent.analyst.system,
            {"Aliases": aliases, "ChartInfo": chart_info},
        )
        if term_guide:
            analyst_system = f"{analyst_system}\n{term_guide}"
        analyst_user = render_prompt(
            self.prompts.agent.analyst.user,
            {"Comments": "\n".join(f"- {comment}" for comment in comments)},
        )
        return await self.llm.structured(
            analyst_system,
            analyst_user,
            AnalystOutput,
        )

    async def _run_advisor(
        self, song: Song, analyst_output: AnalystOutput
    ) -> AdvisorOutput:
        aliases = ", ".join(alias.alias for alias in song.aliases)
        advisor_system = render_prompt(
            self.prompts.agent.advisor.system,
            {"Title": song.title, "Artist": song.artist or "", "Aliases": aliases},
        )
        advisor_user = render_prompt(
            self.prompts.agent.advisor.user,
            {
                "AnalysisData": json.dumps(
                    analyst_output.model_dump(), ensure_ascii=False
                )
            },
        )
        return await self.llm.structured(advisor_system, advisor_user, AdvisorOutput)

    def _clean_comments(self, comments: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        html_tag = re.compile(r"<[^>]*>")
        for comment in comments:
            normalized = html_tag.sub("", comment)
            normalized = " ".join(normalized.split()).strip()
            if not normalized or normalized in seen:
                continue
            if any(keyword in normalized for keyword in self._noise_keywords):
                continue
            upper_content = normalized.upper()
            if len(normalized) < 5 and not any(
                term in upper_content or term in normalized
                for term in self._valid_short_terms
            ):
                continue
            cleaned.append(normalized)
            seen.add(normalized)
        return cleaned

    async def _clean_comments_with_llm(self, comments: list[str]) -> list[str]:
        cleaned = self._clean_comments(comments)
        if not cleaned:
            return []
        system_prompt = self.prompts.agent.cleaner.system
        user_prompt = render_prompt(
            self.prompts.agent.cleaner.user,
            {
                "Comments": "\n".join(
                    f"{index + 1}. {comment}" for index, comment in enumerate(cleaned)
                )
            },
        )
        try:
            response = await self.llm.structured(
                system_prompt, user_prompt, CleanedComments
            )
            if response.comments:
                return [item for item in response.comments if item.strip()]
        except Exception:
            return cleaned
        return cleaned

    def _prepare_comments(self, comments: Sequence[object]) -> list[tuple[str, str]]:
        prepared: list[tuple[str, str]] = []
        seen: set[str] = set()
        for comment in comments:
            source_title = getattr(comment, "source_title", "") or ""
            if not self._is_official_chart(source_title):
                continue
            content = getattr(comment, "content", "") or ""
            cleaned = self._clean_comments([content])
            if not cleaned:
                continue
            if cleaned[0] in seen:
                continue
            seen.add(cleaned[0])
            prepared.append((source_title, f"[{source_title}] {cleaned[0]}"))
        return prepared

    def _bucket_comments(
        self, song: Song, comments: Sequence[tuple[str, str]]
    ) -> dict[int, list[str]]:
        buckets: dict[int, list[str]] = {}
        for chart in song.charts:
            buckets[chart.id] = []
        for source_title, content in comments:
            chart_context = self._parse_chart_context(source_title)
            matched_chart = self._match_chart(song, chart_context)
            if matched_chart is None:
                continue
            buckets.setdefault(matched_chart.id, []).append(content)
        return buckets

    @staticmethod
    def _match_chart(song: Song, chart_context: tuple[str, str]) -> Chart | None:
        version, difficulty = chart_context
        if not difficulty:
            return None
        for chart in song.charts:
            if chart.difficulty != difficulty:
                continue
            if version == "DX" and song.type == "SD":
                continue
            if version == "Std" and song.type == "DX":
                continue
            return chart
        return None

    @staticmethod
    def _parse_chart_context(title: str) -> tuple[str, str]:
        lowered = title.lower()
        version = ""
        difficulty = ""
        if any(token in lowered for token in ["dx", "deluxe", "2p", "でらっくす"]):
            version = "DX"
        elif any(token in lowered for token in ["std", "standard", "标准", "标準"]):
            version = "Std"

        if any(token in lowered for token in ["basic"]) or "绿" in title:
            difficulty = "Basic"
        elif any(token in lowered for token in ["advanced"]) or "黄" in title:
            difficulty = "Advanced"
        elif "expert" in lowered or "红" in title:
            difficulty = "Expert"
        elif (
            any(token in lowered for token in ["re:master", "remaster"])
            or "白" in title
        ):
            difficulty = "Re:Master"
        elif any(token in lowered for token in ["master"]) or any(
            token in title for token in ["紫", "13+", "14", "14+", "15"]
        ):
            difficulty = "Master"
        return version, difficulty

    @staticmethod
    def _is_official_chart(title: str) -> bool:
        lowered = title.lower()
        return not any(
            token in lowered
            for token in [
                "自制",
                "自作",
                "ugc",
                "宴",
                "world's end",
                "we",
                "改谱",
                "fanmade",
            ]
        )

    @staticmethod
    def _format_chart_info(charts: list[Chart]) -> str:
        infos: list[str] = []
        for chart in charts:
            if chart is None:
                continue
            fit = chart.fit or 0.0
            ds = chart.ds or 0.0
            diff = fit - ds
            infos.append(
                f"[{chart.difficulty}] DS: {ds:.1f}, Fit: {fit:.2f} (Diff: {diff:+.2f})"
            )
        return "; ".join(infos) if infos else "暂无高难度谱面数据"

    def _format_relevant_terms(self, content: str) -> str:
        matched: list[str] = []
        for term, explanation in self._knowledge_terms.items():
            if term in content:
                matched.append(f"- {term}: {explanation}")
        if not matched:
            return ""
        return f"{self.prompts.agent.knowledge.guide_header}{chr(10).join(matched)}"

    @staticmethod
    def _merge_analyst_outputs(outputs: list[AnalystOutput]) -> AnalystOutput:
        merged = AnalystOutput()
        for key in ["difficulty_tags", "key_patterns", "pros", "cons"]:
            seen: set[str] = set()
            values: list[str] = []
            for output in outputs:
                raw = getattr(output, key)
                for item in raw:
                    item_str = str(item)
                    if item_str in seen:
                        continue
                    seen.add(item_str)
                    values.append(item_str)
            setattr(merged, key, values)

        sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
        for output in outputs:
            sentiment = output.sentiment
            if sentiment in sentiment_counts:
                sentiment_counts[sentiment] += 1
        merged.sentiment = max(
            sentiment_counts.items(), key=lambda item: (item[1], item[0] != "Neutral")
        )[0]

        version_analyses = [
            str(output.version_analysis)
            for output in outputs
            if output.version_analysis
        ]
        merged.version_analysis = "\n".join(version_analyses)
        return merged

    @staticmethod
    def _optional_str(value: object) -> str | None:
        if value is None:
            return None
        return str(value)
