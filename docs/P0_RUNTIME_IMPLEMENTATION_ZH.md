---
title: P0 Runtime Observatory 后端实现契约
published: true
category: 工程说明
order: 35
---

# P0 Runtime Observatory 后端实现契约

本文记录 P0 已实现的后端行为、API 语义与数据口径。前端位于 `studio/frontend/`，控制面位于 `studio/backend/`，框架无关的运行时事件模块位于 `runtime/`。普通 `simulation.log` 仅用于诊断；产品状态由 `events.jsonl` 中的 RuntimeEvent 重建。

## 3.1 修复模型请求阻塞

模型能力、上下文预算与 4xx/超时/限流分类沿用 `Agent.py` 的 provider-aware 请求路径。调用指标以结构化日志和 RuntimeEvent 摘要呈现，不返回密钥、原始 prompt 或隐藏推理。

## 3.2 固化运行目录契约

创建草稿会原子创建 `runs/<run_id>/`，拒绝任何同名目录。`manifest.json` 保存经脱敏的参数、输入文件 SHA-256 指纹与 checkpoint 规则；`state.json` 保存下一合法续跑日。独占 `run.lock`、独立数据库和日期边界清理共同阻止两个进程写入同一运行。

## 3.3 建立回归测试

`script/check.sh` 统一执行 Python 编译、Python 单元测试、Shell 语法检查、Studio Worker 测试与 Vite 构建。RuntimeEvent、Registry、API 草稿行为均有自动化覆盖。

## 4.1 持久化 Run 实体

`studio/backend/registry.py` 使用 SQLite 持久化运行 ID、名称、时间、生命周期、健康、配置、输出目录、checkpoint、PID、退出码、失败原因、心跳和最后事件 ID。服务查询会核对 PID；活动 Worker 消失且没有结束标记时标为 failed，停止中的 Worker 消失则标为 cancelled。

## 4.2 运行控制

`ProcessManager` 只派发脱离 HTTP 请求的子 Worker。start/stop 对 queued、running、stopping 的重复调用保持幂等；启动先校验输入、目录、范围和并发配额；停止先发送 SIGTERM，十秒后才升级 SIGKILL，并记录原因。草稿可编辑、复制或安全删除，已启动运行只能复制。

## 4.3 Run API

控制 API 为 `POST /api/runs`、`GET /api/runs`、`GET/PATCH /api/runs/{id}`、`POST /start|stop|resume|archive|copy` 及草稿 `DELETE`。非法状态迁移返回 409；参数或前置资源不合法返回 422；未知运行返回 404。

## 5.1 Runtime 模块

`runtime/event.py` 定义 frozen RuntimeEvent；`observer.py` 提供 best-effort 五种 emit；`event_store.py` 追加 JSONL 并维护热缓冲；`snapshot.py` 用持久事件归约 Run、Day、Worker 和 Agent 状态；`schemas.py` 固定枚举和脱敏。观测写入失败只将 health 降为 degraded，绝不影响市场算法。

## 5.2 事件契约

每条事件在单 Run 内拥有严格递增 `event_id`，并包含 scope、stage、日期、Agent/Worker、时间、attempt、受限长度的输入/输出摘要、消息、错误代码和脱敏错误摘要。事件类型固定为 `stage_started/completed/skipped/failed/retrying`；Agent 一级阶段固定为六槽位，Day 固定为五槽位。

## 5.3 仿真埋点

`simulation.py` 在 Run、自然日 Prepare/Agents/Market/Social/Commit 和 Agent State/Perception/Interpretation/Decision/Action/Commit 处发射事件。非交易日将 Market 以 `skipped + market_closed` 发射。Agent 局部异常生成 agent failure，运行仍可继续，完成时 health 会降级。

## 6. Runtime API 与实时传输

`GET /runtime` 从 JSONL 重建快照；`GET /events` 为 SSE，读取 `Last-Event-ID` 并从持久文件补发后进入实时流；`GET /agents/{agent_id}/runtime`、`/diagnostics` 和独立 `/logs` 供观察与诊断。慢 SSE 客户端只读取 EventStore 缓冲/文件，不会阻塞模拟线程。

## 7.1 新建实例

`RunComposer` 提交名称、人数、日期、并发、激活概率、技术面概率和随机种子到 `POST /api/runs`。服务端做范围、日期和路径边界校验，成功后立即进入 `/studio/runs/{run_id}`；密钥字段没有 API 回显路径。

## 7.2 启动与状态反馈

启动按钮调用控制 API 后转入独立 Worker；刷新页面只重连 API/SSE，不接触进程。界面以文字和 Tag 显示 draft、queued、running、stopping、completed、failed、cancelled，并提供停止、诊断和合法续跑入口。

## 8.1 页面骨架

`LiveSimulationView` 固定为 Run Header、Day Cycle、Focus Agent、Worker Lanes、Today Summary/Recent Events 与 Diagnostics Drawer，避免把 RuntimeEvent 当作终端日志滚动展示。

## 8.2 Run Header

Header 分别输出 Run 生命周期、健康度、模拟日期、事件水位和已观察 Agent 数，不将三种尺度压成单一进度条。Stop 与 Diagnostics 直接连接控制面。

## 8.3 Day Cycle

Day Cycle 固定显示 Environment、Agent Processing、Market、Social、Commit。槽位仅更新状态、摘要和 substage；`market_closed` 显示为已跳过而不是隐藏市场。

## 8.4 Focus Agent Pipeline

Agent 管线固定展示六个槽位并显示状态、耗时、attempt 和摘要。Interpretation 只提示已脱敏的 belief/信号摘要；Decision 与 Action 明确标注认知意图和可执行动作；Commit 标注持久事实。

## 8.5 Worker Lanes 与 Agent Queue

Snapshot reducer 按稳定 `worker_id` 保留活跃 Worker，而非假设串行。点击 Worker 会选择 Focus Agent 并关闭 Auto Follow；没有活跃 Worker 时界面退化为 Current Agent 文案。

## 8.6 Today Summary 与事件流

今日摘要来自 Snapshot 的 Agent 状态计数；Recent Events 只保留最近高层事件。失败、重试和慢阶段进入 Diagnostics，而不是与普通运行事实混排。

## 8.7 动效与可访问性

运行槽位采用轻度 pulse，并受 `prefers-reduced-motion` 禁用。所有状态同时有文字/Tag；Agent、Worker、事件条目使用原生可聚焦按钮，可用键盘选择。

## 9.1 结果 API

`/results/summary` 读取 `simulation_results/*/daily_summary_*.csv`；`/trades`、`/orders` 分页读取真实交易记录；`/agents` 查询运行目录的 SQLite 快照；`/social` 与 `/artifacts` 仅报告真实产物。缺失输入返回空结果加 `unavailable` 来源，不用 0 伪造。

## 9.2 结果 UI

完成的 Run 在 Observatory 内显示每日汇总、成交明细、Agent 结果三个首要表。每张表标明来源和读取时间，数据来自 API 分页结果；用户仍可留在同一页面查看运行事件与诊断。
