"""Database storage primitives."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from maiecho_py.internal.model import (
    AnalysisResult,
    Chart,
    Comment,
    Song,
    SongAlias,
    SongFilter,
    Video,
)
from maiecho_py.internal.storage.database import Database


class StorageRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create_song(self, song: Song) -> Song:
        with self._database.session() as session:
            session.add(song)
            session.commit()
            return song

    def upsert_song(self, song: Song) -> Song:
        with self._database.session() as session:
            existing = session.scalar(
                select(Song)
                .where(Song.game_id == song.game_id)
                .options(selectinload(Song.charts))
            )
            if existing is None:
                session.add(song)
                session.commit()
                return song

            self._copy_song_scalar_fields(existing, song)
            existing.charts.clear()
            for chart in song.charts:
                existing.charts.append(self._clone_chart(chart))
            session.commit()
            return existing

    def get_song(self, song_id: int) -> Song | None:
        with self._database.session() as session:
            return session.scalar(self._song_detail_query().where(Song.id == song_id))

    def get_song_by_game_id(self, game_id: int) -> Song | None:
        with self._database.session() as session:
            return session.scalar(
                self._song_detail_query().where(Song.game_id == game_id)
            )

    def get_all_songs(self) -> list[Song]:
        with self._database.session() as session:
            stmt = select(Song).options(selectinload(Song.aliases)).order_by(Song.id)
            return list(session.scalars(stmt).all())

    def get_songs(self, song_filter: SongFilter) -> tuple[list[Song], int]:
        with self._database.session() as session:
            query = self._apply_song_filter(select(Song), song_filter)
            count_stmt = select(func.count()).select_from(
                query.order_by(None).subquery()
            )
            total = int(session.scalar(count_stmt) or 0)

            offset = (song_filter.page - 1) * song_filter.page_size
            songs_stmt = (
                query.options(selectinload(Song.charts), selectinload(Song.aliases))
                .order_by(Song.id)
                .offset(offset)
                .limit(song_filter.page_size)
            )
            return list(session.scalars(songs_stmt).all()), total

    def save_song_aliases(self, song_id: int, aliases: list[str]) -> None:
        with self._database.session() as session:
            song = session.get(Song, song_id)
            if song is None:
                raise ValueError(f"歌曲不存在: {song_id}")
            song.aliases.clear()
            for alias in aliases:
                song.aliases.append(SongAlias(alias=alias))
            session.commit()

    def create_comment(self, comment: Comment) -> Comment:
        with self._database.session() as session:
            if comment.external_id:
                existing = session.scalar(
                    select(Comment).where(
                        Comment.source == comment.source,
                        Comment.external_id == comment.external_id,
                    )
                )
                if existing is not None:
                    existing.song_id = comment.song_id or existing.song_id
                    existing.source_title = (
                        comment.source_title or existing.source_title
                    )
                    existing.content = comment.content
                    existing.author = comment.author
                    existing.post_date = comment.post_date
                    existing.search_tag = comment.search_tag
                    existing.sentiment = comment.sentiment
                    session.commit()
                    return existing
            session.add(comment)
            session.commit()
            return comment

    def update_comment(self, comment: Comment) -> Comment:
        with self._database.session() as session:
            merged = session.merge(comment)
            session.commit()
            return merged

    def get_comments_by_keyword(self, keyword: str) -> list[Comment]:
        with self._database.session() as session:
            pattern = f"%{keyword}%"
            stmt = select(Comment).where(
                or_(Comment.content.like(pattern), Comment.source_title.like(pattern))
            )
            return list(session.scalars(stmt).all())

    def get_comments_by_song_id(self, song_id: int) -> list[Comment]:
        with self._database.session() as session:
            stmt = (
                select(Comment).where(Comment.song_id == song_id).order_by(Comment.id)
            )
            return list(session.scalars(stmt).all())

    def get_unmapped_comments(self) -> list[Comment]:
        with self._database.session() as session:
            stmt = select(Comment).where(Comment.song_id.is_(None)).order_by(Comment.id)
            return list(session.scalars(stmt).all())

    def create_analysis_result(self, result: AnalysisResult) -> AnalysisResult:
        with self._database.session() as session:
            session.add(result)
            session.commit()
            return result

    def get_analysis_result_by_song_id(self, song_id: int) -> AnalysisResult | None:
        return self.get_analysis_results_by_target("song", song_id)

    def get_analysis_results_by_target(
        self, target_type: str, target_id: int
    ) -> AnalysisResult | None:
        with self._database.session() as session:
            stmt = (
                select(AnalysisResult)
                .where(
                    AnalysisResult.target_type == target_type,
                    AnalysisResult.target_id == target_id,
                )
                .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            )
            return session.scalar(stmt)

    def create_video(self, video: Video) -> Video:
        with self._database.session() as session:
            existing = session.scalar(
                select(Video).where(Video.external_id == video.external_id)
            )
            if existing is None:
                session.add(video)
                session.commit()
                return video

            existing.source = video.source
            existing.title = video.title
            existing.description = video.description
            existing.author = video.author
            existing.url = video.url
            existing.publish_time = video.publish_time
            session.commit()
            return existing

    def update_song_last_scraped_time(self, song_id: int) -> None:
        with self._database.session() as session:
            song = session.get(Song, song_id)
            if song is None:
                raise ValueError(f"歌曲不存在: {song_id}")
            song.last_scraped = datetime.now(timezone.utc).isoformat()
            session.commit()

    def update_song_alias_suitability(self, alias_id: int, is_suitable: bool) -> None:
        with self._database.session() as session:
            alias = session.get(SongAlias, alias_id)
            if alias is None:
                raise ValueError(f"别名不存在: {alias_id}")
            alias.is_suitable = is_suitable
            session.commit()

    @staticmethod
    def _song_detail_query() -> Select[tuple[Song]]:
        return select(Song).options(
            selectinload(Song.charts), selectinload(Song.aliases)
        )

    @staticmethod
    def _clone_chart(chart: Chart) -> Chart:
        return Chart(
            difficulty=chart.difficulty,
            level=chart.level,
            ds=chart.ds,
            fit=chart.fit,
            notes=chart.notes,
            charter=chart.charter,
            avg_achievement=chart.avg_achievement,
            avg_dx=chart.avg_dx,
            std_dev=chart.std_dev,
            sample_count=chart.sample_count,
        )

    @staticmethod
    def _copy_song_scalar_fields(target: Song, source: Song) -> None:
        target.game_id = source.game_id
        target.title = source.title
        target.artist = source.artist
        target.genre = source.genre
        target.bpm = source.bpm
        target.release_date = source.release_date
        target.version = source.version
        target.type = source.type
        target.is_new = bool(source.is_new)
        target.cover_url = source.cover_url
        target.last_scraped = source.last_scraped

    @staticmethod
    def _apply_song_filter(
        stmt: Select[tuple[Song]], song_filter: SongFilter
    ) -> Select[tuple[Song]]:
        if song_filter.version:
            stmt = stmt.where(Song.version == song_filter.version)
        if song_filter.type:
            stmt = stmt.where(Song.type == song_filter.type)
        if song_filter.genre:
            stmt = stmt.where(Song.genre == song_filter.genre)
        if song_filter.is_new is not None:
            stmt = stmt.where(Song.is_new == song_filter.is_new)
        if song_filter.keyword:
            pattern = f"%{song_filter.keyword}%"
            alias_song_ids = select(SongAlias.song_id).where(
                SongAlias.alias.like(pattern)
            )
            stmt = stmt.where(
                or_(
                    Song.title.like(pattern),
                    Song.artist.like(pattern),
                    Song.id.in_(alias_song_ids),
                )
            )
        if song_filter.min_ds > 0 or song_filter.max_ds > 0:
            chart_song_ids = select(Chart.song_id)
            if song_filter.min_ds > 0:
                chart_song_ids = chart_song_ids.where(Chart.ds >= song_filter.min_ds)
            if song_filter.max_ds > 0:
                chart_song_ids = chart_song_ids.where(Chart.ds <= song_filter.max_ds)
            stmt = stmt.where(Song.id.in_(chart_song_ids))
        return stmt


__all__ = ["StorageRepository"]
