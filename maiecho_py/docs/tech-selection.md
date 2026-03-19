# MaiEcho Python 技术选型

## 目标

这个目录不是重写 Go 版业务逻辑，而是先建立一个与 `server/` 同构的 Python 3.12 服务骨架，方便后续按模块迁移或并行验证。

## 初始技术栈

- **FastAPI**：对应 Go 版 Gin，适合继续保留清晰的 `controller -> service -> internal modules` 分层，同时原生支持 OpenAPI。
- **SQLAlchemy 2.x**：对应 Go 版 GORM，先落地 SQLite 和声明式模型，后续可平滑扩展到 PostgreSQL。
- **Pydantic + pydantic-settings**：负责配置模型、环境变量覆盖和接口响应类型，能把配置校验前置到启动阶段。
- **PyYAML**：继续沿用 YAML 管理 `config` 与 `prompts`，便于和现有 Go 版模板对照。
- **httpx**：统一外部 HTTP 客户端，后续适合承接 Diving-Fish、YuzuChan 和采集链路。
- **OpenAI Python SDK**：保持 OpenAI-compatible 接口风格，便于接入 DashScope、DeepSeek、Qwen 等兼容网关。
- **APScheduler**：对应 Go 版调度器位置，先提供启动/关闭骨架，不提前伪造采集任务逻辑。
- **psutil**：让 `/api/v1/system/status` 可以先返回真实的内存占用指标。
- **Jinja2**：用于替代 Go `text/template` 风格的 Prompt 渲染，后续迁移提示词时不需要把模板逻辑硬编码到 Python 里。
- **Alembic**：对应未来替代 GORM `AutoMigrate` 的演进路径，让 SQLite/PostgreSQL 共用明确的 schema 版本管理。
- **Tenacity**：用于外部 Provider 和采集链路的重试/退避，适合承接 Diving-Fish 与 Bilibili 的网络抖动场景。

> 当前状态说明：FastAPI、SQLAlchemy、Pydantic、YAML 资源加载、基础路由和应用生命周期已经接线；Alembic、Tenacity、Jinja2 已纳入选型与依赖，但还处于“已选未全面接入业务链路”的阶段。

## 结构映射

Python 目录保持和 Go 服务接近：

- `cmd/maiecho/main.py`：服务入口。
- `internal/config`：配置与提示词加载。
- `internal/router` / `controller`：路由与 HTTP 接口。
- `internal/storage` / `model`：数据库引擎、会话与模型。
- `internal/service`：业务编排占位层。
- `internal/agent` / `collector`：后续迁移评论清洗、分桶分析和采集能力。
- `internal/provider/divingfish`、`internal/provider/yuzuchan`：外部数据源客户端边界。
- `prompts/`、`config/`、`sqlite_db/`：继续沿用 Go 版资源组织方式。

## 不选什么

- **不选 Django**：它的 ORM + 全家桶过重，会冲淡现有 `controller -> service -> internal modules` 的边界。
- **不选 SQLModel 作为核心 ORM**：上手快，但在复杂映射和演进阶段不如直接使用 SQLAlchemy 2.x 稳定。
- **不默认引入 Scrapy**：当前采集更像 API/HTTP client + 少量反爬策略，不是典型大规模站点抓取；后续遇到强动态页面再补 Playwright。
- **不把 Playwright 设为首批强依赖**：Bilibili 现阶段更适合先走 `httpx` + 退避 + 头部/cookie 策略，浏览器自动化作为二阶段兜底。

## 外部参考：`TrueRou/maimai.py` 能怎么用

`maimai.py` 是一个偏 **maimai 领域 SDK / wrapper** 的 Python 项目，不是和 MaiEcho 同类型的分析后端。它的核心价值在于：

- 提供了比较成熟的 **领域模型与 Provider 分层思路**。
- 已经内置 `DivingFishProvider`、`YuzuProvider`、`LXNSProvider`、`WechatProvider` 等异步适配层。
- 使用 `httpx + tenacity` 做异步请求和重试，这一点和我们当前 Python 选型方向一致。
- 把 song / alias / player / score / curve 等能力拆成接口（如 `ISongProvider`、`IAliasProvider`、`ICurveProvider`），这对我们设计 `internal/provider` 很有参考价值。

### 对 MaiEcho Python 版的直接帮助

1. **可作为 `provider/divingfish` 的参考实现**
   - 它已经实现了 `music_data`、曲线/统计、玩家记录等 Diving-Fish 数据访问。
   - 对我们最有价值的是它对 **歌曲/难度/曲线数据的 Python 化映射方式**，以及 `tenacity` 重试策略。

2. **可作为 `provider/yuzuchan` 的参考实现**
   - 它已经有 `YuzuProvider.get_aliases()`，并且把 Yuzu 返回的别名按歌曲 ID 聚合。
   - 这很适合拿来对照我们要迁移的 Go 版 `RefreshAliases` 流程。

3. **可作为 maimai 领域模型参考**
   - 它的 `models.py`、`enums.py` 说明了 Python 社区里如何表达 song、difficulty、score、song type、level index 等领域对象。
   - 我们不一定直接复用它的模型，但可以参考它的命名、枚举拆分和 provider 输出形态。

4. **可作为“Provider 接口层”设计参考**
   - 它把 song provider、alias provider、curve provider 分开，而不是把所有第三方接口都堆到一个 client 里。
   - 这和 MaiEcho 当前 Go 版的 provider 边界非常兼容，适合我们在 Python 版继续保持 `provider/divingfish`、`provider/yuzuchan` 的清晰职责。

### 不应该怎么用

- **不要把 `maimai.py` 当成 MaiEcho 的整体替代品**：它偏 SDK，不负责 Bilibili 评论采集、评论清洗、分桶分析、LLM 报告生成。
- **不要直接把它的服务接口形态照搬成我们的 Web 架构**：MaiEcho 仍然需要自己的 `controller -> service -> storage/agent/provider` 分层。
- **不要把 player/score 查询能力误当成当前主线**：MaiEcho 当前的主目标是谱面评论分析，不是查分器。

### 当前规划中的采用策略

- **短期**：把它作为 `divingfish` / `yuzuchan` Python provider 的参考实现来源。
- **中期**：参考它的 provider 接口拆分方式，优化我们自己的 `internal/provider` 设计。
- **长期**：如果后面 MaiEcho 需要补充更完整的 maimai 元数据、曲线数据、玩家侧上下文，可评估是否局部引入其模型映射思路，甚至在隔离层里做兼容适配。

### 结论

`maimai.py` **有用，但用途是“参考和借鉴”大于“直接依赖”**。

对当前 Python 迁移最现实的价值排序是：

1. `DivingFishProvider` 参考
2. `YuzuProvider` 参考
3. maimai 领域模型/枚举参考
4. Provider 接口拆分参考

它不会替代 MaiEcho 的采集、分析、存储和 API 层，但能明显减少我们在 Python 版 provider 迁移时的试错成本。

## 当前边界

当前 Python 版已经实现这些真实能力：

1. 配置加载、提示词加载与应用生命周期。
2. SQLite 存储层、仓储接口、旧 schema 补列。
3. Diving-Fish 歌曲同步与 Yuzu 别名刷新。
4. songs / collect / analysis / status API。
5. Bilibili collect、backfill、discovery、mapper、analysis 自动工作流。
6. song 级与 chart 级 analysis 生成/读取。
7. scheduler 周期任务编排与状态观测。

当前还未完全对齐 Go 的，主要是：

- 更深的 Bilibili WAF/反爬恢复。
- 更细的 provider / mapper / analyzer 边缘语义。
- 更完整的日志、文档与运维外围。

## 下一阶段建议

1. 继续强化 Bilibili WAF/反爬恢复与失败恢复细节。
2. 继续打磨 provider / mapper / analyzer 的边缘语义。
3. 补齐更完整的 API/运维文档与配置说明。
