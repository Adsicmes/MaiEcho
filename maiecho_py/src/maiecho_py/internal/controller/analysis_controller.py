from __future__ import annotations

from typing import cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from maiecho_py.internal.container import AppContainer

router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalysisResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: str
    target_id: int
    summary: str | None
    rating_advice: str | None
    difficulty_analysis: str | None
    reasoning_log: str | None
    payload_json: str | None


class AggregatedAnalysisResponse(BaseModel):
    song_result: AnalysisResultResponse | None
    chart_results: list[AnalysisResultResponse]


class BatchAnalysisRequest(BaseModel):
    game_ids: list[int]


def _container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


def _not_implemented() -> None:
    raise HTTPException(status_code=501, detail="Analysis 能力尚未从 Go 版迁移完成")


@router.post("/songs/{song_id}")
async def analyze_song(song_id: int, request: Request) -> dict[str, object]:
    analyzed = False
    try:
        analyzed = await _container(request).analysis_service.analyze_song_by_game_id(
            song_id
        )
    except NotImplementedError:
        _not_implemented()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "message": "分析完成" if analyzed else "无可分析评论",
        "generated": analyzed,
    }


async def _run_batch_analysis(request: Request, game_ids: list[int]) -> None:
    await _container(request).analysis_service.analyze_batch_by_game_ids(game_ids)


@router.post("/batch")
def batch_analyze_songs(
    payload: BatchAnalysisRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if not payload.game_ids:
        raise HTTPException(status_code=400, detail="game_ids 不能为空")
    background_tasks.add_task(_run_batch_analysis, request, payload.game_ids)
    return {"message": "批量分析任务已在后台启动"}


@router.get("/songs/{song_id}", response_model=AggregatedAnalysisResponse)
def get_analysis_result(song_id: int, request: Request) -> AggregatedAnalysisResponse:
    aggregated = _container(
        request
    ).analysis_service.get_aggregated_analysis_result_by_game_id(song_id)
    if aggregated is None:
        raise HTTPException(status_code=404, detail="未找到分析结果")
    song_result, chart_results = aggregated
    return AggregatedAnalysisResponse(
        song_result=AnalysisResultResponse.model_validate(song_result)
        if song_result is not None
        else None,
        chart_results=[
            AnalysisResultResponse.model_validate(item) for item in chart_results
        ],
    )
