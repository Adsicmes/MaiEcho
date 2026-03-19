# MaiEcho Python

MaiEcho Python 是一个面向 **maimai** 的评论采集与谱面分析后端服务。

当前仓库已经移除旧的 Go 实现，保留可运行的 Python 版本，具备这些核心能力：

- 同步 Diving-Fish 歌曲与谱面信息
- 刷新 YuzuChan 歌曲别名
- 采集 Bilibili 视频与评论
- discovery / mapper 自动把未绑定评论挂到歌曲
- 生成 song 级与 chart 级分析结果
- 执行定期 discovery / mapper / analysis 编排
- 通过 `/api/v1/system/status` 观察运行状态与 collector 健康

## 快速开始

```bash
cd maiecho_py
uv sync --extra dev
uv run python main.py
```

启动后访问：

- Swagger 文档：`http://127.0.0.1:8080/docs`
- 状态接口：`http://127.0.0.1:8080/api/v1/system/status`

更完整的运行说明见：

- `maiecho_py/README.md`
- `maiecho_py/docs/tech-selection.md`
