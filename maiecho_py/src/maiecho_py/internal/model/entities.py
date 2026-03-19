from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from maiecho_py.internal.model.base import Base, TimestampMixin


class Song(TimestampMixin, Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    artist: Mapped[str | None] = mapped_column(String(255))
    genre: Mapped[str | None] = mapped_column(String(100))
    bpm: Mapped[float | None] = mapped_column(Float)
    release_date: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[str | None] = mapped_column(String(100))
    type: Mapped[str | None] = mapped_column(String(50))
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    cover_url: Mapped[str | None] = mapped_column(String(1024))
    last_scraped: Mapped[str | None] = mapped_column(String(64))

    charts: Mapped[list[Chart]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )
    aliases: Mapped[list[SongAlias]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )


class Chart(TimestampMixin, Base):
    __tablename__ = "charts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), index=True)
    difficulty: Mapped[str] = mapped_column(String(50))
    level: Mapped[str | None] = mapped_column(String(50))
    ds: Mapped[float | None] = mapped_column(Float)
    fit: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    charter: Mapped[str | None] = mapped_column(String(255))
    avg_achievement: Mapped[float | None] = mapped_column(Float)
    avg_dx: Mapped[float | None] = mapped_column(Float)
    std_dev: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int | None] = mapped_column(Integer)

    song: Mapped[Song] = relationship(back_populates="charts")


class SongAlias(TimestampMixin, Base):
    __tablename__ = "song_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), index=True)
    alias: Mapped[str] = mapped_column(String(255), index=True)
    is_suitable: Mapped[bool] = mapped_column(Boolean, default=True)

    song: Mapped[Song] = relationship(back_populates="aliases")


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int | None] = mapped_column(ForeignKey("songs.id"), index=True)
    chart_id: Mapped[int | None] = mapped_column(ForeignKey("charts.id"), index=True)
    source: Mapped[str | None] = mapped_column(String(50))
    source_title: Mapped[str | None] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    content: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    post_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_tag: Mapped[str | None] = mapped_column(String(255), index=True)
    sentiment: Mapped[float | None] = mapped_column(Float)

    song: Mapped[Optional[Song]] = relationship(back_populates="comments")


class AnalysisResult(TimestampMixin, Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(50), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    rating_advice: Mapped[str | None] = mapped_column(Text)
    difficulty_analysis: Mapped[str | None] = mapped_column(Text)
    reasoning_log: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[str | None] = mapped_column(Text)


class Video(TimestampMixin, Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(1024))
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
