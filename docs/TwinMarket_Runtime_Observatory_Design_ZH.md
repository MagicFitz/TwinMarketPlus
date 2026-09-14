# TwinMarket Runtime Observatory 运行中界面设计文档

> 文档类型：产品 / 交互 / 运行时数据契约设计  
> 模块名称：TwinMarket Runtime Observatory  
> 建议路由：`/studio/runs/:runId/live`  
> 设计目标：将市场模拟的运行过程本身可视化，使用户能够持续观察交易日循环、Agent 感知—认知—决策—行动过程，以及市场和社交环境如何被更新。

---

## 1. 设计背景

TwinMarket 的运行界面不应只是一个显示“运行进度”的 Dashboard。

用户在创建一次市场模拟并点击运行之后，往往会持续停留在运行页面，希望观察：

- 当前模拟推进到了哪个交易日；
- 系统此刻正在做什么；
- 哪些 Agent 正在运行；
- 某个 Agent 今天读取了什么信息；
- Agent 的 belief 是否发生变化；
- Agent 最终做出了什么交易和社交行为；
- 这些行为如何进入订单池、论坛和市场；
- 一个交易日如何完成并进入下一个交易日；
- 哪些步骤耗时较长、失败或发生重试。

因此，运行页的核心不是“Progress”，而是：

> **让用户看到一个人工金融市场正在运行。**

该页面应被设计为 **Runtime Observatory（运行观测台）**。

---

## 2. 核心设计原则

### 2.1 展示运行机制，而不仅是运行结果

传统运行页面通常只展示：

```text
Running
37%
24 / 126 days
```

TwinMarket 应进一步展示：

```text
2023-07-18
Agent #10039126898

读取论坛
    ↓
读取新闻和公告
    ↓
更新 belief
    ↓
选择关注资产
    ↓
形成交易决策
    ↓
生成可执行订单
    ↓
产生帖子 / 社交行为
    ↓
提交到市场和论坛环境
```

运行过程本身即研究对象。

---

### 2.2 固定流程槽位，动态更新内容

运行信息不应主要依靠不断滚动的日志呈现。

应建立固定的视觉流程：

```text
STATE
  ↓
PERCEPTION
  ↓
INTERPRETATION
  ↓
DECISION
  ↓
ACTION
  ↓
COMMIT
```

每一个阶段在页面中的位置固定，只改变：

- 状态；
- 耗时；
- 输入摘要；
- 输出摘要；
- 当前子阶段；
- 错误或重试信息。

这种设计使用户可以长时间盯着页面，而不需要阅读不断变化的日志。

---

### 2.3 区分三个运行尺度

运行页应同时展示三个尺度：

```text
Run
└── Trading Day
    └── Agent
```

即：

1. 整次实验；
2. 当前交易日；
3. 当前 Agent。

三层信息不能混为一个进度条。

---

## 3. TwinMarket 当前运行模型的抽象

现有模拟可以抽象为两个嵌套循环。

### 3.1 外层：交易日循环

```text
Run
│
├── Day t
│   ├── Prepare Environment
│   ├── Process Agents
│   ├── Collect Actions
│   ├── Update Market
│   ├── Update Social Environment
│   └── Commit Day
│
├── Day t+1
│   └── ...
│
└── Completed
```

一次交易日包含以下主要阶段。

#### Phase A — Prepare Environment

准备当天所有 Agent 共用的环境状态：

- 判断交易日 / 非交易日；
- 加载行情；
- 加载当日新闻；
- 获取当前有效 Agent；
- 加载 Agent belief；
- 构建当日用户关系网络；
- 确定 top users；
- 确定 Agent 激活状态；
- 分配模型/API配置。

#### Phase B — Process Agents

处理当天所有 Agent。

可能采用：

```text
Serial
Agent 1 → Agent 2 → Agent 3 → ...

Parallel
Worker 1 → Agent A
Worker 2 → Agent B
Worker 3 → Agent C
...
```

因此 UI 不能假设 Agent 一定严格串行。

#### Phase C — Collect Actions

汇总 Agent 输出：

- trading decisions；
- post intentions；
- forum reactions；
- conversations；
- belief updates。

#### Phase D — Market Update

将 Agent 决策转换为市场状态：

- 构建订单；
- 执行 matching；
- 更新成交；
- 更新持仓；
- 更新现金和组合价值；
- 更新行情及交易结果。

#### Phase E — Social Update

将 Agent 的社交行为作用到论坛环境：

- 创建帖子；
- 执行点赞 / 互动 / 引用等行为；
- 更新帖子评分；
- 更新关系网络所需状态。

#### Phase F — Day Commit

完成当天数据持久化：

- trading records；
- reaction records；
- post records；
- conversation records；
- 数据库状态；
- graph snapshots；
- 日终产物。

随后进入下一模拟日。

---

## 4. Agent 感知—认知—行动模型

代码中的具体函数会不断变化，因此 UI 不应直接绑定所有函数。

应建立稳定的 Agent Runtime Ontology。

建议统一抽象为：

```text
State
    ↓
Perception
    ↓
Interpretation
    ↓
Decision
    ↓
Action
    ↓
Commit
```

这是运行页的核心视觉模型。

---

## 5. 六阶段 Agent Runtime Pipeline

### 5.1 STATE — 当前 Agent 状态

回答：

> “现在是谁在进行决策？”

输入包括：

- Agent ID；
- Agent 类型；
- strategy；
- 当前 belief；
- 是否 active；
- 是否 top user；
- 当前现金；
- 当前持仓；
- 总资产；
- 当前网络位置；
- 当前模拟日期。

UI 示例：

```text
STATE ✓ 0.03s

Agent      #10039126898
Strategy   Technical
Role       Normal User

Cash       32.4%
Positions  3

Belief
Bearish · 0.61
```

STATE 不表示 LLM 推理，它是当日认知过程的初始条件。

---

### 5.2 PERCEPTION — 感知环境

回答：

> “Agent 今天看到了什么？”

可能包括：

#### Social perception

- 推荐帖子；
- 关注用户帖子；
- 历史互动；
- 网络邻居信息。

#### Public information

- 重要新闻；
- 系统广播；
- 宏观信息。

#### Retrieved information

- 新闻检索；
- 公告检索；
- RAG 检索结果；
- 相关文本数量。

#### Market perception

- 已有持仓；
- 前日行情；
- 技术指标；
- 推荐资产；
- 候选资产。

UI 示例：

```text
PERCEPTION ✓ 4.21s

Forum
5 posts retrieved

News
3 public news

Search
8 documents → 2 selected

Market
2 candidate indices
```

内部子阶段可以显示：

```text
✓ Forum
✓ Public News
● Announcement Retrieval
○ Market Data
```

---

### 5.3 INTERPRETATION — 信息解释与 belief 更新

回答：

> “Agent 如何理解刚刚获取的信息？”

该阶段可以包含：

- 信息初步判断；
- 新闻/论坛观点整合；
- belief 更新；
- sentiment / stance 更新；
- 信息重要性判断；
- uncertainty 更新。

UI 不应强制展示完整 Chain-of-Thought。

适合展示：

- old belief；
- new belief；
- belief delta；
- 关键输入信息；
- 模型输出摘要；
- 调用耗时；
- token 数；
- 模型名。

示例：

```text
INTERPRETATION ✓ 7.21s

Belief
0.61 → 0.73 Bearish

Signals
- PMI deterioration
- CNY depreciation
- Consumer weakness

LLM
Model      xxx
Latency    7.21s
Tokens     2,381
```

---

### 5.4 DECISION — 形成行为意图

回答：

> “Agent 想做什么？”

该阶段展示 Agent 的策略结果。

金融行为：

- Buy；
- Sell；
- Hold；
- target position；
- target price；
- reason。

示例：

```text
DECISION ✓ 4.82s

Energy Index
BUY

Current position     10%
Target position      18%
Target price       102.40

Consumer Index
SELL
20% → 12%

Technology
HOLD
15% → 15%
```

该阶段表示 Agent 的**认知决策**，还不是最终进入环境的真实行为。

---

### 5.5 ACTION — 转换为环境可以执行的行为

回答：

> “Agent 的意图最终转化成了什么动作？”

例如：

```text
Agent intention
      ↓
Executable action
```

金融行为包括：

- order side；
- quantity；
- price；
- sub-orders；
- 无效订单原因。

社交行为包括：

- post；
- post type；
- like；
- repost；
- reference；
- interaction intention。

示例：

```text
ACTION ✓ 0.12s

BUY Energy
800 shares @ 102.40

SELL Consumer
400 shares @ 94.20

Forum Post
Generated
```

---

### 5.6 COMMIT — 写入模拟世界

回答：

> “哪些行为已经成为 TwinMarket 世界中的事实？”

包括：

- decision persisted；
- conversation persisted；
- post persisted；
- order submitted；
- forum action submitted；
- artifact generated。

示例：

```text
COMMIT ✓

conversation.json      saved
trading decision       saved
post intent            saved
order                   submitted
```

COMMIT 是 Agent 世界与 Environment 世界之间的重要边界。

---

# 6. LiveSimulationView 总体布局

建议将原先的：

```text
LiveRunOverview
AgentExecutionView
```

整合为：

```text
LiveSimulationView
```

核心页面结构：

```text
┌────────────────────────────────────────────────────────────────────┐
│ RUN HEADER                                                         │
├────────────────────────────────────────────────────────────────────┤
│ DAY CYCLE                                                          │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│                     FOCUS AGENT PIPELINE                           │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│ WORKER LANES / AGENT QUEUE                                         │
├─────────────────────────────────────┬──────────────────────────────┤
│ TODAY SUMMARY                       │ RECENT EVENTS                │
└─────────────────────────────────────┴──────────────────────────────┘
```

---

## 7. Layer 1 — Run Header

顶部状态栏展示整次 Run。

建议字段：

```text
TwinMarket · Running

2023-07-18
Trading Day 24 / 126

Agents      37 / 100
LLM Calls   182
Elapsed     18m 32s
Health      Healthy
```

操作：

```text
Stop
Open Diagnostics
Run Settings
```

注意：

- Run Progress；
- Day Progress；
- Agent Progress；

必须分开。

---

# 8. Layer 2 — Day Cycle

Day Cycle 是当天宏观流程。

推荐固定显示：

```text
PREPARE
    ↓
AGENTS
    ↓
MARKET
    ↓
SOCIAL
    ↓
COMMIT
```

或横向：

```text
Environment → Agent Processing → Market Clearing → Social Update → Day Commit
```

状态：

```text
✓ completed
● running
○ pending
! warning
× failed
```

示例：

```text
2023-07-18

Environment       ✓
Agents            ● 37 / 100
Market Clearing   ○
Social Update     ○
Day Commit        ○
```

---

# 9. Layer 3 — Focus Agent Pipeline

这是整个页面最重要的视觉区域。

布局建议：

```text
                    CURRENT AGENT · #10039126898
                   Technical Trader · Worker 01

┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ STATE        │ → │ PERCEPTION   │ → │ INTERPRET    │
│ ✓            │   │ ✓            │   │ ●            │
└──────────────┘   └──────────────┘   └──────────────┘
                                            │
                                            ↓
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ COMMIT       │ ← │ ACTION       │ ← │ DECISION     │
│ ○            │   │ ○            │   │ ○            │
└──────────────┘   └──────────────┘   └──────────────┘
```

可采用折线型信息流，使视觉上形成完整闭环。

---

## 10. Agent Card 的状态设计

每个阶段卡片有四种主要状态。

### Pending

```text
DECISION

Waiting
```

### Running

```text
INTERPRETATION ●

Updating belief...

6.38s
```

### Completed

```text
INTERPRETATION ✓

Belief
0.61 → 0.73

7.21s
```

### Failed

```text
PERCEPTION !

News Retrieval Failed

Retry 2 / 3
```

---

# 11. Agent Pipeline 中的实时更新

关键原则：

> 不新增 UI 节点，只更新固定节点内部的数据。

例如：

```text
PERCEPTION
```

依次变化：

```text
Loading forum...
```

↓

```text
Forum ✓
Loading news...
```

↓

```text
Forum ✓
News ✓
Retrieving announcements...
```

↓

```text
Forum ✓
News ✓
Announcements ✓
Market Data ●
```

↓

```text
PERCEPTION ✓ 4.21s
```

这样用户可以感受到系统“正在处理”。

---

# 12. Layer 4 — Worker Lanes

由于 TwinMarket 支持并发 Agent，不应该假设只有一个 Agent 在处理。

页面下方提供：

```text
LIVE AGENTS

Worker 01   Agent 083   INTERPRETATION    12.8s
Worker 02   Agent 921   PERCEPTION         6.2s
Worker 03   Agent 124   DECISION          18.1s
Worker 04   Agent 382   COMPLETED         14.7s
```

点击任意 Agent：

```text
Focus Agent → Agent 921
```

主 Agent Pipeline 随之更新。

---

## 13. Serial 模式

如果：

```text
max_workers = 1
```

Worker Lanes 自动退化为：

```text
Current Agent
#10039126898
```

不需要设计第二套 UI。

---

# 14. Agent Queue

除了正在运行的 Agent，还可以显示：

```text
Completed      37
Running         4
Queued         55
Retrying        1
Failed          1
Inactive        2
```

注意：

`Inactive` 应独立于 execution status。

推荐数据模型：

```text
activation:
  active
  inactive

execution:
  pending
  queued
  running
  retrying
  completed
  failed
  skipped
```

---

# 15. Today Summary

运行过程中实时累计当天行为。

建议展示：

```text
TODAY

Agents Completed       37 / 100

Buy                     12
Sell                     7
Hold                    18

Orders                   19
Posts                    31
Interactions             42
Failures                  1
```

其作用不是替代 Agent Pipeline，而是形成市场层面的总体动态。

---

# 16. Recent Events

右侧或底部保留 Event Stream。

示例：

```text
13:42:08 Agent 392810 decision completed
13:42:09 Agent 194820 post generated
13:42:10 Agent 100391 belief updating
13:42:11 Worker 03 LLM response · 3.28s
13:42:13 Agent 182301 retrying retrieval
```

默认只展示高层事件。

详细日志放入：

```text
Diagnostics Drawer
```

不要让主运行页面成为终端日志 viewer。

---

# 17. Market Clearing 视觉阶段

当 Agent Processing 到：

```text
100 / 100
```

主界面应发生明显阶段变化。

例如：

```text
Agent Processing
100 / 100 ✓

Collecting Decisions...
```

随后：

```text
MARKET CLEARING ●

Buy Orders       43
Sell Orders      37

Matched          51
Unmatched        29
```

然后：

```text
Updating Portfolios...
```

最后：

```text
MARKET UPDATE ✓
```

这个阶段非常重要，因为它让用户知道：

> Agent 决策不是模拟终点，市场环境还需要统一处理所有行为。

---

# 18. Social Environment Update

撮合之后展示：

```text
SOCIAL UPDATE ●

Posts        31
Likes        84
Reposts      12
References    7
```

执行过程中动态更新：

```text
Applying forum actions...
```

完成：

```text
SOCIAL UPDATE ✓
```

---

# 19. Day Completion Transition

一个交易日结束时，应进行明显视觉过渡。

例如：

```text
DAY 24 COMPLETED

2023-07-18

100 Agents
80 Orders
51 Trades
31 Posts
103 Social Actions
```

短暂展示后：

```text
Starting Day 25

2023-07-19
```

随后 Day Cycle 重置。

这样比日期数字直接变化更能制造“市场时间推进”的感觉。

---

# 20. 非交易日

非交易日仍可能存在：

- 新闻；
- belief 更新；
- 社交活动；
- Agent 发帖；
- 关系网络变化。

因此 Day Cycle 可以变为：

```text
Environment
    ↓
Agents
    ↓
Market Closed
    ↓
Social Update
    ↓
Commit
```

Market 阶段显示：

```text
Market Closed
No matching executed
```

而不是直接跳过造成 UI 断裂。

---

# 21. Runtime Event Architecture

当前运行日志不足以可靠驱动上述 UI。

应该正式引入：

```text
RuntimeEvent
```

前端不应自行解析普通文本日志来推断状态。

---

## 22. Runtime Event 基础结构

建议：

```json
{
  "event_id": "evt_123",
  "run_id": "run_001",

  "simulation_date": "2023-07-18",

  "scope": "agent",
  "agent_id": "10039126898",
  "worker_id": "worker_01",

  "stage": "perception",
  "substage": "news_retrieval",

  "event": "completed",

  "started_at": "2026-09-14T13:42:01.200Z",
  "ended_at": "2026-09-14T13:42:04.481Z",

  "duration_ms": 3281,

  "attempt": 1,

  "input_summary": {},
  "output_summary": {},

  "message": "Retrieved 8 documents, selected 2"
}
```

---

# 23. 最小事件类型

第一阶段只需要四种：

```text
stage_started
stage_completed
stage_skipped
stage_failed
```

重试可以使用：

```text
stage_retrying
```

---

# 24. Event Scope

建议区分：

```text
run
day
agent
market
social
artifact
system
```

示例：

```text
scope=day
stage=prepare_environment

scope=agent
stage=decision

scope=market
stage=matching

scope=social
stage=forum_actions
```

---

# 25. Agent Stage 枚举

稳定的一级阶段：

```text
state
perception
interpretation
decision
action
commit
```

---

# 26. Agent Substage

Substage 可以随实现变化。

例如：

```text
state
  load_profile
  load_belief
  load_positions

perception
  forum_feed
  public_news
  news_retrieval
  stock_recommendation
  market_data

interpretation
  initial_analysis
  belief_update

decision
  choose_assets
  collect_indicators
  final_decision

action
  order_generation
  post_generation
  forum_intention

commit
  conversation_write
  decision_write
  post_write
```

UI 核心 Pipeline 只绑定 stage。

具体函数变化只需要调整 substage。

---

# 27. Stage Summary Contract

每个 stage 完成后应生成摘要。

例如：

```json
{
  "stage": "perception",
  "duration_ms": 4210,

  "summary": {
    "forum_posts": 5,
    "public_news": 3,
    "retrieved_documents": 8,
    "selected_documents": 2,
    "candidate_assets": 2
  }
}
```

前端不需要理解底层数据库结构。

---

# 28. LLM Runtime Data

对于涉及 LLM 的阶段，建议记录：

```text
provider
model
request_id
latency
input_tokens
output_tokens
retry_count
status
```

不建议默认展示：

- API key；
- 完整 system prompt；
- 完整 private endpoint；
- 完整 hidden reasoning。

---

# 29. Timing Metrics

运行页可以记录三个层级的时间。

### Run

```text
total elapsed
```

### Day

```text
environment prepare
agent processing
matching
social update
commit
```

### Agent

```text
state
perception
interpretation
decision
action
commit
```

这些指标未来也可用于性能分析。

---

# 30. Performance Timeline

高级模式可以增加：

```text
Agent Runtime Timeline
```

例如：

```text
Agent 001 |███ Perception|████ Interpretation|██ Decision|
Agent 002 |██ Perception |██████ Interpretation|█ Decision|
Agent 003 |████ Perception|██ Interpretation|███ Decision|
```

用于分析：

- 哪个 Agent 最慢；
- 哪个阶段是瓶颈；
- LLM latency；
- worker utilization。

MVP 可暂不实现。

---

# 31. Focus Agent 选择策略

默认 Focus Agent 可以采用：

### 方案 A：最近进入新阶段的 Agent

视觉变化丰富。

### 方案 B：当前运行时间最长的 Agent

有助于发现瓶颈。

### 方案 C：Worker 01

行为稳定简单。

建议默认：

> 自动聚焦最近发生阶段变化的 Agent，但当用户手动选择 Agent 后关闭自动切换。

提供：

```text
Auto Follow [ON/OFF]
```

---

# 32. Agent Drawer

点击 Agent 卡片可打开：

```text
Agent Inspector
```

包含：

```text
Profile
Portfolio
Belief History
Perceived Information
Conversation
Decision
Orders
Posts
Runtime Events
```

主页面只展示摘要。

---

# 33. 信息展示层级

建议形成：

```text
Level 1
Runtime Overview

Level 2
Stage Summary

Level 3
Agent Inspector

Level 4
Raw Event / Artifact / Log
```

避免首页一次展示所有数据。

---

# 34. 页面视觉层级

建议四层布局：

```text
LAYER 1
RUN

LAYER 2
DAY CYCLE

LAYER 3
FOCUS AGENT

LAYER 4
SYSTEM ACTIVITY
```

用户第一眼看到的应是：

```text
今天到了哪里？
当前谁在运行？
它正在做什么？
```

而不是：

```text
CPU / Memory / PID / raw log
```

---

# 35. 页面概念线框图

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TwinMarket · Running                          2023-07-18 · Day 24 / 126       │
│ Healthy   Agents 37/100   LLM 182   Elapsed 18m32s                  Stop    │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────── DAY CYCLE ──────────────────────────────────┐
│  Environment      Agent Processing          Market          Social   Commit │
│      ✓                 ● 37 / 100              ○               ○       ○    │
└──────────────────────────────────────────────────────────────────────────────┘


                         CURRENT AGENT

                   #10039126898 · Worker 01
                    Technical · Active

┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ STATE        │ → │ PERCEPTION   │ → │ INTERPRET    │
│ ✓ 0.03s      │   │ ✓ 4.21s      │   │ ● 6.38s      │
│              │   │              │   │              │
│ Cash 32.4%   │   │ 5 posts      │   │ Updating     │
│ 3 positions  │   │ 3 news       │   │ belief       │
│ Bearish .61  │   │ 2 assets     │   │              │
└──────────────┘   └──────────────┘   └──────────────┘
                                             │
                                             ↓
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ COMMIT       │ ← │ ACTION       │ ← │ DECISION     │
│ ○ Waiting    │   │ ○ Waiting    │   │ ○ Waiting    │
└──────────────┘   └──────────────┘   └──────────────┘


┌────────────────────────────── LIVE AGENTS ───────────────────────────────────┐
│ Worker 01  Agent 083   INTERPRETATION       12.8s                           │
│ Worker 02  Agent 921   PERCEPTION            6.2s                           │
│ Worker 03  Agent 124   DECISION             18.1s                           │
│ Worker 04  Agent 382   COMPLETED            14.7s                           │
└──────────────────────────────────────────────────────────────────────────────┘


┌──────────────── TODAY ───────────────┐ ┌──────────── EVENTS ─────────────────┐
│ Buy                 12              │ │ 13:42:08 Decision completed          │
│ Sell                 7              │ │ 13:42:09 Post generated              │
│ Hold                18              │ │ 13:42:10 Belief updating             │
│ Orders              19              │ │ 13:42:11 LLM response · 3.28s        │
│ Posts               31              │ │ ...                                  │
└─────────────────────────────────────┘ └───────────────────────────────────────┘
```

---

# 36. 状态颜色

系统运行状态和市场涨跌颜色必须分离。

Runtime 状态建议：

```text
completed     teal / mint
running       amber / blue
pending       neutral
warning       amber
failed        coral
skipped       brown / gray
```

市场：

```text
up            red
down          green
flat          neutral
```

不能只依赖颜色。

---

# 37. 动效

动效目标：

> 表达运行感，而不是装饰。

建议：

### Running Stage

- 边框轻微 pulse；
- 内部计时器更新；
- 小型 loading indicator。

### Stage Transition

```text
running → completed
```

短暂 highlight。

### Data Flow

阶段之间箭头可以有轻微流动效果。

禁止：

- 大量弹跳；
- 复杂粒子；
- 游戏式动画；
- 长时间阻塞动效。

---

# 38. 运行速度非常快时

若一个 Agent 几百毫秒完成，则 UI 不应强制播放每一步动画。

原则：

```text
Runtime Truth > Animation
```

前端可以批量消费 event。

当处理过快时：

```text
Agent 1 completed
Agent 2 completed
Agent 3 completed
...
```

Focus Agent 显示最新完整快照即可。

---

# 39. 运行速度非常慢时

LLM 调用可能几十秒。

此时必须明确：

```text
INTERPRETATION ●

Waiting for LLM...

Elapsed
18.42s

Model
xxx

Attempt
1 / 3
```

避免用户认为系统卡死。

---

# 40. Retry

重试不应该创建新的 Pipeline。

例如：

```text
PERCEPTION !

News Retrieval
Retrying

Attempt 2 / 3
```

成功后：

```text
PERCEPTION ✓

Completed after retry
7.82s
```

---

# 41. Error

Agent 局部失败：

```text
Agent #123
DECISION ×
```

但 Run 仍可继续。

因此：

```text
Run lifecycle = running
Run health = degraded
```

不要把局部 Agent failure 直接视为整个实验 Failed。

---

# 42. Diagnostics Drawer

主页面只展示：

```text
Warnings
Errors
Retries
Slow Stages
```

展开 Drawer 后再展示：

```text
Runtime Events
Structured Errors
Raw Logs
PID
Exit Code
API Errors
```

---

# 43. 前端数据结构建议

```ts
type RuntimeStage =
  | 'state'
  | 'perception'
  | 'interpretation'
  | 'decision'
  | 'action'
  | 'commit';

type StageStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'skipped'
  | 'failed'
  | 'retrying';

type AgentRuntime = {
  agentId: string;
  workerId?: string;

  activation: 'active' | 'inactive';

  execution:
    | 'pending'
    | 'queued'
    | 'running'
    | 'retrying'
    | 'completed'
    | 'failed'
    | 'skipped';

  currentStage?: RuntimeStage;

  stages: Record<RuntimeStage, StageSnapshot>;

  startedAt?: string;
  completedAt?: string;
};
```

---

# 44. StageSnapshot

```ts
type StageSnapshot = {
  status: StageStatus;

  substage?: string;

  startedAt?: string;
  completedAt?: string;

  durationMs?: number;

  attempt?: number;

  summary?: Record<string, unknown>;

  error?: {
    code?: string;
    message: string;
  };
};
```

---

# 45. DayRuntime

```ts
type DayRuntime = {
  date: string;
  isTradingDay: boolean;

  stage:
    | 'prepare'
    | 'agents'
    | 'market'
    | 'social'
    | 'commit'
    | 'completed';

  agents: {
    total: number;
    active: number;
    queued: number;
    running: number;
    completed: number;
    failed: number;
  };

  actions: {
    buy: number;
    sell: number;
    hold: number;
    posts: number;
    interactions: number;
    orders: number;
  };
};
```

---

# 46. 推荐 API

### Snapshot

```text
GET /api/runs/{runId}/runtime
```

返回：

- Run；
- Day；
- current workers；
- focus agent；
- counters。

### Event Stream

```text
GET /api/runs/{runId}/events
```

建议：

```text
SSE
```

用于推送 RuntimeEvent。

### Agent Runtime

```text
GET /api/runs/{runId}/agents/{agentId}/runtime
```

### Agent Detail

```text
GET /api/runs/{runId}/agents/{agentId}
```

---

# 47. Runtime Event 与普通 Log 的区别

RuntimeEvent：

```text
结构化
稳定 schema
面向产品状态
可以用于 replay
可以计算 duration
可以驱动 UI
```

普通 Log：

```text
面向开发者
文本
schema 不稳定
用于 debug
```

二者不能混为一体。

---

# 48. 可重放性

Runtime Event 的长期价值不仅是实时 UI。

如果所有 Event 被保存：

```text
events.jsonl
```

那么已完成 Run 也可以进入：

```text
Replay Mode
```

用户能够重新播放：

```text
Day 24
Agent 37
Perception
Interpretation
Decision
...
```

这将成为 TwinMarket 非常有辨识度的审计能力。

---

# 49. Replay Mode

未来可以支持：

```text
LIVE
REPLAY
```

相同的 Runtime Observatory UI。

LIVE：

```text
读取 SSE
```

REPLAY：

```text
读取 events.jsonl
```

因此当前 UI 架构设计时就应避免直接绑定实时进程。

---

# 50. MVP 范围

第一版不需要实现所有细节。

建议 MVP：

### 必须

- Run Header；
- Day Cycle；
- Agent Pipeline 六阶段；
- Agent completed / running / queued；
- stage duration；
- Agent Decision 摘要；
- Today counters；
- Event Stream；
- SSE；
- RuntimeEvent；
- day transition。

### 可以延后

- Worker performance timeline；
- token 成本可视化；
- 完整 Agent conversation；
- graph animation；
- Replay；
- runtime comparison；
- stage latency distribution。

---

# 51. 需要修改现有模拟代码的最小范围

核心目标不是重构模拟算法。

只增加：

```text
RuntimeObserver
```

例如：

```python
observer.emit_stage_started(
    scope="agent",
    agent_id=user_id,
    stage="perception",
    substage="news_retrieval",
)
```

然后：

```python
observer.emit_stage_completed(
    ...,
    duration_ms=duration,
    summary={...},
)
```

模拟逻辑保持原样。

---

# 52. Observer 设计原则

模拟模块只负责：

```text
emit()
```

不应该知道：

- React；
- SSE；
- Card；
- Web UI；
- ECharts。

推荐：

```text
Simulation
    ↓
RuntimeObserver
    ↓
Event Store
    ↓
FastAPI
    ↓
SSE
    ↓
React
```

形成明确解耦。

---

# 53. 推荐后端结构

```text
runtime/
├── event.py
├── observer.py
├── event_store.py
├── snapshot.py
└── schemas.py
```

其中：

```text
event.py
RuntimeEvent

observer.py
emit runtime events

event_store.py
append-only JSONL / memory buffer

snapshot.py
events → current runtime state

schemas.py
API contracts
```

---

# 54. 前端组件建议

```text
LiveSimulationView

├── RunHeader
├── DayCycle
├── FocusAgentPanel
│   ├── AgentHeader
│   └── AgentPipeline
│       ├── StateStageCard
│       ├── PerceptionStageCard
│       ├── InterpretationStageCard
│       ├── DecisionStageCard
│       ├── ActionStageCard
│       └── CommitStageCard
│
├── WorkerLanePanel
├── TodaySummary
├── RuntimeEventList
└── RuntimeDiagnosticsDrawer
```

---

# 55. 产品上的核心信息链

整个运行界面最终应始终围绕：

```text
Information
    ↓
Belief
    ↓
Decision
    ↓
Action
    ↓
Environment
    ↓
Next State
```

这是 TwinMarket 相比普通 Agent Simulation Dashboard 最值得突出的地方。

---

# 56. 最终设计原则总结

TwinMarket Runtime Observatory 不应被设计成：

```text
进度条
+
KPI
+
日志
```

而应设计成：

```text
RUN
    ↓
DAY
    ↓
AGENT

State
    ↓
Perception
    ↓
Interpretation
    ↓
Decision
    ↓
Action
    ↓
Commit

    ↓

Market / Social Environment

    ↓

Next Day
```

用户应该能够在不打开代码和日志的情况下理解：

> 当前模拟世界中，谁正在感知什么、形成什么判断、采取什么行为，以及这些行为如何改变环境。

这既是运行反馈，也是 TwinMarket “可观察、可审计、可解释”的核心产品表达。
