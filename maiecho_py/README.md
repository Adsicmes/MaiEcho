# MaiEcho Python Scaffold

`maiecho_py/` 是 MaiEcho Go 服务的 Python 3.12 同构脚手架，目标是先把目录边界、配置方式、提示词资源、数据库入口和 HTTP 启动链搭起来，再逐步迁移真实业务能力。

## 已建立的结构

```text
maiecho_py/
├── pyproject.toml
├── main.py
├── config/
│   └── config.example.yaml
├── docs/
│   └── tech-selection.md
├── prompts/
│   └── prompts.yaml
├── sqlite_db/
│   └── .gitkeep
└── src/maiecho_py/
    ├── app.py
    ├── cmd/maiecho/main.py
    ├── config/config.example.yaml
    ├── prompts/prompts.yaml
    ├── sqlite_db/.gitkeep
    └── internal/
        ├── agent/
        ├── collector/
        ├── config/
        ├── controller/
        ├── llm/
        ├── logger/
        ├── model/
        ├── provider/
        ├── router/
        ├── scheduler/
        ├── service/
        ├── status/
        └── storage/
```

## 现在能做什么

- 作为真实 Python 包安装与导入。
- 从 YAML 加载配置和提示词模板。
- 初始化 SQLAlchemy SQLite 引擎与基础模型。
- 启动 FastAPI 应用工厂。
- 提供带任务观测信息的 `/api/v1/system/status` 接口。
- 同步 Diving-Fish 歌曲与 Yuzu 别名。
- 执行 collect / backfill / discovery / mapper / analysis 自动工作流。
- 提供 songs / collect / analysis API，并写入 SQLite。

## 设计原则

- 尽量保留 Go 版的模块边界和初始化顺序。
- 不提前编造采集、同步、分析结果。
- 先把入口、资源文件、依赖和内部边界稳定下来。

## 配置与资源

- 配置模板：`src/maiecho_py/config/config.example.yaml`
- 提示词模板：`src/maiecho_py/prompts/prompts.yaml`
- SQLite 目录：`src/maiecho_py/sqlite_db/`

运行时也会优先查找项目根目录下的这些资源：

- `config/config.yaml` 或 `config/config.example.yaml`
- `prompts/prompts.yaml`
- `sqlite_db/maiecho.db`

## 本地运行

1. 安装依赖：`uv sync --extra dev`
2. 准备配置：复制 `config/config.example.yaml` 为 `config/config.yaml`
3. 启动服务：`uv run python main.py`
4. 打开 API 文档：`http://127.0.0.1:8080/docs`

默认会使用：

- `config/config.yaml`
- `prompts/prompts.yaml`
- `sqlite_db/maiecho.db`

## 常用验证命令

- 测试：`uv run pytest`
- Lint：`uv run ruff check .`
- 类型检查：`uv run mypy src tests`

## 最短工作流

1. `POST /api/v1/songs/sync`
2. `POST /api/v1/songs/aliases/refresh`
3. `POST /api/v1/collect` 或等待定期 discovery
4. `POST /api/v1/analysis/songs/{game_id}` 或等待定期 analysis
5. `GET /api/v1/system/status` 查看运行态

## 运行态观测

`GET /api/v1/system/status` 会返回：

- `active_tasks`：当前活跃任务数
- `queued_tasks`：排队中的采集任务数
- `periodic_jobs`：周期任务名称列表
- `collector_health`：各 collector 的健康状态、最近错误、封禁截止时间
- `recent_tasks`：最近任务执行记录
- `last_log_entry`：最近一条日志

## 技术选型说明

见 `docs/tech-selection.md`。
