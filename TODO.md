# TwinMarket Application TODO

> 更新时间：2026-09-23
>
> 当前目标：先交付一个单用户、可创建并观察真实仿真实例的稳定版本。
> FastAPI 后端从旧 `studio/` 中拆分为顶层独立服务；同时新建一个基于 shadcn/ui
> 设计体系的独立前端。Web 版本用于展示和验证，后续产品形态为 Electron 本地桌面应用。
>
> 核心闭环：`创建实例 → 启动运行 → Runtime Observatory → 查看真实结果`。

## 0. 范围与状态

### 0.1 首个稳定版范围

- 单用户、单机运行。
- 同时最多运行 1–2 个仿真实例。
- 顶层 `backend/` 提供独立 FastAPI 服务，不再依赖 `studio` Python 模块。
- 顶层 `frontend/` 使用 React、TypeScript、Vite、Tailwind CSS 和 shadcn/ui。
- 新前端通过 HTTP/SSE 连接本机或单台展示服务器上的 FastAPI。
- FastAPI 负责控制、查询和事件推送，仿真由独立 Python Worker 执行。
- SQLite、CSV、JSON、`events.jsonl` 和运行目录继续作为首版持久化方案。
- 旧 `studio/` 在功能对等前保留为迁移参考，不作为最终产品前端。
- Web 展示版不承担多用户生产平台职责。

### 0.2 不阻塞首个稳定版

- 多用户、组织、角色、实验所有权和复杂权限。
- PostgreSQL、Redis、任务队列和跨机器 Worker。
- 多租户资源隔离、复杂配额和计费。
- Runtime Replay 播放控制和多实验对比。
- Worker 性能甘特图、Token 成本分析和完整模型对话展示。
- 社交图动画和高级分析页面。

### 0.3 目标目录结构

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── schemas/
│   ├── services/
│   └── workers/
└── tests/

frontend/
├── src/
│   ├── components/ui/       # shadcn/ui primitives
│   ├── features/runs/
│   ├── features/runtime/
│   ├── features/results/
│   ├── lib/
│   └── routes/
└── tests/

runtime/                     # 仿真与后端共享，不依赖 UI
simulation.py
studio/                      # 迁移期间保留的旧实现
```

### 0.4 当前完成度判断

- Runtime、FastAPI 原型和旧 Studio UI 的基础功能约完成 75%–85%。
- 按“独立后端 + 全新 shadcn 前端”的新目标计算，整体约完成 55%–65%。
- 已具备可演示原型，但目录解耦、新前端和端到端稳定性尚未完成。
- 首个新 Web 展示稳定版预计还需 10–18 个有效开发日。
- Electron 原型在 Web 稳定版之后预计还需 3–5 个有效开发日。

## 1. 已完成

### 1.1 只读 Studio 基线

- [x] React + Vite Studio 已具备 Experiment、Agent、Market、Setting、Documentation 页面。
- [x] 原有只读服务可访问已有运行目录、SQLite、配置摘要和已发布文档。
- [x] SQLite 只读连接启用 `mode=ro` 和 `PRAGMA query_only=ON`。
- [x] 日志、配置和 RuntimeEvent 具备基础脱敏。
- [x] 已有运行准备、新闻索引构建和运行监控脚本。

### 1.2 模型请求修复

- [x] 根据模型上下文窗口和估算输入 token 动态收缩 `max_tokens`。
- [x] 为 provider/model 定义上下文长度、最大输出和参数能力。
- [x] 区分不可重试的 4xx 与可重试的超时、限流和 5xx。
- [x] 避免对确定性 400 连续重试。
- [x] 记录 provider、model、request ID、latency、token、attempt 和错误代码。
- [x] 使用 10 Agent、低激活概率完成 2 个交易日 smoke run。

> 说明：旧的 100 Agent 产物只包含部分日期，日志中仍存在上下文超限 HTTP 400，不能作为完整验证证据；重新验证已移入 P2，不阻塞首个展示稳定版。

### 1.3 运行目录契约

- [x] 每个 `run_id` 使用不可冲突的 `runs/<run_id>/` 目录。
- [x] 创建时保存脱敏参数、随机种子、代码版本和启动命令摘要。
- [x] 保存 Agent 模板、belief、行情、交易日、新闻和模型配置的 SHA-256 指纹。
- [x] 使用 `manifest.json` 固化输入与配置快照。
- [x] 使用 `state.json` 保存 checkpoint 和下一合法续跑日期。
- [x] 续跑时清理边界日期及之后的数据库记录和日期产物。
- [x] 使用运行锁和独立数据库防止多个进程写入同一实例。

### 1.4 Run Registry 与控制面

- [x] SQLite Run Registry 保存配置、目录、生命周期、健康状态、PID、退出码、失败原因、心跳和最后事件 ID。
- [x] 生命周期支持 `draft / queued / running / stopping / completed / failed / cancelled`。
- [x] 健康状态支持 `healthy / degraded / stale / unavailable`。
- [x] 支持创建、读取、编辑草稿、复制、归档和安全删除草稿。
- [x] 支持启动、停止和从 checkpoint 续跑。
- [x] 启动前校验输入文件、参数范围、数据文件和运行目录。
- [x] 启动和停止的重复请求具备基础幂等保护。
- [x] 停止时先发送 SIGTERM，超时后升级为 SIGKILL。
- [x] 通过本机并发上限防止启动过多任务。
- [x] 仿真在独立 Worker/子进程中运行，不占用 HTTP 请求协程。
- [x] stdout/stderr 写入运行目录下的 `simulation.log`。
- [x] 非法生命周期转换返回 409。

### 1.5 RuntimeEvent 基础设施

- [x] 建立独立的 `runtime/event.py`、`observer.py`、`event_store.py`、`snapshot.py` 和 `schemas.py`。
- [x] 定义不可变 `RuntimeEvent` 和固定枚举。
- [x] 支持 `stage_started / stage_completed / stage_skipped / stage_failed / stage_retrying`。
- [x] 支持 `run / day / agent / market / social / artifact / system` scope。
- [x] Agent 固定为 `State → Perception → Interpretation → Decision → Action → Commit`。
- [x] Day 固定为 `Prepare → Agents → Market → Social → Commit`。
- [x] Event Store 追加写入 `events.jsonl` 并维护有限内存缓冲。
- [x] 单个 Run 内的 `event_id` 严格递增。
- [x] Snapshot Reducer 可从持久事件重建 Run、Day、Worker 和 Agent 状态。
- [x] Observer 写入失败不会改变市场算法结果，并可将 health 降为 degraded。
- [x] Run、自然日、Agent 六阶段、Market 和 Social 已接入基础埋点。
- [x] 非交易日会保留完整 Day Cycle，并将 Market 标记为 skipped/market_closed。
- [x] Agent 局部失败不会自动将整个 Run 标记为 failed。

### 1.6 FastAPI 与实时接口

- [x] 提供 `/health/live` 和 `/health/ready`。
- [x] 提供创建、列表、详情、编辑、复制、启动、停止、续跑、归档和删除 Run API。
- [x] 提供 `/runtime` 当前快照接口。
- [x] 提供 `/events` SSE 增量事件接口。
- [x] SSE 后端支持 `Last-Event-ID` 和 `last_event_id` 查询参数。
- [x] 提供单 Agent Runtime、Diagnostics 和独立日志接口。
- [x] 完成的 Run 可以仅从 `events.jsonl` 重建 Snapshot。
- [x] 普通文本日志不作为产品状态事实源。
- [x] 原有 Agent、Market、Documentation 只读能力已接入 FastAPI。

### 1.7 创建与 Runtime Observatory UI

- [x] UI 可以创建草稿实例并生成稳定 `run_id`。
- [x] 创建后进入 `/studio/runs/{run_id}`。
- [x] 表单包含名称、人数、起止日期、并发、激活概率、技术面概率和随机种子。
- [x] 高级参数默认折叠。
- [x] UI 可以启动、停止和续跑实例。
- [x] 页面显示 draft、queued、running、stopping、completed、failed 和 cancelled。
- [x] 创建 `LiveSimulationView`，包含 Run Header、Day Cycle、Focus Agent、Worker Lanes、Today Summary、Recent Events 和 Diagnostics Drawer。
- [x] 分开展示 Run、Day 和 Agent 状态。
- [x] 固定展示 Day 五阶段和 Agent 六阶段。
- [x] 展示阶段状态、耗时、substage、摘要和 attempt。
- [x] Interpretation 不展示隐藏推理或完整原始模型输出。
- [x] Decision、Action 和 Commit 使用不同语义说明。
- [x] 默认 Auto Follow 最近活跃 Agent；手动选择 Worker 后关闭 Auto Follow。
- [x] Today Summary 汇总 Buy、Sell、Hold、Orders、Posts、Interactions 和 Failures。
- [x] Diagnostics 汇总失败、重试和慢阶段。
- [x] 状态同时使用文字表达，不只依赖颜色。
- [x] 支持 `prefers-reduced-motion`。

### 1.8 真实结果查询

- [x] 提供每日汇总、成交、订单、Agent、Social 和产物清单 API。
- [x] 成交、订单和 Agent API 支持服务端分页。
- [x] 成交和订单支持日期、资产过滤。
- [x] 成交和订单支持 CSV/JSON 流式导出。
- [x] UI 在 Run 完成后展示每日汇总、成交明细和 Agent 结果三个标签页。
- [x] UI 展示结果来源和最后读取时间。
- [x] 缺失结果显示 unavailable，不虚构为 0。

### 1.9 当前自动化检查

- [x] BaseAgent 覆盖上下文超限、确定性 400、限流、超时和 provider 参数测试。
- [x] 运行准备脚本覆盖用户 ID、belief、数据库完整性和拒绝覆盖测试。
- [x] checkpoint 清理边界具备测试。
- [x] RuntimeEvent 覆盖追加、恢复、顺序、脱敏和 Observer 写入失败测试。
- [x] Snapshot Reducer 覆盖重复事件和 Agent 局部失败测试。
- [x] Registry 覆盖基础生命周期和幂等转换测试。
- [x] API 覆盖创建草稿、manifest、runtime 和非法续跑测试。
- [x] 保留原有只读数据库、路径边界和日志脱敏测试。
- [x] `script/check.sh` 统一运行 Python 编译、Python 测试、Shell 检查、Sites Worker 测试和前端构建。
- [x] 2026-09-23 本地执行 `bash script/check.sh` 全部通过。

## 2. P0 — Web 展示稳定版剩余工作

### 2.1 后端从 Studio 拆分

- [x] 在仓库顶层建立独立 `backend/` Python package 和测试目录。
- [x] 将 `studio/backend/app.py` 迁移为 `backend/app/main.py`。
- [x] 将 Registry、Process Manager、结果查询和 Worker 分别迁入独立模块。
- [x] 将 `studio/server.py` 中仍被 FastAPI 使用的 catalog、documentation、Agent、Market 和日志读取逻辑抽入后端 service。
- [x] 后端生产代码不再 import `studio.*`。
- [x] `runtime/` 保持框架无关，可同时被 `simulation.py` 与独立后端导入。
- [x] 更新 Worker 启动模块、命令摘要和所有 Python import 路径。
- [x] 将后端测试迁到 `backend/tests/`，保留原有只读安全与 Runtime 测试。
- [x] 为后端建立独立依赖文件和启动命令。
- [x] 通过环境变量配置项目根目录、数据目录、运行目录、Registry 路径和允许的前端 origin。
- [x] 保证迁移前后的 API 路径、响应结构和错误状态兼容。
- [x] 更新 `script/check.sh`，分别检查核心仿真、独立后端和前端。

### 2.2 新 shadcn 前端基础

- [x] 在仓库顶层建立独立 `frontend/` 项目。
- [x] 使用 React + TypeScript + Vite + Tailwind CSS + shadcn/ui。
- [x] 建立颜色、字体、间距、圆角、阴影、状态色和图表色设计 tokens。
- [x] 配置深色/浅色主题，并确保 Runtime 状态语义不只依赖颜色。
- [x] 建立 App Shell、侧边导航、顶部栏、页面容器和响应式布局。
- [x] 建立 Button、Card、Badge、Tabs、Dialog、Drawer、Form、Table、Skeleton、Toast 等基础组件。
- [x] 建立 API client、统一错误结构、请求取消和 loading/empty/error 状态。
- [x] 从后端 OpenAPI schema 生成或维护类型安全的 TypeScript API 类型。
- [x] 建立 SSE hook，负责连接、cursor、重连、去重和清理。
- [x] 配置开发代理、生产 API base URL 和 Electron 本地服务地址注入点。

### 2.3 新前端功能迁移

- [x] 实现 `/runs` 实例列表和状态筛选。
- [x] 实现 `/runs/new` 创建实例页面。
- [x] 实现 `/runs/{run_id}` 实例详情与启动入口。
- [x] 实现 `/runs/{run_id}/live` Runtime Observatory。
- [x] 实现 `/runs/{run_id}/results` 结果数据表。
- [x] 迁移 Run Header、Day Cycle、Focus Agent、Worker Lanes、Today Summary、Recent Events 和 Diagnostics。
- [x] 迁移每日汇总、成交明细和 Agent 结果三个首要结果视图。
- [x] 迁移必要的 Agent、Market 和 Documentation 只读入口；非核心高级页允许延后。
- [x] 新前端达到核心闭环功能对等后，再停止维护旧 Studio UI。
- [x] Web 和 Electron 都只使用新 `frontend/`，不在两个 UI 代码库中重复开发。

### 2.4 真实闭环验收

- [ ] 从 UI 创建一个新的 10 Agent、2 交易日实例。
- [ ] 点击启动后 2 秒内进入 queued/running，刷新页面不影响任务。
- [ ] 完整观察 Day 五阶段和任意 Agent 六阶段。
- [ ] 验证 Agent 处理结束后依次进入 Market、Social 和 Commit。
- [ ] 验证非交易日显示 Market Closed，且 Social/Commit 继续执行。
- [ ] 验证运行完成后可以读取真实每日汇总、成交和 Agent 结果。
- [ ] 验证配置、事件、数据库和结果文件的日期与最终状态一致。
- [ ] 验证当前模型配置下不再出现上下文超限 400 或确定性重复重试。

### 2.5 生命周期与故障恢复

- [ ] Worker 运行期间周期性更新 heartbeat，而不是只在开始和结束时更新。
- [ ] 根据 PID、heartbeat、结束事件和退出码识别 stale/僵尸 Worker。
- [ ] FastAPI 重启后恢复 queued/running/stopping Run 的正确状态。
- [ ] `resume` 重复请求保持幂等，不启动第二个 Worker。
- [ ] 验证停止流程最终进入 cancelled，并保留已有事件和产物。
- [ ] 验证失败后从 `checkpoint.next_date` 续跑，不重复提交已完成日期。
- [ ] 应用关闭或服务退出时不遗留无法识别的子进程。

### 2.6 RuntimeEvent 与 SSE 稳定性

- [ ] Snapshot API 改为增量缓存/持久快照，避免每次从第一个事件全量扫描。
- [ ] 前端保存已消费事件 ID，并验证 EventSource 自动重连后的补发行为。
- [ ] 页面刷新后先加载 Snapshot，再从正确 cursor 接收增量事件。
- [ ] 增加 Event Store 截断文件恢复和并发写入测试。
- [ ] 验证慢 SSE 客户端不会阻塞 Worker 或 Event Store。
- [ ] 对完成 Run 验证 Snapshot 重建结果与运行结束时一致。

### 2.7 创建与运行 UI 收尾

- [ ] 创建表单提供模型配置和必要数据源选择，或明确显示首版使用的固定配置。
- [ ] 提交前显示服务端校验结果、预计 Agent 数和日期规模。
- [ ] 启动前显示确认信息并防止重复点击。
- [ ] 草稿允许继续编辑；已启动 Run 只能复制后修改。
- [ ] Run Header 补充交易日序号、已处理 Agent、LLM 调用数、累计耗时和最后事件时间。
- [ ] Agent Processing 显示 completed、running、queued、retrying、failed 和 inactive 数量。
- [ ] 慢 LLM 阶段持续显示 elapsed、model 和 attempt。
- [ ] Recent Events 支持 scope、stage、Agent 和错误级别过滤。
- [ ] UI 覆盖 loading、empty、unavailable、stale、failed 和 completed 状态。
- [ ] 验证 390px、1024px 和桌面宽度不出现页面级横向溢出。
- [ ] 验证键盘焦点、状态非颜色表达和 reduced motion。

### 2.8 结果页收尾

- [ ] 后端成交和订单查询增加明确排序参数。
- [ ] 结果 UI 增加分页，不在浏览器加载完整大表。
- [ ] 结果 UI 增加日期、Agent、资产和行为类型筛选。
- [ ] 结果 UI 标明来源日期，并区分初始化历史数据与本次模拟数据。
- [ ] 完成后提供明显的结果入口，同时保留返回 Observatory 的能力。

### 2.9 发布前自动化测试

- [ ] 集成测试：创建 → 启动子进程 → 收到事件 → 正常完成。
- [ ] 集成测试：停止 → cancelled → 已有产物仍可读。
- [ ] 集成测试：失败 → checkpoint 续跑 → 不重复日期。
- [ ] 集成测试：API 重启 → 活跃 Worker 恢复或正确标记 stale。
- [ ] 集成测试：SSE 断开 → Last-Event-ID 补发 → Snapshot 一致。
- [ ] 集成测试：Agent 局部失败 → Run 继续且 health=degraded。
- [ ] UI 测试：创建校验、启动确认和重复点击保护。
- [ ] UI 测试：Run/Day/Agent 状态、Auto Follow 和手动 Focus Agent。
- [ ] UI 测试：结果分页、筛选、排序和导出。

### 2.10 Web 展示部署

- [ ] 明确 Web 展示拓扑：静态前端 + FastAPI + 本机 Worker + 持久运行目录。
- [ ] 为 FastAPI 和 Worker 提供可重复的启动/停止脚本或容器配置。
- [ ] 将 Run Registry 和 `runs/` 挂载到持久目录。
- [ ] 使用环境变量或受限配置文件提供模型密钥，不写入仓库、事件或前端响应。
- [ ] FastAPI 仅开放必要路径；下载和配置路径继续使用 allowlist。
- [ ] 如果展示地址可从公网访问，增加简单访问口令或反向代理访问控制。
- [ ] 配置 `/health/live`、`/health/ready` 和基本故障日志。
- [ ] 记录部署、升级、回滚和清理运行目录的方法。
- [ ] 在干净环境执行依赖安装、启动、真实 smoke run 和生产构建。

## 3. P1 — Electron 桌面版

### 3.1 架构与进程生命周期

- [ ] Electron Renderer 复用新的顶层 `frontend/`，不复用旧 Studio UI。
- [ ] Electron Main 启动 FastAPI/Python sidecar，并等待 `/health/ready`。
- [ ] FastAPI 仅监听 `127.0.0.1`，使用随机可用端口或受控固定端口。
- [ ] Renderer 通过受限 preload API 获取本地服务地址，不开放通用 Node 权限。
- [ ] Electron 退出时温和关闭 API；运行中的仿真实例按明确策略停止或继续。
- [ ] 检测并处理端口占用、Python sidecar 启动失败和异常退出。
- [ ] 防止重复启动多个 API/Worker 管理器。

### 3.2 本地数据与设置

- [ ] 将 Registry、`runs/`、缓存和日志迁移到 Electron `userData` 目录。
- [ ] 首次启动时完成目录初始化和版本检查。
- [ ] 提供模型 endpoint、model 和 API key 设置界面。
- [ ] API key 使用系统凭据存储或等价安全方案，读取接口永不返回明文。
- [ ] 提供选择/打开运行目录、导出结果和诊断包的入口。
- [ ] 定义旧版本运行目录和 Registry 的迁移策略。

### 3.3 打包与发布

- [ ] 决定 Python runtime、依赖和资源文件的 sidecar 打包方式。
- [ ] 打包后验证 SQLite、数据文件、配置和动态 Python 依赖均可定位。
- [ ] 建立 Electron 开发、打包和 smoke test 命令。
- [ ] 验证首次启动、创建实例、运行、停止、续跑和退出清理。
- [ ] 生成 macOS 可分发包；根据实际分发渠道决定是否签名和公证。
- 自动更新、崩溃上报和 Windows/Linux 包不阻塞首个 Electron 版本。

## 4. P2 — 后续增强

- [ ] 完成 100 Agent、完整 10 交易日性能与稳定性验证。
- [ ] 增加 Agent Group 创建、复制、版本化、筛选和参数编辑。
- [ ] 增加 Market Environment 创建、数据导入和交易规则配置。
- [ ] 增加模型连接测试、能力检查、熔断和成本摘要。
- [ ] 支持按 Run、Day、Agent、stage 和错误代码检索 RuntimeEvent。
- [ ] 增加事件与结果的 correlation ID 跳转和审计链路。
- [ ] 增加 Runtime Replay 和跨实验对比。
- [ ] 增加事件归档、运行目录保留期限和安全清理。

## 5. Web 展示稳定版 Definition of Done

- [ ] FastAPI、Worker、Registry 和查询服务位于独立 `backend/`，生产代码不依赖 `studio.*`。
- [ ] 用户核心闭环全部运行在新的 shadcn/ui `frontend/` 中。
- [ ] 旧 Studio 不再是 Web 部署或 Electron 运行时依赖。
- [ ] 用户可以从 UI 创建、启动并观察一个真实 10 Agent、2 交易日实例。
- [ ] 刷新或短暂断线不会影响 Worker，页面能恢复最新状态和遗漏事件。
- [ ] 用户可以停止运行，并获得 cancelled 状态和仍可读取的已有产物。
- [ ] 失败 Run 可以从合法 checkpoint 续跑且不重复日期。
- [ ] Run 完成后可以查看真实每日汇总、成交明细和 Agent 结果。
- [ ] 产品状态只依赖 Registry、Snapshot 和 RuntimeEvent，不解析普通日志推断状态。
- [ ] Agent 局部失败只降低 health，不错误终止整个 Run。
- [ ] 页面和接口不泄露密钥、私有 endpoint、完整 prompt、隐藏推理或原始敏感模型内容。
- [ ] 核心端到端测试、现有单元测试、Shell 检查和生产构建全部通过。
- [ ] 干净环境可以按照文档完成安装、启动、运行和停止。

## 6. 推荐实施顺序

1. 先建立顶层 `backend/`，迁移 FastAPI、services、Worker 和测试，并消除所有 `studio.*` 生产依赖。
2. 冻结 API 契约，建立顶层 TypeScript + shadcn/ui `frontend/`、API client 和 SSE hook。
3. 按“实例列表 → 创建 → Observatory → 结果页”顺序迁移核心闭环。
4. 完成 10 Agent 真实闭环验收，修复发现的生命周期和 UI 问题。
5. 增加 heartbeat、stale 检测、服务重启恢复、续跑幂等和 Snapshot 增量化。
6. 补齐结果分页筛选、错误状态、关键集成测试和 UI 测试。
7. 完成新前端 + 独立后端的 Web 展示部署、干净环境 smoke run 和发布文档。
8. 核心功能对等后冻结旧 Studio，以 `frontend/ + backend/ + runtime/` 进入 Electron。
