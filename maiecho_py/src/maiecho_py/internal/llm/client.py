from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, TypeVar, cast

from openai import AsyncOpenAI
from pydantic import BaseModel

from maiecho_py.internal.config.models import LLMConfig

T = TypeVar("T", bound=BaseModel)
instructor = import_module("instructor")


@dataclass(slots=True)
class LLMClient:
    client: Any
    model: str

    @classmethod
    def from_config(cls, config: LLMConfig) -> "LLMClient":
        base_client = AsyncOpenAI(
            api_key=config.api_key or "placeholder", base_url=config.base_url
        )
        return cls(
            client=instructor.from_openai(base_client),
            model=config.model,
        )

    async def text(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if not response.choices or response.choices[0].message.content is None:
            raise ValueError("LLM 未返回有效内容")
        return cast(str, response.choices[0].message.content)

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        return await self.text(system_prompt, user_prompt)

    async def structured(
        self, system_prompt: str, user_prompt: str, model: type[T]
    ) -> T:
        response = await self.client.chat.completions.create(
            model=self.model,
            response_model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if not isinstance(response, model):
            raise ValueError("LLM 未返回符合 schema 的结构化结果")
        return response

    async def close(self) -> None:
        await self.client.client.close()
