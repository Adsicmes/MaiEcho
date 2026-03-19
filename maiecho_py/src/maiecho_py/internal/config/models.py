from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogConfig(BaseModel):
    level: str = "INFO"
    output_path: str = "logs/maiecho.log"
    encoding: str = "console"
    llm_log_path: str = "logs/llm_conversations.log"


class LLMConfig(BaseModel):
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"


class BilibiliConfig(BaseModel):
    cookie: str = ""
    proxy: str = ""


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    server_port: str = ":8080"
    database_url: str = "./sqlite_db/maiecho.db"
    log: LogConfig = Field(default_factory=LogConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    bilibili: BilibiliConfig = Field(default_factory=BilibiliConfig)


class PromptPair(BaseModel):
    system: str
    user: str


class MapperPrompts(BaseModel):
    verify_match: PromptPair


class RelevancePrompts(BaseModel):
    check_alias: PromptPair
    check_title: PromptPair


class KnowledgePrompts(BaseModel):
    guide_header: str


class AgentPrompts(BaseModel):
    cleaner: PromptPair
    analyst: PromptPair
    advisor: PromptPair
    mapper: MapperPrompts
    relevance: RelevancePrompts
    knowledge: KnowledgePrompts


class PromptConfig(BaseModel):
    agent: AgentPrompts


class OptionalLogConfig(BaseModel):
    level: str | None = None
    output_path: str | None = None
    encoding: str | None = None
    llm_log_path: str | None = None


class OptionalLLMConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class OptionalBilibiliConfig(BaseModel):
    cookie: str | None = None
    proxy: str | None = None


class RuntimeOverrides(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAIECHO_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server_port: str | None = None
    database_url: str | None = None
    log: OptionalLogConfig = Field(default_factory=OptionalLogConfig)
    llm: OptionalLLMConfig = Field(default_factory=OptionalLLMConfig)
    bilibili: OptionalBilibiliConfig = Field(default_factory=OptionalBilibiliConfig)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
            continue
        result[key] = value
    return result
