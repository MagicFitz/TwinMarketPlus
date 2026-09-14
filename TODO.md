# TwinMarket UI Implementation TODO

> 目标：从当前只读 Studio 原型演进为一个可以完成“新建实例 → 启动运行 → 观测运行 → 查看结果”的 TwinMarket UI，并将运行过程设计为可观察、可审计、可解释的 Runtime Observatory。
>
> 设计依据：`docs/TwinMarket_Runtime_Observatory_Design_ZH.md`，以及围绕最简交互闭环、完整后端能力与 FastAPI 迁移的讨论。

## 0. 当前基线

- [x] React + Vite Studio 已具备 Experiment、Agent、Market、Setting、Documentation 页面。
- [x] `studio/server.py` 可以只读访问现有 `logs_*`、SQLite、配置摘要和已发布文档。
- [x] 当前 SQLite 访问使用只读连接，写请求被拒绝，日志和配置有基础脱敏。
- [x] 已有运行准备、新闻索引构建和运行监控脚本。
- [x] Studio Python 测试、Sites Worker 测试和生产构建可以通过。
- [ ] 当前 UI 尚不能创建、启动、停止或续跑实验。
- [ ] 当前运行状态主要通过数据库、目录和文本日志推断，没有正式的运行事件协议。
- [ ] 当前 100 Agent 实跑尚未完成；OpenAI/vLLM 请求存在上下文超限导致的 HTTP 400。
- [ ] 当前 Sites Worker 只托管静态资源，不提供 Python API。

## 1. 已确认的产品范围

### 1.1 核心用户闭环

- [ ] 将首要流程收敛为：`新建实例 → 运行 → Runtime Observatory → 结果数据表`。
- [ ] 新建成功后生成稳定的 `run_id`，并直接进入实例详情或运行页面。
- [ ] 运行页同时表达 Run、Trading Day、Agent 三个尺度，不使用一个进度条混合表达。
- [ ] 结果页至少提供每日汇总、成交明细和 Agent 结果三类真实数据。
- [ ] Agent、Market、Setting 的高级配置可以保留，但不阻塞首次运行闭环。

### 1.2 Runtime Observatory 原则

- [ ] 运行页定位为“人工金融市场观测台”，而不是 KPI + 进度条 + 终端日志。
- [ ] 使用固定流程槽位，动态更新节点内部的状态、耗时、输入摘要、输出摘要和重试信息。
- [ ] Agent 一级运行本体固定为：`State → Perception → Interpretation → Decision → Action → Commit`。
- [ ] 当日宏观流程固定为：`Prepare → Agents → Market → Social → Commit`。
- [ ] 结构化 `RuntimeEvent` 是产品状态事实源；普通日志仅用于 Diagnostics。
- [ ] 不默认展示 API Key、完整私有 endpoint、完整 prompt、隐藏推理或未脱敏模型输出。
- [ ] 运行事实优先于动画；快速运行时允许批量消费事件，慢速运行时必须明确显示等待和耗时。

### 1.3 暂不作为首版阻塞项

- [ ] Worker 性能甘特图。
- [ ] Token 成本分析。
- [ ] 完整模型对话展示。
- [ ] 社交图动画。
- [ ] Runtime Replay 播放控制。
- [ ] 多实验运行时对比和阶段延迟分布。
- [ ] 多租户、跨机器 Worker 和复杂组织权限。

## 2. 目标架构

```text
React UI
   ↓ HTTP / SSE
FastAPI Control API
   ├── Run Registry
   ├── Runtime Snapshot Reducer
   ├── Results Query Service
   └── Diagnostics Service
          ↓
Simulation Process Manager
   ↓
simulation.py + RuntimeObserver
   ├── SQLite / CSV / JSON artifacts
   ├── events.jsonl
   └── simulation.log
```

- [ ] FastAPI 只承担控制面、查询面和事件推送，不在 HTTP 请求协程中直接执行长时间模拟。
- [ ] 仿真通过独立子进程或 Worker 运行，API 服务重启不能直接破坏正在运行的实验。
- [ ] `simulation.py` 仅调用 `RuntimeObserver.emit(...)`，不感知 React、SSE 或具体 UI 组件。
- [ ] 本地第一版继续使用 SQLite 和运行目录；出现多机或高并发需求后再引入 PostgreSQL、Redis 或任务队列。
- [ ] 静态 Sites Worker 与动态 API 部署保持解耦；部署 UI 不等于部署运行后端。

## 3. P0 — 先恢复可运行基线

### 3.1 修复模型请求阻塞

- [ ] 根据模型上下文窗口和估算输入 token 动态收缩 `max_tokens`。
- [ ] 为不同 provider 定义模型能力配置：上下文长度、最大输出、是否支持指定参数。
- [ ] 将不可重试的 4xx 参数错误与可重试的超时、限流、5xx 分开处理。
- [ ] 避免对同一个确定性 400 连续重试 10 次。
- [ ] 将 provider、model、request_id、latency、token 数、attempt 和错误代码写入结构化事件。
- [ ] 使用 10 Agent、低激活概率完成至少 2 个交易日 smoke run。
- [ ] 使用 100 Agent 完成一个完整 10 交易日验证运行。

### 3.2 固化运行目录契约

- [ ] 每个 `run_id` 对应一个不可冲突的运行目录。
- [ ] 保存创建时的完整非敏感配置快照，而不是只从日志反向解析参数。
- [ ] 保存数据、Agent Group、Market Environment、模型配置的版本或摘要指纹。
- [ ] 保存随机种子、代码版本和启动命令摘要，支持结果复现。
- [ ] 明确 checkpoint、续跑日期和已有产物之间的一致性规则。
- [ ] 禁止两个进程同时写入同一运行目录和同一组数据库。

### 3.3 建立回归测试

- [ ] 为 `BaseAgent` 增加上下文超限、限流、超时和重试分类测试。
- [ ] 为运行准备脚本增加用户 ID、belief、数据库完整性和拒绝覆盖测试。
- [ ] 为 checkpoint 清理边界增加测试。
- [ ] 将 Python 编译检查、Shell 语法检查、Studio 测试和前端构建纳入统一检查命令。

## 4. P0 — Run Registry 与生命周期

### 4.1 持久化 Run 实体

- [ ] 新建运行注册表，至少保存：
  - `run_id`、名称、描述；
  - 创建时间、开始时间、结束时间；
  - 生命周期状态、健康状态；
  - 配置快照、输出目录、checkpoint 信息；
  - PID/Worker ID、退出码、失败原因；
  - 最后心跳和最后事件 ID。
- [ ] 生命周期枚举固定为：`draft / queued / running / stopping / completed / failed / cancelled`。
- [ ] 健康状态独立为：`healthy / degraded / stale / unavailable`。
- [ ] Agent 局部失败只降低 Run health，不自动将整个 Run 标为 failed。
- [ ] 服务重启时核对 PID、心跳、结束标记和退出码，恢复正确状态。

### 4.2 运行控制

- [ ] 支持创建、复制、归档和安全删除未运行实例。
- [ ] 支持启动、停止、失败重试和 checkpoint 续跑。
- [ ] `start`、`stop`、`resume` 必须幂等。
- [ ] 启动前校验所有必需文件、参数、数据库、belief、模型配置和输出目录。
- [ ] 停止流程先发送温和终止信号，超时后再升级处理，并记录终止原因。
- [ ] 防止启动超过本机并发配额或模型接口容量的任务。
- [ ] 将 stdout/stderr 写入运行日志，但不以文本日志作为 UI 状态事实源。

### 4.3 Run API

- [ ] `POST /api/runs`：创建草稿实例。
- [ ] `GET /api/runs`：分页、筛选并列出实例。
- [ ] `GET /api/runs/{run_id}`：读取配置、生命周期、健康状态和产物概览。
- [ ] `POST /api/runs/{run_id}/start`：启动实例。
- [ ] `POST /api/runs/{run_id}/stop`：停止实例。
- [ ] `POST /api/runs/{run_id}/resume`：从合法 checkpoint 续跑。
- [ ] `POST /api/runs/{run_id}/archive`：归档实例。
- [ ] 对非法状态转换返回明确的 409，而不是笼统的 500。

## 5. P0 — RuntimeEvent 基础设施

### 5.1 Runtime 模块

- [ ] 新建稳定、独立的运行时模块：

```text
runtime/
├── event.py
├── observer.py
├── event_store.py
├── snapshot.py
└── schemas.py
```

- [ ] `event.py` 定义不可变 `RuntimeEvent`。
- [ ] `observer.py` 提供低侵入的 `emit_started/completed/skipped/failed/retrying` 接口。
- [ ] `event_store.py` 将事件追加写入 `events.jsonl`，并维护有限内存缓冲区。
- [ ] `snapshot.py` 将事件归约为当前 Run、Day、Worker 和 Agent 状态。
- [ ] `schemas.py` 定义后端和前端共享的稳定字段与枚举。
- [ ] Observer 写入失败不能改变市场算法结果，但必须产生可见的 degraded health。

### 5.2 事件契约

- [ ] 每个事件至少包含：
  - `event_id`、`run_id`；
  - `simulation_date`；
  - `scope`、`stage`、`substage`；
  - `event`；
  - `agent_id`、`worker_id`（适用时）；
  - `started_at`、`ended_at`、`duration_ms`；
  - `attempt`；
  - `input_summary`、`output_summary`；
  - 用户可理解的 `message`；
  - 结构化错误代码和已脱敏错误摘要。
- [ ] 一级事件类型固定为：`stage_started / stage_completed / stage_skipped / stage_failed / stage_retrying`。
- [ ] Scope 固定为：`run / day / agent / market / social / artifact / system`。
- [ ] Agent stage 固定为：`state / perception / interpretation / decision / action / commit`。
- [ ] Substage 可以随底层实现变化，但不能迫使 UI 改变主 Pipeline。
- [ ] `event_id` 在单个 Run 中有严格顺序，可支持断线补发和未来 Replay。

### 5.3 仿真埋点

- [ ] 在 Run 启动、停止、完成、失败处发出事件。
- [ ] 在每个自然日开始和完成处发出事件，并记录是否交易日。
- [ ] 为当天 `prepare / agents / market / social / commit` 五阶段埋点。
- [ ] 为 Agent 六阶段埋点，并提供稳定摘要：
  - State：身份、策略、激活状态、现金/持仓/belief 摘要；
  - Perception：论坛、新闻、检索文档、候选资产数量；
  - Interpretation：belief 前后值、信号摘要、LLM 指标；
  - Decision：Buy/Sell/Hold、目标仓位和理由摘要；
  - Action：可执行订单、帖子、互动和无效原因；
  - Commit：已写入的 decision、conversation、order、post 和 artifact。
- [ ] 为并发任务记录稳定 `worker_id`，不能假设 Agent 严格串行。
- [ ] 为 market matching 记录买卖订单、匹配、未匹配和成交计数。
- [ ] 为 social update 记录帖子、点赞、转发、引用和失败计数。
- [ ] 非交易日仍发出完整 Day Cycle，并将 Market 标记为 `skipped/market_closed`。

## 6. P0 — Runtime API 与实时传输

- [ ] `GET /api/runs/{run_id}/runtime`：返回完整当前快照。
- [ ] `GET /api/runs/{run_id}/events`：通过 SSE 推送增量事件。
- [ ] `GET /api/runs/{run_id}/agents/{agent_id}/runtime`：返回 Agent Pipeline 快照。
- [ ] `GET /api/runs/{run_id}/diagnostics`：返回错误、重试、慢阶段、PID 和退出码摘要。
- [ ] SSE 支持 `Last-Event-ID`，重连时先补发遗漏事件再进入实时模式。
- [ ] 慢客户端不得阻塞模拟进程；采用缓冲、批量或丢弃非关键重复更新的策略。
- [ ] 快速运行时允许一批事件更新一个完整 Agent 快照，不人为延迟模拟。
- [ ] 对完成的 Run，Runtime API 从持久化事件重建状态，不依赖活跃进程。
- [ ] 普通日志使用独立分页/尾部接口，禁止与 RuntimeEvent 混用。

## 7. P0 — 最简 UI 主流程

### 7.1 新建实例

- [ ] 提供名称、用户数量、起止日期、模型配置和必要数据源字段。
- [ ] 高级参数默认折叠，保留并发数、激活概率、技术面概率和随机种子。
- [ ] 提交前显示校验结果和预计规模，不展示或回填密钥。
- [ ] 创建成功后跳转到 `/studio/runs/{run_id}`。
- [ ] 未启动实例可以继续编辑；已启动实例配置不可原地修改，只能复制为新实例。

### 7.2 启动与状态反馈

- [ ] 用户确认后启动运行，并跳转到 `/studio/runs/{run_id}/live`。
- [ ] 明确显示排队、启动中、运行中、正在停止、完成、失败和已取消。
- [ ] 长任务必须提供停止入口；失败任务必须提供诊断和合法续跑入口。
- [ ] 刷新或关闭页面不能影响后台模拟。
- [ ] 浏览器断线重连后恢复最新 Snapshot 和遗漏事件。

## 8. P0 — LiveSimulationView

### 8.1 页面骨架

- [ ] 合并零散运行概览，创建 `LiveSimulationView`。
- [ ] 页面结构固定为：

```text
RunHeader
DayCycle
FocusAgentPanel
WorkerLanePanel
TodaySummary + RuntimeEventList
RuntimeDiagnosticsDrawer
```

### 8.2 Run Header

- [ ] 显示运行状态、健康状态、模拟日期和交易日序号。
- [ ] 分开展示 Run 进度、Day 进度和 Agent 进度。
- [ ] 显示已处理 Agent、LLM 调用数、累计耗时和最后事件时间。
- [ ] 提供 Stop、Diagnostics 和 Run Settings 入口。
- [ ] 状态不得只依赖颜色，必须同时有图标或文字。

### 8.3 Day Cycle

- [ ] 固定展示 `Environment → Agent Processing → Market → Social → Commit`。
- [ ] 支持 `completed / running / pending / warning / failed / skipped`。
- [ ] Agent Processing 显示完成数、运行数、队列数、重试数和失败数。
- [ ] Agent 处理完成后显著切换到 Market Clearing，再进入 Social 和 Day Commit。
- [ ] 日完成时展示短暂日终摘要，再重置并进入下一日。
- [ ] 非交易日显示 `Market Closed / No matching executed`，不隐藏整个阶段。

### 8.4 Focus Agent Pipeline

- [ ] 固定展示六阶段卡片，不因实时事件新增或移动节点。
- [ ] 每张卡片支持 pending、running、completed、skipped、failed、retrying。
- [ ] 展示阶段耗时、当前 substage、摘要和重试次数。
- [ ] Interpretation 只展示 belief 变化、信号摘要和调用指标，不展示隐藏推理。
- [ ] Decision 明确区分认知意图，Action 明确区分实际可执行动作。
- [ ] Commit 明确表示哪些信息已成为模拟世界中的持久事实。
- [ ] 默认自动聚焦最近进入新阶段的 Agent。
- [ ] 用户手动选择 Agent 后关闭自动切换，并提供 Auto Follow 开关。

### 8.5 Worker Lanes 与 Agent Queue

- [ ] 为每个活跃 Worker 显示 Agent、阶段、耗时和状态。
- [ ] 点击 Worker/Agent 后更新 Focus Agent。
- [ ] `max_workers=1` 时自动退化为单个 Current Agent，而不是维护第二套页面。
- [ ] Activation 与 Execution 状态分离。
- [ ] 汇总 completed、running、queued、retrying、failed、inactive。

### 8.6 Today Summary 与事件流

- [ ] 实时累计 Buy、Sell、Hold、Orders、Posts、Interactions 和 Failures。
- [ ] Recent Events 默认只显示高层事件，不成为终端日志 Viewer。
- [ ] 事件列表支持 scope、stage、Agent 和错误级别筛选。
- [ ] Warnings、Errors、Retries 和 Slow Stages 进入 Diagnostics Drawer。
- [ ] 慢 LLM 阶段显示等待时长、模型和 attempt，避免被误判为卡死。

### 8.7 动效与可访问性

- [ ] Running 节点使用轻微 pulse、计时器或 loading indicator。
- [ ] 完成转换可以短暂高亮；数据流箭头只使用轻微动效。
- [ ] 遵循 `prefers-reduced-motion`。
- [ ] 运行、失败、跳过、市场涨跌使用不同语义体系，且不能只靠颜色。
- [ ] 键盘可以选择 Worker、Agent、阶段详情和 Diagnostics。

## 9. P0 — 结果页

### 9.1 结果 API

- [ ] `GET /api/runs/{run_id}/results/summary`：每日市场与社交汇总。
- [ ] `GET /api/runs/{run_id}/results/trades`：成交明细，支持分页、排序、日期和资产筛选。
- [ ] `GET /api/runs/{run_id}/results/agents`：Agent 收益、资产、持仓和行为分组。
- [ ] `GET /api/runs/{run_id}/results/orders`：订单及未成交原因。
- [ ] `GET /api/runs/{run_id}/results/social`：帖子和互动汇总。
- [ ] `GET /api/runs/{run_id}/artifacts`：产物清单和可下载文件。
- [ ] 大表必须服务端分页，聚合结果应缓存或预计算。

### 9.2 结果 UI

- [ ] 完成后自动从 Observatory 进入结果入口，但保留查看运行事件的能力。
- [ ] 提供每日汇总、成交明细、Agent 结果三个首要标签页。
- [ ] 每张表显示数据口径、来源日期和最后更新时间。
- [ ] 支持日期、Agent、资产、行为类型筛选。
- [ ] 支持 CSV/JSON 流式导出。
- [ ] 缺失数据展示 unavailable，不得伪造为 0。
- [ ] 区分初始化历史数据与本次模拟产生的数据。

## 10. P1 — Agent、Market 与 Setting 完整能力

### 10.1 Agent Group

- [ ] 创建、复制、版本化和归档 Agent Group。
- [ ] 支持模板选择、确定性采样和条件筛选。
- [ ] 编辑行为金融参数、初始资金、持仓、策略和 belief。
- [ ] 校验 Profiles、Strategy、TradingDetails 和 belief 的用户集合一致。
- [ ] 查看 Agent Profile、Portfolio、Belief History、感知信息、决策、订单、帖子和 Runtime Events。

### 10.2 Market Environment

- [ ] 创建、复制、版本化和归档 Market Environment。
- [ ] 配置资产包、交易日历、撮合机制、费用和成交限制。
- [ ] 导入并校验行情、新闻和交易日数据。
- [ ] 构建、更新和验证新闻向量索引。
- [ ] 运行创建时冻结数据快照或内容指纹，保证实验可复现。

### 10.3 Model 与 Data Source

- [ ] 管理语言模型和 embedding 模型连接。
- [ ] 密钥加密保存，读取 API 永不返回明文。
- [ ] 提供连接测试、模型能力检查、限流和健康状态。
- [ ] 支持 timeout、并发、退避、熔断和 provider-specific 参数。
- [ ] 统计模型调用量、token、延迟、失败率和成本摘要。

## 11. P1 — Diagnostics、审计与 Replay 基础

- [ ] 结构化保存错误、重试、慢阶段、进程退出和 API 错误。
- [ ] 支持按 Run、Day、Agent、stage、错误代码检索 RuntimeEvent。
- [ ] 为事件和产物记录关联 ID，支持从结果追溯到 Agent 决策和输入摘要。
- [ ] 已完成 Run 可以从 `events.jsonl` 重建 Observatory 快照。
- [ ] 确保前端状态只依赖 Snapshot + Event，不绑定实时进程。
- [ ] 预留 `/studio/runs/{run_id}/replay`，首版不实现播放控制。
- [ ] 记录谁创建、启动、停止、续跑、归档或删除了实验。

## 12. P2 — 生产化与扩展

- [ ] 增加用户认证、项目权限、实验所有权和角色控制。
- [ ] 增加请求限流、任务并发配额和磁盘配额。
- [ ] 增加 Worker 心跳、僵尸进程发现和自动状态修复。
- [ ] 增加数据库迁移、API 版本和向后兼容策略。
- [ ] 增加结构化服务日志、指标、追踪和健康检查。
- [ ] 增加运行目录归档、保留期限和安全清理策略。
- [ ] 如果需要多机运行，迁移到 PostgreSQL + Redis/任务队列 + 独立 Worker。
- [ ] 为远程部署增加 TLS、CORS allowlist、CSRF/鉴权策略和 secret manager。
- [ ] 对所有路径、下载、配置引用和进程参数保持 allowlist，禁止目录穿越与命令注入。

## 13. FastAPI 迁移计划

- [ ] 不对当前 `studio/server.py` 做一次性重写；先抽离纯数据读取和业务服务函数。
- [ ] 新建 FastAPI 应用和版本化路由，例如 `studio/api/main.py`、`studio/api/routes/`。
- [ ] 使用 Pydantic 定义 Run、RuntimeEvent、Snapshot、Result 和 Error Schema。
- [ ] 将现有只读 `/api/runs`、Agent、Market、Documentation 路由迁移并保持行为一致。
- [ ] 继续保留 SQLite `mode=ro`、`PRAGMA query_only=ON`、路径边界和脱敏测试。
- [ ] 在回归测试通过后，再加入 Run 写 API、Process Manager 和 SSE。
- [ ] 开发模式由 Vite 代理 `/api` 到 FastAPI；生产模式明确静态 UI 与 API 的部署地址。
- [ ] 提供 `/health/live` 和 `/health/ready`，ready 检查注册表和必要数据源，但不发起昂贵模型调用。

## 14. 测试与验证矩阵

### 14.1 单元测试

- [ ] RuntimeEvent schema、枚举和脱敏。
- [ ] Event Store 追加、恢复、截断文件和并发写入。
- [ ] Snapshot Reducer 的乱序、重复、重试、跳过和失败事件。
- [ ] 生命周期合法转换、幂等启动和重复停止。
- [ ] 结果统计口径、分页和缺失数据。
- [ ] 路径、配置和下载 allowlist。

### 14.2 集成测试

- [ ] 创建实例 → 启动子进程 → 收到事件 → 正常完成。
- [ ] 停止运行 → 状态 cancelled → 产物保持可读。
- [ ] API 服务重启 → 识别活跃 Worker 或恢复 stale 状态。
- [ ] SSE 断开 → 使用 Last-Event-ID 补发 → 快照一致。
- [ ] Agent 局部失败 → Run 保持 running 且 health=degraded。
- [ ] 非交易日 → Market skipped → Social/Commit 正常执行。
- [ ] checkpoint 续跑不重复提交已完成日期。

### 14.3 UI 测试

- [ ] 新建实例表单校验、启动确认和重复点击保护。
- [ ] Run/Day/Agent 三层进度语义正确。
- [ ] 六阶段卡片覆盖所有状态。
- [ ] Auto Follow 和手动 Focus Agent 行为正确。
- [ ] 高速事件批量更新时页面不丢失最终真值。
- [ ] 慢 LLM 阶段持续显示 elapsed 和 attempt。
- [ ] SSE 断线保留最后快照，重连后恢复。
- [ ] 结果表筛选、分页、排序和导出。
- [ ] 390、1024 和桌面宽度无横向页面溢出。
- [ ] 键盘、焦点、对比度、状态非颜色表达和 reduced motion 验证。

### 14.4 性能与可靠性

- [ ] 100 Agent 并发事件量下，Observer 对仿真耗时影响可接受。
- [ ] 事件文件增长时 Snapshot API 不每次全量扫描。
- [ ] SSE 慢客户端不会拖慢 Event Store 或模拟进程。
- [ ] 大成交表使用服务端分页，浏览器不加载完整文件。
- [ ] 长时间运行后日志、事件、数据库和注册表状态一致。

## 15. 核心验收场景

- [ ] 用户可以在 UI 中创建一个 10 Agent 实例并看到校验通过。
- [ ] 点击运行后 2 秒内进入 Running/Queued 明确状态，页面刷新不影响任务。
- [ ] Observatory 能分别显示 Run、Day 和 Agent 进度。
- [ ] 用户能观察任意活跃 Agent 的六阶段状态、耗时、摘要和重试。
- [ ] Agent 全部处理完成后，界面明确进入 Market、Social、Commit，而不是直接跳到下一天。
- [ ] 非交易日保持完整流程，并明确显示 Market Closed。
- [ ] 局部 Agent 失败时 Run 可继续且 health=degraded。
- [ ] 用户可以停止运行，并获得明确的 cancelled 状态和可用的已有产物。
- [ ] Run 完成后可以查看真实的每日汇总、成交明细和 Agent 结果表。
- [ ] 任一结果都能追溯到运行配置、日期和相关结构化事件。
- [ ] 页面不泄露凭据、私有 endpoint、完整隐藏推理或未脱敏原始模型内容。

## 16. Definition of Done

一个阶段只有同时满足以下条件才可勾选完成：

- [ ] 功能已经接入真实 TwinMarket 数据或真实运行流程，不使用虚构结果。
- [ ] API Schema、错误状态和数据口径已有文档。
- [ ] 关键路径具备自动化测试，且现有只读安全测试没有回归。
- [ ] UI 覆盖 loading、empty、unavailable、stale、failed 和 completed 状态。
- [ ] 不依赖解析普通文本日志来推断产品级运行状态。
- [ ] 没有把 Agent 局部失败错误提升为整个 Run 失败。
- [ ] 没有泄露配置密钥、私有 prompt、隐藏推理或敏感日志。
- [ ] 对现有模拟算法的修改仅限必要的 Observer 埋点或已单独评审的修复。
- [ ] 相关文档、迁移说明和本地启动方式已经更新。

## 17. 推荐实施顺序

1. 修复模型上下文超限并完成小规模真实运行。
2. 建立 Run Registry、生命周期和独立 Process Manager。
3. 建立 RuntimeEvent、Event Store、Snapshot Reducer，并在仿真主流程埋点。
4. 引入 FastAPI，先迁移现有只读接口，再增加控制 API 和 SSE。
5. 完成“新建实例 → 启动 → Observatory → 结果表”主流程。
6. 补齐 Agent Group、Market Environment、模型和数据源管理。
7. 增加 Replay、跨实验分析和生产化能力。

