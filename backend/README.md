# TwinMarket Backend

`backend/` 是独立的 FastAPI 控制和查询面。它管理 Run Registry、后台 Worker、RuntimeEvent/SSE、结果产物，以及 Studio 所需的只读 catalog、文档、Agent、Market 和日志接口；后端生产代码不依赖 `studio.*`。

## 启动

从仓库根目录安装后端和模拟运行依赖：

```sh
venv/bin/python -m pip install -r backend/requirements.txt
venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766
```

开发中的 Studio 前端仍把 `/api` 代理到 `127.0.0.1:8766`，因此 API 路径、响应结构和错误状态保持不变。

## 配置

以下环境变量由 HTTP 服务与它启动的 Worker 共同使用。相对路径以 `TWINMARKET_PROJECT_ROOT` 为基准；项目根本身的相对值以启动时的当前目录为基准。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `TWINMARKET_PROJECT_ROOT` | 仓库根目录 | 模拟代码、配置和文档根目录 |
| `TWINMARKET_DATA_DIR` | `data/` | 后端读取的模板、市场与索引数据目录 |
| `TWINMARKET_RUNS_DIR` | `runs/` | 新运行的独占输出目录 |
| `TWINMARKET_REGISTRY_PATH` | `backend/data/runs.sqlite3` | SQLite Run Registry 文件 |
| `TWINMARKET_ALLOWED_ORIGINS` | `http://127.0.0.1:5173` | 逗号或换行分隔的 CORS 前端 origin 列表 |

例如：

```sh
export TWINMARKET_PROJECT_ROOT=/srv/twinmarket
export TWINMARKET_DATA_DIR=/srv/twinmarket/data
export TWINMARKET_RUNS_DIR=/var/lib/twinmarket/runs
export TWINMARKET_REGISTRY_PATH=/var/lib/twinmarket/runs.sqlite3
export TWINMARKET_ALLOWED_ORIGINS=https://studio.example.test
venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766
```

如果需要继续查看迁移前的本地草稿，可把 `TWINMARKET_REGISTRY_PATH` 指向旧的 `studio/backend/data/runs.sqlite3`；该文件不会由迁移自动删除。

## 验证

```sh
./script/check.sh
```

该命令分别检查核心仿真、独立后端和 Studio 前端。

## 日级市场快照

Tushare 连接、独立同步 Worker、不可变快照和 Run 输入隔离见 [使用指南](../docs/MARKET_SNAPSHOTS_ZH.md)。本期接入交易日历、日线及可选每日估值；新闻缺失必须明确允许。运行接口测试可安装 `backend/requirements-dev.txt`。
