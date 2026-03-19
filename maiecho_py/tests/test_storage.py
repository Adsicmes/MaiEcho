from __future__ import annotations

from pathlib import Path

from maiecho_py.internal.model import AnalysisResult, Chart, Comment, Song, SongFilter
from maiecho_py.internal.storage.database import _resolve_sqlite_url, build_database
import maiecho_py.internal.storage as storage


def test_in_memory_database_url_is_resolved_correctly() -> None:
    assert _resolve_sqlite_url(":memory:") == "sqlite:///:memory:"


def test_upsert_song_replaces_charts_and_preserves_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "storage.db"
    repository = storage.StorageRepository(build_database(str(db_path)))

    original = Song(
        game_id=1001,
        title="Song A",
        artist="Artist",
        type="DX",
        charts=[Chart(difficulty="Master", level="14", ds=14.0, fit=14.2)],
    )
    saved = repository.upsert_song(original)

    updated = Song(
        game_id=1001,
        title="Song A Updated",
        artist="Artist",
        type="DX",
        charts=[
            Chart(difficulty="Expert", level="12+", ds=12.7, fit=12.8),
            Chart(difficulty="Master", level="14+", ds=14.4, fit=14.5),
        ],
    )
    upserted = repository.upsert_song(updated)

    assert saved.id == upserted.id
    fetched = repository.get_song_by_game_id(1001)
    assert fetched is not None
    assert fetched.title == "Song A Updated"
    assert [chart.difficulty for chart in fetched.charts] == ["Expert", "Master"]


def test_get_songs_supports_keyword_and_ds_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "storage.db"
    repository = storage.StorageRepository(build_database(str(db_path)))

    alpha = repository.create_song(
        Song(
            game_id=2001,
            title="Alpha",
            artist="Composer",
            genre="POPS",
            charts=[Chart(difficulty="Master", level="13+", ds=13.7, fit=13.8)],
        )
    )
    repository.save_song_aliases(alpha.id, ["阿尔法"])
    repository.create_song(
        Song(
            game_id=2002,
            title="Beta",
            artist="Other",
            genre="GAME",
            charts=[Chart(difficulty="Master", level="11", ds=11.2, fit=11.1)],
        )
    )

    songs, total = repository.get_songs(SongFilter(keyword="阿尔法", min_ds=13.0))

    assert total == 1
    assert [song.title for song in songs] == ["Alpha"]


def test_comment_and_analysis_queries_return_expected_records(tmp_path: Path) -> None:
    db_path = tmp_path / "storage.db"
    repository = storage.StorageRepository(build_database(str(db_path)))
    song = repository.create_song(Song(game_id=3001, title="Gamma"))

    repository.create_comment(
        Comment(
            song_id=song.id, content="这首歌谱面很有意思", source_title="Gamma 手元"
        )
    )
    repository.create_comment(
        Comment(song_id=song.id, content="普通评论", source_title="无关视频")
    )
    repository.create_analysis_result(
        AnalysisResult(target_type="song", target_id=song.id, summary="old")
    )
    latest = repository.create_analysis_result(
        AnalysisResult(target_type="song", target_id=song.id, summary="new")
    )

    matched_comments = repository.get_comments_by_keyword("谱面")
    latest_result = repository.get_analysis_result_by_song_id(song.id)

    assert len(matched_comments) == 1
    assert latest_result is not None
    assert latest_result.id == latest.id
    assert latest_result.summary == "new"
