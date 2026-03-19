from __future__ import annotations

from dataclasses import dataclass
import re

from openai import AsyncOpenAI

from maiecho_py.internal.config.models import LLMConfig


@dataclass(slots=True)
class LLMClient:
    client: AsyncOpenAI
    model: str

    @classmethod
    def from_config(cls, config: LLMConfig) -> "LLMClient":
        return cls(
            client=AsyncOpenAI(
                api_key=config.api_key or "placeholder", base_url=config.base_url
            ),
            model=config.model,
        )

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if not response.choices or response.choices[0].message.content is None:
            raise ValueError("LLM 未返回有效内容")
        return response.choices[0].message.content

    async def chat_with_reasoning(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[str, str]:
        full_response = await self.chat(system_prompt, user_prompt)
        match = re.search(r"<thinking>(.*?)</thinking>", full_response, re.S)
        if match is None:
            return full_response.strip(), ""
        reasoning = match.group(1).strip()
        content = re.sub(
            r"<thinking>.*?</thinking>", "", full_response, flags=re.S
        ).strip()
        return content, reasoning

    async def close(self) -> None:
        await self.client.close()
