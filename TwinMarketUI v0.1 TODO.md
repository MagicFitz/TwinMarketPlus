# TwinMarketUI v0.1 TODO

> 目标：交付第一个可以真实使用的 TwinMarket 图形界面，而不是完成最终产品架构。

## 0. v0.1 要回答的问题

v0.1 只验证一个问题：

**用户能否通过图形界面创建一个 TwinMarket 仿真，并理解仿真正在发生什么以及最终发生了什么？**

核心闭环：

```
Create → Run → Observe → Results
```

首版默认场景：

- 单用户
- 单机
- 同时最多运行 1 个仿真实例
- 10 Agents
- 2 个交易日
- 使用现有 Runtime、FastAPI、Registry 和 RuntimeEvent 基础设施
- 不要求最终目录架构
- 不要求生产级可靠性
- 不要求 Electron

# P0 — v0.1 必须完成

## 1. Create

- 提供 `/runs/new` 创建页面
- 用户可以设置：
  - Run Name
  - Agent 数量
  - 起止日期
  - 随机种子
- 其他参数使用默认配置或折叠在 Advanced 中
- 创建成功后生成唯一 `run_id`
- 创建后进入 Run 页面

### 验收

用户能够创建：

```
10 Agents × 2 Trading Days
```

的真实仿真实例。

## 2. Run

- 提供 Start 按钮
- 点击后启动真实 Python simulation
- 防止重复点击启动
- 显示基本 Run 状态：

```
draft / running / completed / failed / cancelled
```

- 提供 Stop

### 验收

点击 Start 后：

```
UI → API → Worker → simulation.py
```

真实执行。

## 3. Runtime Observatory

页面只展示三层状态。

### Run

显示：

- 当前状态
- Day X / N
- 当前阶段
- 已处理 Agent 数量
- 累计运行时间

### Day

固定展示：

```
Prepare → Agents → Market → Social → Commit
```

每个阶段只需要：

- waiting
- running
- completed
- failed / skipped

### Agent

显示当前或选中的 Agent：

```
State → Perception → Interpretation → Decision → Action → Commit
```

每个阶段展示：

- 状态
- 耗时
- 简短结果摘要

不得展示：

- Chain-of-Thought
- 完整 Prompt
- 完整模型原始输出

### Today Summary

只显示：

- Buy
- Sell
- Hold
- Orders
- Failures

### 实时通信

- 页面可以接收 RuntimeEvent
- 页面刷新后能够重新读取当前 Snapshot
- 不要求 v0.1 完成复杂 SSE 恢复机制

### 验收

用户能够回答：

1. 仿真运行到第几天？
2. 当前正在处理什么？
3. 哪个 Agent 正在决策？
4. Agent 做出了什么行为？
5. 当前市场发生了什么？

## 4. Results

Run 完成后只提供三个视图：

### Summary

- 每日基本统计
- Buy / Sell / Hold
- 成交数量

### Trades

- 时间
- Agent
- Asset
- Side
- Price
- Quantity

### Agents

- Agent
- Decision
- Action
- Final State / Summary

### 验收

所有展示数据必须来自真实 simulation output。

缺失数据显示：

```
Unavailable
```

而不是自动填充为 0。

## 5. 最小可靠性

v0.1 只保证：

- Worker 不阻塞 HTTP 请求
- 同一个 Run 不重复启动 Worker
- 页面刷新不会终止 simulation
- simulation 完成后状态正确变成 completed
- simulation 失败后状态正确变成 failed
- Stop 后进入 cancelled
- RuntimeEvent 写入失败不改变市场仿真结果

暂时不要求：

- FastAPI 重启后恢复运行任务
- 完整 heartbeat/stale Worker 检测
- SSE Last-Event-ID 完整恢复
- Snapshot 增量缓存
- Worker crash 自动恢复
- checkpoint resume 的所有边缘情况

## 6. 最小测试

必须：

- RuntimeEvent 基础测试
- Run 生命周期基础测试
- API create/start/stop 测试
- 一条端到端 smoke test：

```
Create → Start → Events → Complete → Results
```

- 前端可以成功 production build

暂时不要求：

- 完整 UI 自动化测试
- SSE 网络异常测试矩阵
- API 重启恢复集成测试
- 大规模性能测试

# Definition of Done

TwinMarketUI v0.1 完成的标准只有：

- 用户可以创建一个 10 Agent / 2 Day Run
- 点击 Start 后真实 simulation 启动
- Observatory 可以看到 Day / Agent / Market 的实时过程
- 刷新页面后可以恢复当前显示状态
- Run 完成后可以查看 Summary / Trades / Agents
- 所有核心数据显示都来自真实 simulation
- 一条完整端到端 smoke run 可以稳定通过

达到以上条件立即停止增加功能，发布 v0.1 并开始实际使用。

# P1 — v0.1 完成后

以下内容不阻塞 v0.1：

## Architecture

- 独立 `backend/`
- 消除 `studio.*` dependency
- service 分层
- API contract 清理
- TypeScript API 类型生成

## UI Engineering

- 完整 shadcn Design System
- Dark Mode
- 响应式细节
- 完整 loading / empty / error 状态
- Accessibility 完善
- Advanced Diagnostics
- Recent Events filters
- Worker Lanes

## Runtime Reliability

- heartbeat
- stale Worker detection
- FastAPI restart recovery
- SSE reconnect / Last-Event-ID
- incremental Snapshot
- checkpoint/resume 完整可靠性

## Results

- 高级筛选
- 排序
- 大表分页
- 导出
- 跨实验比较
- Runtime Replay

# P2 — 产品化

- Electron
- Python sidecar packaging
- API Key 系统凭据存储
- userData migration
- macOS packaging / signing
- 自动升级
- 多用户
- PostgreSQL / Redis / Queue
- 大规模 simulation
- 成本统计
- 完整审计与实验管理