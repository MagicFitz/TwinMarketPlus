---
title: TwinMarket 模拟运行指南
published: true
category: 使用指南
order: 11
---

# TwinMarket 模拟运行指南

本文说明如何使用学院的 `qwen3-30b` vLLM 服务运行 TwinMarket，并通过只读观察器查看进度。所有命令均从仓库根目录执行。

## 1. 环境与数据检查

激活已经初始化好的 Python 3.12 环境：

```bash
source venv/bin/activate
uv pip check --python venv/bin/python
```

项目需要以下核心输入：

- `data/sys_1000.db`：1000 用户模板、历史交易和截至 2023-06-14 的市场状态。
- `data/stock_data.csv`：后续真实行情。
- `data/trading_days.csv`：交易日历。
- `data/sorted_impact_news.pkl`：按日整理的新闻。
- `util/belief/belief_1000_0129.csv`：与 1000 用户模板匹配的初始 belief。
- `data/InformationDB_news_2023/`：使用 `bge-m3` 生成的新闻 FAISS 索引。

可选地重新生成新闻索引：

```bash
python script/build_news_index.py --batch-size 64 --force
```

生成后应看到 3439 个 1024 维向量。原新闻列表的另外两个元素是 `NaN`，不会进入索引。

## 2. 聊天模型配置

`config/api.yaml` 已配置为学院的 OpenAI 兼容 vLLM 服务：

```yaml
api_type: openai
api_key:
  - EMPTY
model_name: qwen3-30b
base_url: http://221.226.39.110:8025/v1
timeout: 300
```

可用下面的命令做轻量预检：

```bash
python - <<'PY'
from openai import OpenAI

client = OpenAI(base_url="http://221.226.39.110:8025/v1", api_key="EMPTY")
response = client.chat.completions.create(
    model="qwen3-30b",
    messages=[{"role": "user", "content": "只回复 OK"}],
    max_tokens=16,
)
print(response.choices[0].message.content)
PY
```

## 3. 用户数量与运行参数

`script/run.sh` 是通用运行入口，模拟用户数量由 `USER_COUNT` 控制。它会从 `data/sys_1000.db` 确定性选择指定数量的用户，并生成用户 ID 完全匹配的 belief 文件。

> 不要把 `util/belief/belief_100.csv` 与 `sys_1000.db` 直接组合；两者的用户 ID 不匹配。运行脚本使用 `belief_1000_0129.csv` 筛选匹配记录。

可配置变量如下：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `USER_COUNT` | `1000` | 模拟用户数，范围 1–1000 |
| `RUN_DIR` | `logs_${USER_COUNT}_qwen3_30b_10td` | 独立输出目录 |
| `START_DATE` | `2023-06-15` | 全新模拟开始日期 |
| `END_DATE` | `2023-06-30` | 模拟结束日期 |
| `MAX_WORKERS` | `32` | 本地并发线程数 |
| `ACTIVATE_PROB` | `0.8` | 每日用户激活概率 |
| `PROB_OF_TECHNICAL` | `0.5` | 技术面噪声交易概率 |
| `PREPARE_ONLY` | `0` | 设为 `1` 时只生成用户数据库和 belief，不启动模拟 |
| `CONFIG_PATH` | `config/api.yaml` | 聊天模型配置 |

运行目录已经存在时脚本会拒绝覆盖；请设置新的 `RUN_DIR` 或先手动归档旧结果。脚本不会修改 `data/sys_1000.db`。

## 4. 运行 10 个交易日

2023-06-15 至 2023-06-30 包含恰好 10 个开市日和 6 个休市自然日。模拟按自然日推进，因此会处理全部 16 天。

1000 用户运行：

```bash
USER_COUNT=1000 \
RUN_DIR="logs_1000_qwen3_30b_10td" \
MAX_WORKERS=32 \
bash script/run.sh
```

100 用户快捷运行：

```bash
bash script/run_100.sh
```

也可以覆盖输出目录或并发数：

```bash
RUN_DIR="logs_100_experiment_02" MAX_WORKERS=64 bash script/run_100.sh
```

默认 `ACTIVATE_PROB=0.8` 表示每天约 80% 的用户调用模型。首次验证吞吐时可降为 `0.05`：

```bash
ACTIVATE_PROB=0.05 RUN_DIR="logs_100_smoke" bash script/run_100.sh
```

如果想先检查生成的 100 用户数据而不启动模型：

```bash
PREPARE_ONLY=1 RUN_DIR="logs_100_prepared" bash script/run_100.sh
```

服务宣称的请求吞吐不等同于本地最优线程数。建议从 32 开始，确认本机数据库写入和日志状态稳定后，再逐级增加到 80、160 或更高。

## 5. 观察运行流程

在另一个终端运行：

```bash
source venv/bin/activate
python script/monitor_simulation.py \
  --log-dir "logs_100_qwen3_30b_10td" \
  --start-date "2023-06-15" \
  --end-date "2023-06-30"
```

观察器每 5 秒刷新，并显示：

- 当前处理日期和已完成交易日进度；
- 用户快照、交易明细和行情表的最新日期；
- 论坛帖子与互动数量；
- 交易决策、帖子、关系图和撮合结果文件数量；
- 日志距上次更新的时间、最近 1 MiB 日志中的疑似错误行数量和日志尾部。

按 `Ctrl-C` 退出观察器不会停止模拟。单次检查和机器可读输出分别使用：

```bash
python script/monitor_simulation.py --log-dir "logs_100_qwen3_30b_10td" --once
python script/monitor_simulation.py --log-dir "logs_100_qwen3_30b_10td" --json
```

## 6. 输出结构

一次正常运行会在对应的 `RUN_DIR` 下产生：

- `user_<用户数>.db`：不断追加用户快照、行情和成交记录；
- `belief_<用户数>.csv`：与选中用户匹配的初始 belief；
- `forum_<用户数>.db`：帖子、引用和互动；
- `trading_records/YYYY-MM-DD.json`：用户交易决策；
- `reaction_records/YYYY-MM-DD.json`：论坛互动决策；
- `post_records/YYYY-MM-DD.json`：发帖决策；
- `conversation_records/YYYY-MM-DD/*.json`：模型对话；
- `graphs/*.pkl`：每日用户关系图；
- `simulation_results/YYYY-MM-DD/`：每日撮合与汇总结果；
- `simulation.log`：完整控制台日志。

## 7. 中断与续跑注意事项

- 停止模拟使用 `Ctrl-C`，不要同时启动两个进程写同一组数据库。
- 当前程序以 `start_date == 2023-06-15` 判断“全新运行”；其他开始日期会进入 checkpoint 模式。
- 续跑前先复制整个运行目录作为备份，再使用原来的 `user` 和 `forum` 数据库。
- `init_system` 会清理开始日期之后的数据库记录，因此续跑日期必须与已有输出状态一致。
- 如果日志长期不更新，先检查模型接口，再查看观察器列出的错误行和最后处理日期。
