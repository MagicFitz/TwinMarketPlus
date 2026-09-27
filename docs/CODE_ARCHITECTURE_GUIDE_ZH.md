---
title: TwinMarket 代码架构、数据流与扩展指南
published: true
category: 工程说明
order: 30
---

# TwinMarket 代码架构、数据流与扩展指南

本文面向两类读者：

- 第一次阅读 TwinMarket，希望快速建立完整心智模型的开发者；
- 准备新增运行参数、Agent 行为、撮合规则、Runtime 状态、后端 API 或前端页面的维护者。

本文基于 2026-09-25 的当前工作树，覆盖顶层 `frontend/`、`backend/`、`runtime/`、`simulation.py`、`trader/`、`util/`、根目录 `Agent.py`，以及被这些模块直接调用的 `script/prepare_simulation_run.py` 和 `script/run_contract.py`。旧的 `studio/` 只作为迁移历史存在，不是当前前后端实现来源。

文档描述的是“代码现在实际怎样运行”，并在后半部分单列当前限制和推荐改法。阅读代码时应优先相信当前实现和测试，而不是早期设计文档中的理想行为。

## 1. 一分钟心智模型

TwinMarket 不是一个把 Python 对象直接暴露给网页的单体应用。它分为四个边界：

```text
浏览器 React SPA
    │  REST / SSE
    ▼
FastAPI 控制面与只读查询面
    │  SQLite Registry + 子进程 + 运行目录
    ▼
backend.worker
    │  命令行参数
    ▼
simulation.py
    ├─ trader/：Agent 决策、提示词、模型调用辅助、撮合与结算
    ├─ util/：用户/论坛数据库、关系图、向量新闻库
    └─ runtime/：事件写入
```

最重要的三条原则是：

1. **前端不直接引用 Python 内核。** 所有数据都通过后端 HTTP API 获取。
2. **后端不在请求线程中运行仿真。** 它启动独立 Worker，Worker 再启动 `simulation.py`。
3. **后端与内核的稳定边界是运行目录。** 生命周期索引在 Registry；领域事实、事件和结果在 `runs/<run_id>/`。

因此，排查问题时先判断问题属于哪一种：

| 现象 | 优先检查 |
| --- | --- |
| 按钮是否可点、页面是否刷新 | 前端路由、页面状态、`api.ts`、HTTP 返回 |
| Run 为何是某个状态 | Registry、`ProcessManager`、Worker 退出码 |
| Runtime 页面为何显示某阶段 | `events.jsonl`、Reducer、前端 Runtime 页面 |
| 某 Agent 为何做出决策 | 用户快照、belief、图、新闻、Prompt、模型响应 |
| 市场结果为何如此 | 决策 JSON、订单 JSON、撮合、结算和当日 DB 快照 |
| 续跑为何重复或漏算 | `state.json`、Registry checkpoint、清理边界 |

## 2. 目录与职责

### 2.1 顶层模块

| 路径 | 当前职责 | 主要消费者 |
| --- | --- | --- |
| `frontend/` | React SPA，Run 创建/控制/观察、结果、Agent、市场、设置、文档 | 浏览器或 Electron 壳 |
| `backend/` | FastAPI、Run Registry、进程编排、只读查询、结果与设置服务 | 前端 |
| `runtime/` | 与 Web 无关的事件、事件存储、脱敏、快照归约 | 内核写入，后端读取 |
| `simulation.py` | 仿真 CLI 与自然日主循环 | Worker、CLI 脚本 |
| `Agent.py` | 模型 Provider 适配、能力判断、上下文预算和重试 | `PersonalizedStockTrader` |
| `trader/` | Agent 策略、Prompt、响应解析、撮合和结算 | `simulation.py` |
| `util/` | 用户 DB、论坛 DB、关系图、FAISS 新闻索引 | `simulation.py`、`trader/` |
| `script/` | Run 准备、CLI 运行契约、检查脚本 | Worker、开发者 |
| `data/` | 模板数据库、新闻、行情、交易日历和索引 | 准备脚本、内核 |
| `config/` | 语言模型与嵌入模型配置 | Agent、向量检索、设置 API |
| `runs/` | 每次运行的独占状态与结果 | Worker、内核、后端查询 |
| `docs/` | 带发布 frontmatter 的应用内文档 | 后端文档服务、前端文档页 |

### 2.2 依赖方向

推荐把依赖理解为单向流：

```text
frontend
   ↓ HTTP
backend/app
   ↓ service / registry / process
backend.worker
   ↓ CLI
simulation
   ↓
trader + util

simulation ──写──> runtime EventStore
backend    ──读──> runtime EventStore / SnapshotReducer

simulation ──写──> run 目录中的 DB / JSON / CSV
backend    ──读──> run 目录中的 DB / JSON / CSV
```

例外是共享的 `runtime/`：它同时被内核和后端引用，但不应反向依赖 FastAPI 或 React。保持这一点可以让事件契约独立测试。

### 2.3 关键 import 与调用关系

- `backend/app/main.py` 装配 `RunRegistry`、`ProcessManager`、Runtime 和各查询服务。
- `backend/process_manager.py` 使用 `subprocess.Popen` 启动 `python -m backend.worker`。
- `backend/worker.py` 首次运行调用 `script/prepare_simulation_run.py`，随后启动 `simulation.py`。
- `simulation.py` 引用：
  - `runtime.EventStore`、`runtime.RuntimeObserver`；
  - `Agent.BaseAgent`；
  - `trader.trading_agent.PersonalizedStockTrader`；
  - `trader.matching_engine`；
  - `trader.utility.init_system`；
  - `util.UserDB` 与 `util.ForumDB`；
  - `script.run_contract` 中的原子 JSON 写入和按日清理函数。
- `trader/trading_agent.py` 引用 `InformationDB`、UserDB/ForumDB、`TradingPrompt`、响应解析工具和 `BaseAgent`。
- `backend/services/*` 原则上不调用交易算法，只安全读取已经落盘的事实。

## 3. 两条运行入口

### 3.1 当前 Web/后端入口

```text
POST /api/runs
  → create_run()
  → draft

POST /api/runs/{id}/start
  → ProcessManager.start()
  → queued
  → python -m backend.worker --run-id ...
  → running
  → prepare_simulation_run.py
  → python simulation.py ...
  → completed / failed
```

这是 `frontend/` 使用的主路径。Run 元数据使用 `backend/registry.py`，运行清单由 `backend/run_service.py` 创建。

### 3.2 CLI 入口

```text
script/run.sh
  → script/run_contract.py create / launch
  → prepare_simulation_run.py
  → simulation.py
```

CLI 有自己的一套 v1 manifest/state/lock 契约；Backend 使用的是自己的 v2 Run 清单和 Registry。两条路径最终执行相同内核，但创建、锁、续跑和状态同步并非同一实现。

维护时必须明确改动需要支持哪条路径。若是通用仿真参数，通常需要同时修改 Backend Worker 和 `script/run.sh`；若只改一条，另一条会产生行为漂移。

## 4. 持久化边界与数据模型

### 4.1 全局输入

默认输入包括：

- `data/sys_1000.db`：用户、策略、股票资料和初始历史状态模板；
- `data/stock_data.csv`：真实行情输入；
- `data/trading_days.csv`：交易日历；
- `data/sorted_impact_news.pkl`：按日新闻；
- `data/InformationDB_news_2023/`：FAISS 新闻索引及元数据；
- `util/belief/*.csv`：初始 belief；
- `config/api.yaml`：语言模型配置；
- `config/embedding.yaml`：嵌入模型配置。

`TWINMARKET_DATA_DIR` 可以改写多数数据根路径，但当前并非所有撮合代码都完整遵循它，详见“当前限制”。

### 4.2 Run Registry

`backend/registry.py` 使用单表 SQLite，保存控制面需要快速查询的字段：

```text
run_id, name, description
created_at, started_at, ended_at
status, health
config_json
output_dir
checkpoint_json
pid, exit_code, failure_reason
last_heartbeat, last_event_id
archived
```

Registry 是生命周期索引，不是完整仿真事实库。新增普通实验参数优先放入 `config_json`；新增结构化列时必须考虑已有 SQLite 的显式迁移，因为 `CREATE TABLE IF NOT EXISTS` 不会升级旧表。

### 4.3 单 Run 目录

Backend 创建的典型目录如下：

```text
runs/<run_id>/
├─ manifest.json
├─ state.json
├─ events.jsonl
├─ simulation.log
├─ user_<count>.db
├─ forum_<count>.db
├─ belief_<count>.csv
├─ graphs/
│  └─ <name>_<date>.pkl
├─ conversation_records/
│  └─ <date>/<agent_id>.json
├─ trading_records/
│  ├─ <date>.json
│  └─ <date>_orders.json
├─ reaction_records/<date>.json
├─ post_records/<date>.json
└─ simulation_results/
   └─ <date>/
      ├─ daily_summary_<date>.csv
      ├─ transactions_<date>.csv
      ├─ large_order_flow_<date>.csv
      └─ order_books/...
```

各文件的权威含义：

| 载体 | 含义 |
| --- | --- |
| `manifest.json` | 创建时参数、代码版本、输入指纹和命令摘要，用于审计 |
| `state.json` | 内核在完整提交一个自然日后写入的安全续跑点 |
| Registry checkpoint | 控制面当前保存的续跑点；当前可能落后于 `state.json` |
| `events.jsonl` | 只追加的 RuntimeEvent；Runtime UI 的原始事实 |
| `user_*.db` | 用户、市场、成交和每日快照的领域事实 |
| `forum_*.db` | 帖子、反应和引用关系的社交事实 |
| JSON 意图文件 | Agent 当日决策、论坛动作、发帖意图 |
| CSV 结果 | 撮合和市场日级分析产物 |
| `simulation.log` | 诊断日志，不应作为产品状态源 |

不要让前端直接读取这些文件。新视图应先在后端建立受控的只读投影和 DTO。

### 4.4 用户与市场 SQLite

主要表：

| 表 | 作用 |
| --- | --- |
| `Profiles` | 以 `(user_id, created_at)` 保存每日用户快照、现金、持仓、总资产、收益和 persona |
| `Strategy` | 每个用户的策略类型 |
| `StockProfile` | 资产静态资料 |
| `StockData` | 以 `(stock_id, date)` 保存行情、估值、技术指标和资金流 |
| `TradingDetails` | 真实用户的成交腿记录 |

Agent 每个自然日读取前一日 `Profiles`，撮合/结算完成后写入当日新快照。`PersonalizedStockTrader` 本身是当日临时对象，不承载跨日内存状态。

### 4.5 论坛 SQLite

`util/ForumDB.py` 管理：

| 表 | 作用 |
| --- | --- |
| `posts` | 用户、内容、分数、belief、类型、创建时间 |
| `reactions` | 用户对帖子的 like/unlike/repost |
| `post_references` | repost 与原帖之间的引用边 |

belief 的跨日传播依赖帖子：首日从 CSV 获取，后续优先读取最近帖子中的 belief，没有时回退初始 CSV。

## 5. Run 生命周期与控制状态

### 5.1 状态机

生命周期状态定义在 `backend/registry.py`：

```text
draft ──> queued ──> running ──> completed
  │          │          ├──────> failed ──> queued
  │          │          ├──────> stopping ──> cancelled ──> queued
  │          ├──────────> failed
  └──────────> cancelled
```

| 状态 | 含义 | 常见入口 |
| --- | --- | --- |
| `draft` | 已创建目录和清单，尚未启动 | `POST /api/runs` |
| `queued` | 已认领启动，Worker 尚未报告 running | `/start` 或 `/resume` |
| `running` | Worker 正在执行内核 | Worker 启动 |
| `stopping` | 已请求终止进程组 | `/stop` |
| `completed` | 内核成功退出且 Worker 完成收尾 | Worker |
| `failed` | 启动、内核或进程失联失败 | Worker/reconcile |
| `cancelled` | 用户停止或草稿取消 | stop/reconcile |

Health 与 lifecycle 是不同维度：

- lifecycle 回答“运行到哪一步”；
- health 回答“结果/运行是否健康”。

当前定义了 `healthy/degraded/stale/unavailable`，但自动逻辑主要只产生 `healthy/degraded`；也没有真正周期心跳。

### 5.2 创建

`backend/run_service.py`：

1. 合并 `DEFAULTS`；
2. 类型转换并校验用户数、日期、概率和路径；
3. 安全生成 `run_id`；
4. 以私有权限创建独占目录；
5. 写 `manifest.json`、初始 `state.json`；
6. 插入 Registry 的 `draft` 行。

重要细节：`normalize_config()` 只保留 `DEFAULTS` 中声明的字段。新增参数若没有加入默认集合，会被静默丢弃。

### 5.3 启动与 Worker

`ProcessManager.start()`：

1. 校验输入资源和状态；
2. 检查进程内并发配额；
3. 转为 `queued`；
4. 以独立进程组启动 `backend.worker`；
5. 保存 PID。

`backend.worker`：

1. 转为 `running` 并发出 Run 事件；
2. Fresh Run 调准备脚本，复制模板数据库、保留确定性的前 N 个用户并筛选 belief；
3. 拼装 `simulation.py` CLI 参数；
4. 将 stdout/stderr 追加到 `simulation.log`；
5. 根据子进程退出结果更新 Registry 和 RuntimeEvent；
6. 成功时从 `state.json` 读取最终 checkpoint。

### 5.4 停止与失联恢复

- `/stop` 先把状态转为 `stopping`；
- 对整个进程组发送 SIGTERM；
- 10 秒后仍未退出则升级为 SIGKILL，并标记 `cancelled`；
- 查询 Run/Runtime/Event 时会执行 `reconcile()`：
  - `stopping` 且 PID 消失，转 `cancelled`；
  - 其他活动态且 PID 消失，转 `failed`。

### 5.5 Checkpoint 与续跑

内核只在当日所有市场和社交写入成功后调用 `write_checkpoint()`：

```json
{
  "checkpoint": {
    "last_completed_date": "2023-06-15",
    "next_date": "2023-06-16"
  }
}
```

续跑开始时，`init_system()` 和 `clear_date_scoped_artifacts()` 会以 `next_date` 为包含边界，删除该日及之后的数据库行和按日产物，再重新生成。

设计意图是：

```text
已完整提交日期       不动
checkpoint.next_date 重新计算
其后日期             清除后重新计算
```

当前 Backend 的 `/resume` 读取 Registry checkpoint，而 Registry 只在整个 Run 成功后同步 `state.json`。失败或取消后，两个来源可能不一致，见第 14 节。

## 6. 内核自然日数据流

核心入口是 `simulation.py::init_simulation()`。

### 6.1 启动清理与静态加载

进入日期循环前：

1. 建立 `RuntimeObserver` 和 `EventStore`；
2. 删除开始日期及之后的用户/市场/论坛状态；
3. 删除开始日期及之后的按日产物；
4. 读取新闻 pickle、交易日历；
5. 从用户 DB 读取 `Strategy`；
6. 读取初始 belief CSV。

### 6.2 每个自然日的阶段

内核按自然日而非仅交易日推进：

| Day stage | 真实工作 | 主要输入 | 主要输出 |
| --- | --- | --- | --- |
| `prepare` | 判定交易日、加载行情/新闻/用户、belief、构图、选 top users | DB、新闻、日历、belief | DataFrame、图、激活映射 |
| `agents` | 线程池并发执行每个 Agent | 上一日画像、图、新闻、市场 | 三类意图、对话 |
| `market` | 交易日撮合结算；休市日复制快照 | 交易意图、前日状态 | 订单、成交、行情、用户快照 |
| `social` | 提交发帖和互动，更新帖子分数 | 社交意图 | forum DB |
| `commit` | 原子写入 checkpoint | 当日已提交事实 | `state.json` |

更完整的顺序：

```text
日期开始
  → 交易日判断、当日新闻
  → 加载用户列表
  → 随机分配模型配置与激活状态
  → 读取/回退 belief
  → 基于历史交易重建用户关系图
  → 线程池执行 Agent
  → 写决策/反应/发帖意图 JSON
  → 提交有效新帖
  → 交易日撮合结算，或休市日复制 Profiles
  → 提交论坛动作并重算分数
  → 写 checkpoint
  → 下一自然日
```

这是一种“并发生成意图、串行提交事实”的两阶段模型。Agent 阶段原则上不直接改写用户市场数据库；集中提交降低了线程同时写 SQLite 的冲突。

### 6.3 Belief 与社交反馈环

```text
初始 belief.csv
    ↓ 首日
Agent 决策与发帖
    ↓ post.belief
forum DB
    ↓ 次日读取最近 belief
Agent 新决策与新发帖
```

后续日期若用户没有帖子或帖子缺 belief，会回退 CSV。当天 Agent 的互动意图基于提交新帖之前的论坛快照，因此不会在同一天重新响应刚发布的帖子。

### 6.4 用户关系图

`util/UserDB.py::build_graph_new()` 每日：

1. 查询日期范围内每个用户的交易；
2. 按行业累计带时间衰减的权重；
3. 两两计算加权 Jaccard；
4. 超过阈值则连边；
5. 把孤立节点连接成链；
6. 保存 NetworkX pickle；
7. 按度数选择 top users。

图影响：

- 谁会读全体广播新闻；
- 论坛推荐从哪些邻居取帖；
- 可作为研究产物下载。

## 7. 单 Agent 决策流

入口链路：

```text
simulation.process_user_input()
  → PersonalizedStockTrader(...)
  → PersonalizedStockTrader.input_info()
  → BaseAgent / InformationDB / UserDB / ForumDB
  → DecisionIntent + SocialIntent + PostIntent + Conversation
```

### 7.1 Agent 输入快照

每个用户、每天创建新的 `PersonalizedStockTrader`，主要输入包括：

- 前一自然日 `Profiles`；
- 当前持仓和现金；
- 用户 `Strategy`；
- 当日共享关系图；
- 当日新闻和历史 `StockData`；
- 当前 belief；
- top user、随机技术面交易者、激活状态；
- 语言模型配置。

跨日状态由 DB/文件承载，而不是复用 Python 对象。

### 7.2 决策顺序

`input_info()` 的主要步骤：

1. 用画像、策略、持仓和 belief 建立对话上下文；
2. 非首日从图邻居帖子生成 like/unlike/repost 意图；
3. 未激活用户在此处短路主要交易流程；
4. top user 读取广播新闻；
5. 交易日随机推荐候选资产；
6. 非随机交易者生成查询词并调用 FAISS 搜索近 7 日新闻；
7. 模型形成环境判断并更新 belief；
8. 模型从持仓与候选中选择待交易资产；
9. 随机选择符合策略的技术指标和窗口；
10. 模型生成 YAML 决策；
11. 解析、修复并标准化动作、目标仓位和价格；
12. 将仓位变化转换为 100 股整数倍的 `sub_orders`；
13. 模型生成帖子和可供次日使用的新 belief；
14. 返回决策、论坛动作、发帖和对话。

随机技术面交易者跳过检索、belief 更新、选股和时序分析，直接按行情生成决策，但仍可能执行社交/发帖模型调用。

### 7.3 模型层

`Agent.py::BaseAgent`：

- 支持 OpenAI/OpenRouter/vLLM 兼容接口和 local/Ollama；
- 从 YAML 读取模型名、地址、密钥、超时和能力覆盖；
- 估算输入 token 并限制输出；
- 根据 Provider/模型能力过滤不支持的参数；
- 只对连接、超时、限流和服务端错误重试；
- 记录 request id、延迟和 token 等运维信息，不记录密钥。

`trader/prompts.py` 是 Prompt 契约中心。改动模型输出格式时，不能只改 Prompt，还必须同步解析、标准化、订单生成和测试。

### 7.4 新闻检索

`util/InformationDB.py`：

- `EmbeddingWorker` 调嵌入模型；
- `InformationDB` 加载 FAISS 索引和元数据；
- Agent 先生成查询，再做公告/新闻语义检索。

`trader/trading_agent.py` 在模块导入时创建并加载全局 `INFORMATION_DB`。这意味着 import 本身有配置、文件和内存副作用，Worker 启动前必须确保嵌入配置与索引可用。

### 7.5 Runtime Agent 阶段

UI 使用六个逻辑槽位：

```text
state → perception → interpretation → decision → action → commit
```

它们目前不是精确性能 span。主要 LLM 工作整体发生在 `input_info()` 中，并被大部分记入 `interpretation`；`decision` 与 `action` 事件是在返回后根据结果快速补写的摘要；异常统一记到 `commit`。若需要真实逐步骤耗时，应把 Observer hook 下沉到 `PersonalizedStockTrader` 的实际方法内部。

## 8. 订单、撮合与结算

### 8.1 决策到订单

链路：

```text
Prompt/YAML decision
  → _polish_decision()
  → _process_decision_result()
  → trading_records/<date>.json
  → read_json()
  → create_orders_from_decisions()
  → Order
```

决策中每个资产包含 action、当前/目标仓位、目标价格和 `sub_orders`。当前下单量按资产价值换算并取 100 股整数倍。

### 8.2 撮合

`trader/matching_engine.py`：

1. 给订单生成交易时段内的随机唯一时间；
2. 按资产分组；
3. 买单价格降序、时间升序；
4. 卖单价格升序、时间升序；
5. 遍历报价，选择可成交量最大的首个价格；
6. 分配买卖两侧成交量；
7. 输出订单、日汇总、成交腿和大单流。

当买卖量相差至少 2.5 倍且两侧都有订单时，系统会最多复制少数侧 3 份，以 `ZYF` 作为人工流动性订单。它会影响价格和成交，但不作为普通用户写入 `TradingDetails`。

### 8.3 结算顺序

`process_trading_day()` 当前按以下顺序持久化：

```text
生成订单
  → 撮合
  → 写 CSV/订单簿产物
  → 更新 StockData
  → 更新 TradingDetails
  → 写当日 Profiles 快照
```

休市日不撮合，只调用 `update_profiles_table_holiday()` 延续用户快照。

### 8.4 结果口径

维护统计功能时要注意：

- `results/trades` 当前读取 `trading_records/<date>.json`，它是 **Agent 交易决策**，不是撮合成交；
- `trading_records/<date>_orders.json` 是订单；
- 真正成交在 `simulation_results/<date>/transactions_<date>.csv`；
- transactions 当前是买方腿/卖方腿记录，不是一个同时包含买卖双方的配对 Trade；
- `volume` 常表示单边股数；
- `transaction_count` 是成交腿数，不等同于经济意义的成交笔数；
- 某些汇总遍历双边腿，会把经济成交量或成交额计算为两倍。

新增分析功能前必须先选定并写清使用的是 decision、order、matched leg 还是 paired trade。

## 9. Runtime 事件与状态归约

### 9.1 事件契约

`runtime/event.py::RuntimeEvent` 是不可变事件，主要字段：

```text
event_id, run_id, event, scope, stage
simulation_date, substage
agent_id, worker_id
started_at, ended_at, duration_ms, attempt
input_summary, output_summary, message
error_code, error_summary, correlation_id
```

事件类型：

```text
stage_started
stage_completed
stage_skipped
stage_failed
stage_retrying
```

scope 包括 run、day、agent、market、social、artifact、system。

### 9.2 写入

`RuntimeObserver` 是 best-effort 观测层：

- 算法先做真实工作，再用 Observer 描述状态；
- 观测失败不应中断市场算法；
- `EventStore.append()` 在同一进程内用锁保证顺序；
- 事件追加到 `events.jsonl`，并在内存保留热尾部；
- crash 留下的半行 JSON 会被读取逻辑跳过。

### 9.3 快照

后端 `runtime_snapshot()`：

1. 打开该 Run 的 `EventStore`；
2. 从 event 0 读取全部事件；
3. 用 `RuntimeSnapshotReducer` 派生 Run、Day、Agent、Worker、当日摘要和诊断；
4. 叠加 Registry lifecycle/health。

Reducer 是投影，不是新事实来源。若 UI 显示错误，应先看原始事件，再看归约规则。

### 9.4 前端实时组合

Runtime 页面同时消费：

```text
Run Registry 状态      每 3 秒 GET run
Runtime 权威快照       每 2 秒 GET runtime
原始增量事件           EventSource SSE
```

SSE 事件用于最近事件和触发快照 reload；前端不自行完整归约事件。这个选择让刷新和断线恢复更简单，但会放大全量快照读取成本。

## 10. 后端架构

### 10.1 应用装配

`backend/app/main.py::create_app()` 是应用工厂，负责：

- 读取 `Settings`；
- 创建/注入 Registry 与 ProcessManager；
- 配置 CORS；
- 把 service 异常映射为 HTTP；
- 声明 `/health` 与 `/api` 路由。

模块级 `app` 供 Uvicorn 使用：

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766
```

主要环境变量：

| 变量 | 作用 |
| --- | --- |
| `TWINMARKET_PROJECT_ROOT` | 项目根 |
| `TWINMARKET_DATA_DIR` | 数据根 |
| `TWINMARKET_RUNS_DIR` | Run 目录根 |
| `TWINMARKET_REGISTRY_PATH` | Registry SQLite |
| `TWINMARKET_ALLOWED_ORIGINS` | CORS origin allowlist |

同一组路径设置通过环境传给 detached Worker。

### 10.2 服务边界

| 模块 | 作用 |
| --- | --- |
| `registry.py` | 生命周期和控制面元数据 |
| `run_service.py` | 参数归一化、Run 创建和启动前校验 |
| `process_manager.py` | start/stop/reconcile 与并发配额 |
| `worker.py` | 准备输入、启动内核、收尾 |
| `runtime_service.py` | 事件到快照 |
| `results.py` | 结果、导出和 artifact |
| `services/read_only.py` | 路径限制、只读 SQLite、Run 目录解析 |
| `services/agents.py` | Profiles 的 Agent 读模型 |
| `services/market.py` | StockProfile/StockData 读模型 |
| `services/catalog.py` | 模板、市场范围、连接状态 |
| `services/logs.py` | 日志 allowlist 与脱敏 |
| `services/model_settings.py` | 模型配置读取、验证、原子写入 |
| `services/documentation.py` | 发布文档白名单 |

推荐继续保持：FastAPI route 只做 HTTP 参数、DTO 和状态码；可测试的领域读取逻辑放 service。

### 10.3 API 地图

| 资源 | 接口 | 当前前端 |
| --- | --- | --- |
| 健康 | `GET /health/live`, `/health/ready` | 未使用 |
| Catalog | `GET /api/catalog` | 未使用 |
| 设置 | `GET /api/settings/models`, 两个 `PUT` | 已使用 |
| 文档 | `GET /api/documentation[?path=]` | 已使用 |
| Agent | `GET /api/agents`, `/api/agents/{id}` | 已使用 |
| 市场 | `GET /api/market` | 已使用 |
| Run | create/list/get/patch/copy/start/stop/resume/archive/delete | 使用主要动作；patch/delete/归档 UI 不完整 |
| Runtime | snapshot、agent runtime、diagnostics、events | 页面使用 snapshot + events |
| Results | summary/trades/orders/agents/social/export | 页面只用 summary/trades/agents |
| Artifacts | list/download | 未使用 |
| Logs | `GET .../logs` | 未使用 |

### 10.4 只读与安全边界

后端已有以下保护：

- 项目、data、runs 路径越界校验；
- Registry 的 output 必须是 runs 根的直接子目录；
- artifact 读取 resolve 后阻止 symlink 逃逸；
- SQLite 使用 `mode=ro` 与 `PRAGMA query_only=ON`；
- 文档只发布 `docs/` 下小于 1 MiB、非 symlink、frontmatter 为 `published: true` 的 Markdown；
- 模型配置用临时文件 + `os.replace`，权限为 `0600`；
- API 不回传 API key，只回传 `api_key_configured`；
- Runtime 摘要会脱敏 key/token/endpoint/prompt/reasoning；
- 日志 API 只保留 allowlist 的运维行。

但是整个控制面没有认证。它当前应被视为本机可信控制面；CORS 不是服务端鉴权。若监听非本机地址，应先增加认证、授权、TLS 和更严格的 artifact allowlist。

## 11. 前端架构

### 11.1 技术与入口

- React 19、TypeScript、Vite；
- React Router；
- Tailwind CSS + CSS variables；
- Radix 与本地 UI primitives；
- `react-markdown` + GFM；
- Vitest + Testing Library。

启动：

```text
index.html
  → src/main.tsx
  → StrictMode
  → BrowserRouter
  → ToastProvider
  → App
  → AppShell + lazy route
```

`VITE_PUBLIC_BASE` 控制前端资源和 Router basename。开发时 Vite 将 `/api` 代理到 `127.0.0.1:8766`。生产 API 根优先取：

1. `window.__TWINMARKET_CONFIG__.apiBaseUrl`；
2. `VITE_API_BASE_URL`；
3. 同源 `/api`。

### 11.2 目录职责

| 路径 | 作用 |
| --- | --- |
| `src/App.tsx` | lazy 页面和路由声明 |
| `src/routes/` | 页面级容器 |
| `src/components/app-shell.tsx` | 导航、主题、侧栏和 Outlet |
| `src/components/ui/` | 通用视觉组件 |
| `src/hooks/use-resource.ts` | HTTP 请求、取消、轮询、错误和保留旧数据 |
| `src/hooks/use-run-events.ts` | SSE、游标、去重、重连 |
| `src/lib/api.ts` | API 根、请求、错误和 endpoint wrapper |
| `src/lib/api-types.ts` | 业务当前实际使用的手写 DTO |
| `src/lib/openapi.generated.ts` | OpenAPI 生成物；当前未被业务使用且已滞后 |
| `src/lib/runtime-config.ts` | Web/Electron API 地址 |

### 11.3 页面与路由

| 路由 | 页面 | 主要数据 |
| --- | --- | --- |
| `/runs` | Run 列表 | `GET /runs`，5 秒轮询 |
| `/runs/new` | 新建 Run | `POST /runs` |
| `/runs/:runId` | Run 详情 | Run，4 秒轮询；start/stop/resume/copy |
| `/runs/:runId/live` | Runtime | Run + snapshot + SSE |
| `/runs/:runId/results` | 结果 | summary/trades/agents |
| `/agents` | Agent 浏览 | 模板或指定 Run 的 Profiles |
| `/market` | 市场浏览 | 模板或指定 Run 的 StockData |
| `/settings` | 模型设置 | 语言/嵌入 YAML 的脱敏读写 |
| `/doc` | 文档 | 已发布 Markdown |

### 11.4 前端状态分层

当前没有 Redux、Zustand 或 React Query：

| 状态类型 | 保存位置 | 示例 |
| --- | --- | --- |
| 可分享查询状态 | URL | Run 筛选、Agent 搜索、Market asset、结果 tab、doc |
| 服务端查询状态 | `useResource` | loading/data/error/refreshing |
| 页面瞬时状态 | 组件 state | 表单、Dialog、focus agent、drawer |
| 跨会话 UI 偏好 | `localStorage` | theme、sidebar |
| 当前标签页连接状态 | `sessionStorage` | 每个 Run 的 SSE cursor |
| 业务权威状态 | 后端 | Registry、运行目录和配置 |

`useResource` 会取消旧请求；刷新时保留旧数据；刷新失败不清空最后成功结果。mutation 成功后，页面通常 reload、导航或用响应更新局部状态。

### 11.5 API 类型

实际代码使用 `api-types.ts` 的手写 DTO。以下契约需要跨层同步：

| 契约 | 后端/内核 | 前端 |
| --- | --- | --- |
| Run status | `backend/registry.py` | `RunStatus`、badge、按钮条件 |
| Health/Stage | runtime/registry | 类型与 badge |
| Run config | `run_service.DEFAULTS` | `RunConfig`、创建表单 |
| RuntimeEvent | `runtime/event.py` | `RuntimeEvent` |
| RuntimeSnapshot | `runtime/snapshot.py` | `RuntimeSnapshot` |
| 固定阶段 | `runtime/schemas.py` | `runtime-page.tsx` 数组 |
| Result DTO | `backend/results.py` | `api.ts` 与结果页 |

当前 OpenAPI 响应多数没有 `response_model`，生成类型经常是 `unknown`，业务也没有引用生成文件。这是契约漂移的主要来源。

## 12. 三条端到端数据流

### 12.1 创建并启动

```text
NewRunPage form
  → api.runs.create()
  → POST /api/runs
  → normalize_config
  → manifest/state/Registry draft
  → RunDetailPage
  → POST /start
  → ProcessManager
  → worker
  → prepare input DB/belief
  → simulation.py
```

### 12.2 单日反馈闭环

```text
前一日 Profiles + StockData + forum belief
  → 关系图/新闻/Prompt
  → Agent DecisionIntent + SocialIntent
  → Market matching + settlement
  → 新 Profiles + StockData + TradingDetails
  → 发帖/互动 + 新 belief
  → 次日重新读取
```

### 12.3 观察与结果

```text
内核 RuntimeObserver
  → events.jsonl
  → Backend Reducer
  → /runtime
  → RuntimePage

内核 DB/JSON/CSV
  → Backend read model / results service
  → REST DTO
  → Agents/Market/Results 页面
```

## 13. 新增或调整功能的改动地图

### 13.1 新增 Run 参数

按顺序检查：

1. `backend/run_service.py`
   - `DEFAULTS`；
   - `normalize_config()` 的类型、范围、路径和互斥校验；
   - 若是输入文件，加入 fingerprint。
2. `backend/app/main.py`
   - 请求模型和 API 文档。
3. `backend/worker.py`
   - 转换为明确的 `simulation.py` CLI 参数。
4. `simulation.py`
   - `parse_args()`；
   - `init_simulation()` 参数；
   - 实际算法。
5. `script/run.sh`
   - 若 CLI 也要支持，加入环境变量/参数和清单。
6. `frontend/src/lib/api-types.ts`
   - `RunConfig`。
7. `frontend/src/routes/new-run-page.tsx`
   - 默认值、输入、说明、校验和提交。
8. 后端 API 测试、内核单测、前端测试。

若参数是 secret，不应进入 Run config、事件或 manifest；应由安全配置或 secret provider 注入。

### 13.2 修改 Agent 行为或 Prompt

典型链路：

```text
TradingPrompt
  → BaseAgent response
  → parse_response_yaml/json
  → _polish_decision
  → _process_decision_result
  → decision JSON
  → matcher
  → backend result
  → frontend
```

操作建议：

1. 先定义输入/输出 schema 和失败语义；
2. 修改 `trader/prompts.py`；
3. 修改 `trader/trading_agent.py`；
4. 修改 `trader/utility.py` 的解析/修复；
5. 若输出字段变化，同步撮合读取；
6. 在 RuntimeEvent 只放脱敏摘要；
7. 用固定模型响应 fixture 测试解析，不让核心测试依赖真实 API。

### 13.3 新增交易动作或订单字段

必须贯穿：

```text
Prompt 输出契约
→ parser
→ decision normalization
→ sub_orders
→ trading_records JSON
→ read_json
→ Order
→ matcher
→ transactions
→ TradingDetails / Profiles
→ results API
→ frontend DTO/UI
```

不要在中间继续添加无版本的任意字典字段。优先定义 `DecisionIntent`、`OrderIntent`、`MatchedTrade` 等明确 DTO。

### 13.4 修改撮合算法

至少验证：

- 价格优先与时间优先；
- 涨跌停；
- 部分成交和剩余量；
- 人工流动性是否参与资产守恒；
- 买卖双方现金/持仓守恒；
- 一笔 Trade 与两条账本腿的口径；
- StockData、TradingDetails、Profiles 的原子提交；
- 旧 CSV/API 是否需要版本兼容。

推荐先把纯撮合与持久化拆开：

```text
OrderIntent[]
  → pure matcher
  → MatchedTrade[]
  → settlement
  → persistence adapters
```

### 13.5 新增行情或技术指标

检查：

1. 模板 DB 的 `StockData` schema；
2. 正常交易日更新；
3. 无订单/休市日更新；
4. `trader/utility.py` 指标白名单和名称映射；
5. Agent 技术数据读取和 Prompt 格式；
6. Backend Market/Result DTO；
7. 前端图表或表格；
8. 旧 Run 缺字段时的兼容默认值。

### 13.6 新增社交动作

同步修改：

- `reactions.type` 数据库约束；
- `ForumDB` 写入与读取；
- `_forum_action` Prompt 和归一化；
- `execute_forum_actions`；
- 分数、推荐和 repost 传播；
- JSON 产物；
- 后端 DTO 和前端展示；
- schema migration 与旧数据兼容。

### 13.7 新增 Runtime 阶段或事件字段

同步修改：

1. `runtime/schemas.py` 的枚举/阶段；
2. `runtime/event.py`；
3. 内核真实工作点的 Observer hook；
4. `runtime/snapshot.py` 的归约规则；
5. 后端 response model；
6. `frontend/src/lib/api-types.ts`；
7. `runtime-page.tsx` 阶段顺序、统计和提示；
8. `status-badge.tsx`；
9. 事件重放、幂等、断线恢复和旧事件兼容测试。

新增一个未知 stage 字符串通常比改变既有 event/scope 语义更容易兼容。

### 13.8 新增生命周期状态或控制动作

需要修改：

- Registry `STATUSES` 与 `TRANSITIONS`；
- 原子状态认领/CAS；
- ProcessManager/Worker/reconcile；
- FastAPI route 和错误状态码；
- 前端 action wrapper；
- `RunStatus`、badge、筛选和按钮条件；
- 幂等、重复请求、崩溃恢复和并发测试。

状态不是纯 UI 文案；它是后端并发和恢复协议。

### 13.9 新增结果页签

推荐步骤：

1. 明确来源和数据口径；
2. 在 `backend/results.py` 建立安全只读 adapter；
3. 定义 Pydantic response model；
4. 在 `backend/app/main.py` 增加 route；
5. 在 `frontend/src/lib/api.ts` 增加 typed wrapper；
6. 在 `api-types.ts` 加 DTO；
7. 在 Results 页面增加 tab、筛选、分页、空/错状态；
8. 测试损坏文件、路径逃逸、分页、导出和隐私。

如果目标是实际成交，应新增 `transactions` 资源，不要继续复用命名含混的 `trades`。

### 13.10 修改数据库 schema

用户/市场 DB 变化需要检查：

- `data/sys_1000.db` 模板；
- `prepare_simulation_run.py` 的裁剪 SQL；
- `util/UserDB.py`；
- `trader/` 的读取和写入；
- Agents/Market/Results 查询；
- 前端 DTO；
- 测试 fixture；
- 旧 Run 的兼容或 migration。

论坛 DB 同理还需同步建表 CHECK 约束和社交算法。SQLite 变更必须提供迁移或清晰的版本拒绝，不能只改新建表语句。

### 13.11 新增普通前端页面

1. 新建 `src/routes/*-page.tsx`；
2. `App.tsx` 加 lazy import 和 route；
3. `app-shell.tsx` 加导航；
4. `api.ts` 增加领域 API；
5. `api-types.ts` 加 DTO；
6. 复用 Skeleton、Error、Empty、Toast 语义；
7. 用 URL 保存需要分享/刷新恢复的状态；
8. 加路由、请求失败和可访问性测试。

### 13.12 新增模型设置

1. FastAPI Pydantic update model；
2. `ModelSettingsService` allowlist、验证、脱敏读取；
3. 原子写入和权限；
4. 前端 settings 类型与表单；
5. secret 的“保留/替换/清除”三态；
6. CORS method；
7. 确定设置影响“所有未启动 Run”还是只影响“新建 Run”。

## 14. 当前实现的关键限制

本节是修改前必读。条目按正确性和扩展风险排序，并给出推荐方向。

### P0/P1：优先修复

#### 14.1 Fresh/Resume 用魔法日期推断

`simulation.py` 以 `start_date == "2023-06-15"` 判断是否 fresh，并只在这个日期初始化论坛。Backend/前端却允许任意开始日期。

影响：

- 新 Run 从其他日期开始会被当成 resume；
- forum DB 可能未初始化；
- 前一日画像/新闻可能不存在。

推荐：增加显式 `--mode fresh|resume` 或 `--resume`，由 Worker 和 CLI 传入；启动前验证模板是否覆盖起始日前一日。

#### 14.2 Checkpoint 有两个权威来源

`state.json` 每日提交，Registry checkpoint 只在整体成功后同步。失败/取消后 `/resume` 可能从旧日期开始。

推荐：以 `state.json` 为事实源，Registry 只做缓存；在 resume、reconcile 和 Worker 收尾时读取、校验并同步。给 state 增加版本和 run instance id。

#### 14.3 SSE 不会持续 tail 外部进程写入

事件 endpoint 在连接时创建一次 `EventStore`；它的 tail 只在构造时加载，`after()` 不会重新读取 simulation 子进程后来追加的内容。连接可能只收到 backlog 和 keepalive。

推荐：实现带 inode/offset 的文件 tail、跨进程 broker，或改为带 cursor 的增量轮询。修复前 Runtime 的“实时”主要依赖 2 秒快照轮询。

#### 14.4 Agent 超时实际上无效

代码先通过 `as_completed()` 等 Future 完成，再调用 `future.result(timeout=...)`；这时 timeout 不再限制执行。永久挂起的 Agent 会卡住日期循环和线程池退出。

推荐：建立 `future -> user_id` 映射，使用真正的 deadline/`wait()`，并把超时落实到模型 HTTP 调用；定义超时后线程/结果是否可继续提交。

#### 14.5 撮合异常可能被吞掉

`test_matching_system()` 捕获广泛异常后只打印，外层仍可能发出 market completed 并写当日 checkpoint。

推荐：记录诊断后重新抛出；只有市场和结算完整提交后才能完成 Day market/commit。

#### 14.6 市场结算不是原子事务

StockData、TradingDetails、Profiles 分阶段、多次 commit。中途失败可能留下半个交易日。

推荐：同一 SQLite 连接中用事务提交领域表；文件先写临时文件再 rename；checkpoint 必须晚于两者成功。

#### 14.7 跨进程状态认领和事件 ID 非原子

Registry 的 Python 锁只保护单进程；状态 transition 是先读后写；配额检查和 queued 转换不是一个事务。API 和 simulation 也可能并发追加事件。

推荐：SQLite `BEGIN IMMEDIATE` + compare-and-swap（`UPDATE ... WHERE status=?`）；把配额认领纳入同一事务；EventStore 使用文件锁、单写者或集中 broker。

#### 14.8 Worker 启动失败可能遗留 queued

状态先转 queued，`Popen` 失败没有完整补偿；queued 且 PID 为空的 reconcile 也不充分。

推荐：启动异常立即 CAS 到 failed；reconcile 扫描无 PID/无心跳的活动记录。

### P1/P2：设计与性能

#### 14.9 Runtime 快照是 O(N) 全量重放

每次 `/runtime` 从 event 0 读取并归约最多一百万条；前端每 2 秒轮询，并可能每条 SSE 再 reload。

推荐：维护增量 reducer/物化 snapshot，使用 last event id；前端对 SSE 触发节流，并在终态停止轮询。

#### 14.10 Runtime 阶段是 UI 逻辑槽位

Agent 的真实 LLM 工作集中在 `interpretation`，后续 decision/action 只是结果摘要。

推荐：若用于性能诊断，把埋点放进检索、belief、选股、技术分析、决策和发帖实际方法；保留高层阶段作为聚合。

#### 14.11 输入被指纹记录，但没有冻结

创建 draft 时 manifest 记录配置/输入指纹；Worker 启动时仍读取全局路径。创建后修改 YAML 或输入文件会改变旧 draft 的实际行为。

推荐：创建或启动时复制不可变输入到 Run 目录，或在启动前强校验指纹并要求显式重新基线。

#### 14.12 可复现性只是部分保证

只设置 Python 全局 `random.seed`；线程调度会改变随机调用顺序，NumPy、集合顺序、外部 LLM/embedding 也可能非确定；用户图衰减还使用机器当前时间。

推荐：每个 Run/Day/Agent 使用派生 RNG；所有时间使用 simulation clock；记录模型版本和采样参数；需要严格重放时缓存外部响应。

#### 14.13 用户图接近 O(U²)

每天逐用户查询 DB 并两两比较，1000 用户多日运行成本很高。

推荐：一次查询聚合特征、向量化/稀疏矩阵计算，或仅增量更新变化用户；缓存按日特征。

#### 14.14 数据根没有完整贯穿

新闻、日历和索引大多遵循 `TWINMARKET_DATA_DIR`，但 matching engine 的真实行情默认仍使用 `data/stock_data.csv`。

推荐：把 data root/real market path 作为显式内核参数一路传入，禁止深层函数自行解析工作目录相对路径。

#### 14.15 人工流动性与守恒口径不清

`ZYF` 订单能与真实用户成交，却没有明确做市账户资产负债。

推荐：定义外部流动性提供者账户、库存和现金；或明确其是非守恒外生市场，并在结果中分离。

#### 14.16 成交对象和统计口径混杂

成交以双边 legs 表示，部分指标用单边量，部分遍历双边导致翻倍。

推荐：引入稳定 `trade_id`，一个 `MatchedTrade` 包含 buyer/seller/price/quantity，再由 settlement 派生两条账本腿。

#### 14.17 涨跌停计算未完整进入撮合约束

撮合函数计算限价边界，但当前没有一致地用于过滤/裁剪全部订单。

推荐：在订单验证层明确拒绝、裁剪或标记超限订单，并加边界测试。

#### 14.18 激活语义不一致

非首日论坛推荐和互动决策发生在未激活短路之前；提交论坛动作时也未再次按激活状态过滤。

推荐：产品层先定义“未激活”是否仍可浏览/互动，再把这一语义应用到 Agent、提交和 Runtime 摘要。

#### 14.19 模型错误可能延迟显现

`BaseAgent.get_response()` 把异常转换成 `{"error": ...}`；部分调用者仍继续解析 `None`/错误结构，真正原因被后续解析错误覆盖。

推荐：使用明确 Result 类型或抛出 typed exception；每个模型调用点立即验证 `response`。

#### 14.20 导入 `trading_agent` 有重副作用

模块导入时立即读取 embedding 配置并加载 FAISS。

推荐：把 InformationDB 注入 `PersonalizedStockTrader` 或 Worker context，按需初始化一次，并让纯单元测试可以使用 fake。

### 前后端契约与产品边界

#### 14.21 CORS 未允许 PUT

后端 CORS methods 没有 PUT，跨 origin 的 Settings 保存会被预检拒绝；Vite 同源代理会掩盖问题。Electron 的 `file://`/`null` origin 也需要单独设计。

#### 14.22 手写 DTO 与 OpenAPI 已漂移

前端 `RuntimeEvent` 缺少部分后端字段，生成 OpenAPI 文件缺少新设置路由且响应多为 `unknown`。

推荐：给后端全部响应和统一错误声明 Pydantic model；让生成类型成为业务类型来源；CI 校验生成文件无 drift。

#### 14.23 `.gitignore` 会忽略 `frontend/src/lib/`

根 `.gitignore` 的 `lib/` 规则会匹配前端核心 API/type 目录。

推荐：改为根锚定 `/lib/`，或显式取消忽略 `frontend/src/lib/`，并用 `git check-ignore` 加检查。

#### 14.24 首次 SSE 可能从 0 重放

hook 建连只依赖 `runId`；初次 snapshot 尚未返回时 cursor 常为 0，后续 snapshot cursor 增长不会重建连接。

推荐：等初始 snapshot 后再建连，或响应 snapshot cursor 变化；Run instance id 变化时清理 session cursor。

#### 14.25 前端分页和终态停轮询不完整

多个 API 返回分页结果，但页面只显示第一页；Run 终态后仍可能轮询/SSE。

推荐：提供统一分页组件；查询 hook 接受 enabled/interval 函数，在终态关闭实时刷新。

#### 14.26 Settings 保存后的密钥提示可能陈旧

保存响应没有完整更新 query state，`api_key_configured` 展示可能仍是旧值。

推荐：mutation 成功后 reload，或用返回 DTO 原子替换缓存。

#### 14.27 Artifacts 不是天然安全的公开下载区

下载允许多种 JSON/CSV/TXT，可能包含 conversation、Prompt 或模型原始内容。分页结果会脱敏，不代表导出/原始 artifact 自动脱敏。

推荐：使用显式 artifact 类型 allowlist、敏感级别、权限与审计；公网部署前加入认证。

#### 14.28 两套 Run contract 会漂移

CLI 与 Backend 在 manifest 版本、锁、续跑和状态同步上已有差异。

推荐：抽取唯一 `RunContract` 库，由 CLI 和 Backend 共用创建、锁、checkpoint、输入冻结与清理。

## 15. 测试与验证

### 15.1 当前已有覆盖

- 根 `tests/`
  - BaseAgent 能力和重试；
  - Run contract 的清理边界；
  - 用户子集和 belief 准备。
- `backend/tests/`
  - API 基本兼容；
  - RuntimeEvent、Reducer、Registry 基本迁移；
  - 路径逃逸、只读 SQLite、日志脱敏；
  - 模型设置和文档发布边界。
- `frontend/`
  - 少量工具函数和 SSE 去重测试。

统一检查入口：

```bash
./script/check.sh
```

它执行核心 Python 编译/单测、Shell 语法、后端测试、前端测试和构建。

### 15.2 明显测试缺口

优先补充：

1. Worker → simulation → events/results 的单日端到端测试；
2. 任意合法 fresh 起始日；
3. 失败后从 `state.json` 续跑；
4. 外部进程追加时 SSE 持续读取；
5. 并发 start 的原子认领和配额；
6. Popen 失败、服务器重启、孤儿进程 reconcile；
7. 撮合价格优先、涨跌停、部分成交和资产守恒；
8. 市场事务中途失败的回滚；
9. forum 分数和 belief 的跨日反馈；
10. 前端表单、轮询、分页、错误、路由和 SSE 重连；
11. API response schema 与生成 TypeScript 类型漂移检查。

### 15.3 每类改动的最小验收

| 改动 | 最小验收 |
| --- | --- |
| Run 参数 | API 创建值、manifest、Worker CLI、内核实际值一致 |
| Agent/Prompt | 固定响应可解析；非法响应失败清晰；不泄露 Prompt/密钥 |
| 撮合 | 同一输入确定输出；现金/持仓守恒；事务完整 |
| Runtime | 旧事件可重放；新事件可归约；SSE 断线恢复无重复/漏失 |
| Result API | 路径安全、分页、损坏输入、脱敏、旧 Run 兼容 |
| 前端页面 | loading/empty/error/success；键盘可用；刷新可恢复 |
| DB schema | 新库、旧库迁移、旧 Run 只读兼容 |

## 16. 推荐阅读顺序

第一次阅读不建议从 1900 行撮合文件或大型 Agent 类逐行开始。按以下顺序更容易建立模型：

1. `backend/run_service.py`：Run 参数和目录契约；
2. `backend/process_manager.py`、`backend/worker.py`：谁启动谁；
3. `simulation.py::init_simulation()`：每日骨架；
4. `simulation.py::process_user_input()`：单 Agent 边界；
5. `trader/trading_agent.py::input_info()`：Agent 决策顺序；
6. `trader/matching_engine.py::test_matching_system()` 和 `process_trading_day()`：市场提交；
7. `util/UserDB.py::build_graph_new()`、ForumDB 关键写接口；
8. `runtime/event.py`、`event_store.py`、`snapshot.py`：观察协议；
9. `backend/app/main.py` 与 `services/*`：HTTP 投影；
10. `frontend/src/lib/api.ts`、hooks、各 routes：页面如何消费投影。

调试某个具体 Run 时，推荐按事实倒推：

```text
Registry row
  → manifest/state
  → simulation.log
  → events.jsonl
  → 当日 decision/order/result
  → user/forum DB 当日行
  → Backend DTO
  → Frontend 页面状态
```

## 17. 维护原则与提交前清单

### 17.1 稳定边界

- Run config 是版本化输入协议；
- RuntimeEvent 是版本化观察协议；
- 运行目录布局是内核与后端的数据协议；
- 后端 response model 是前端契约；
- checkpoint 只能代表完整提交的自然日；
- 页面永远消费服务 DTO，不直接解释数据库和文件。

### 17.2 设计新功能时

先回答：

1. 新事实由谁产生？
2. 权威状态保存在哪里？
3. 是否跨 Run、跨日或跨进程？
4. 失败后是否可重试、幂等和续跑？
5. 哪些字段可能含密钥、Prompt、推理或个人内容？
6. 旧 Run、旧事件和旧前端是否还能读取？
7. 数据口径是意图、订单、成交还是账本？
8. 哪些层需要同步改动和测试？

### 17.3 提交前

- [ ] 参数从 UI/API 一直传到算法，没有被默认值覆盖或静默丢弃；
- [ ] 状态转换是合法、幂等且并发安全的；
- [ ] checkpoint 晚于所有领域事实提交；
- [ ] Runtime 事件只包含脱敏、有限长度摘要；
- [ ] Pydantic/TypeScript DTO 同步；
- [ ] 新路径经过可信根 resolve，SQLite 只读查询仍为 query-only；
- [ ] 新结果明确口径和版本；
- [ ] 旧 Run/事件有兼容策略；
- [ ] mutation 后前端状态明确 reload、替换或导航；
- [ ] loading/empty/error/终态行为可见；
- [ ] 单元、集成、构建和 `./script/check.sh` 通过。

## 18. 建议的演进目标

在不一次性重写的前提下，最值得逐步形成以下稳定层次：

```text
Run orchestration
  Worker / lifecycle / lock / checkpoint

Daily input snapshot
  日期、市场、新闻、用户画像、belief、关系图

Agent policy
  Snapshot → DecisionIntent + SocialIntent

Market engine
  OrderIntent → MatchedTrade

Settlement
  MatchedTrade + 前日账本 → 新账本与市场状态

Social engine
  SocialIntent → Forum state

Persistence adapters
  SQLite / JSON / CSV / EventStore

Read models
  Backend response DTO → Frontend
```

推荐实施顺序：

1. 统一 fresh/resume 和 checkpoint；
2. 修复 Worker/Registry 的原子状态与 SSE tail；
3. 让撮合失败传播，并将结算放入事务；
4. 定义 Decision/Order/Trade DTO 和准确口径；
5. 为 Backend 响应建立 Pydantic 模型并生成前端类型；
6. 把外部数据、时钟、随机数和模型客户端显式注入；
7. 用单日端到端测试保护状态转换；
8. 再扩展新的 Agent、市场和可视化能力。

完成这些边界后，新功能会从“同时修改多处隐式字典和文件约定”变为“修改清晰的生产者、协议和消费者”，维护成本会显著下降。
