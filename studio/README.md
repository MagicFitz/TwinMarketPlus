# TwinMarket Studio（已冻结）

> 此目录仅作为迁移参考保留。产品 Web 与 Electron renderer 统一使用仓库顶层 `frontend/`；不再在这里新增功能或修复与新前端重复的界面。

四个主路由：`/studio/Experiment`、`/studio/Agent`、`/studio/Market`、`/studio/Setting`。

独立于仓库根目录的论文主页。Studio 现在使用真实本地运行目录创建草稿、派发独立模拟 Worker、读取结构化 RuntimeEvent 与查询真实产物；它不生成示例实验、虚构实时价格或测试分数。

## 前后端边界

- `frontend/`：新建实例、LiveSimulationView 与结果表 UI；`src/` 保留 Studio 壳层和只读资源页面。
- `../backend/`：独立 FastAPI 控制/查询面、SQLite Run Registry、Process Manager 与 Worker。
- `../../runtime/`：与 FastAPI/React 解耦的 RuntimeEvent、EventStore、Observer 和 Snapshot Reducer。
- `../../runs/<run_id>/`：每个运行独占的配置快照、`events.jsonl`、`state.json`、数据库、日志和结果产物。

## 本地运行

前端代理 `/api` 到 `127.0.0.1:8766` 的 FastAPI 控制面：

```sh
cd /Users/fitz/Projects/TwinMarket
venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766
```

```sh
cd /Users/fitz/Projects/TwinMarket/studio
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Python 3.10+，Node 18+；浏览器自动化测试使用本机已安装的 Google Chrome。`npm run build` 验证前端构建；没有配置生产 Python API 部署，不能仅发布静态文件就得到数据服务。

## 可验证体验

- Experiment：创建草稿、校验参数、启动/停止/续跑、独立运行目录与配置快照。
- Runtime Observatory：Run/Day/Agent 三个尺度、固定 Day Cycle、六阶段 Agent Pipeline、Worker Lanes、SSE 断线补发、诊断抽屉和完成后的真实结果表。
- Agent：1,000 人基础模板、类型分布、搜索与分页、成员详情；行为金融测试仅预留流程入口。
- Market：环境预览、现有撮合机制、行业指数包、本地行情/新闻/索引库存。
- Setting：模型名称与配置文件存在性、数据源接入规划、浏览器本地密度偏好；不自动测试模型或外部连接。
- 舒适/紧凑保留相同信息，改变留白与行高；断连保留上次数据，错误提示与日志陈旧提示相互独立。

## 数据口径与边界

- `logs_*` 目录暂按一实验/一运行导入；没有编造 Experiment、Group 或 Environment 版本注册表。
- 独立后端的只读服务仍使用 `mode=ro` + `PRAGMA query_only=ON`；新 Registry 默认只写入 `backend/data/` 与当前 `runs/<run_id>/`，不写既有 `logs_*`。这些位置可通过后端环境变量覆盖。
- 仅绑定 loopback；禁止将这个无鉴权的开发服务转发到公网。Vite 开发代理把 `/api` 指向本机 FastAPI。
- 配置只输出白名单参数、模型名称和文件存在性；日志仅抽取正则匹配的运行事件，不返回原始响应、凭据或 HTTP 请求详情。PKL 只检查文件存在性与大小，不反序列化。
- “近期有更新”只表示日志文件新鲜，不表示进程存活。“已完成”必须检测到结束标记。120 秒未更新标记“日志未更新”，不自动判定失败。
- 日期格只在 Profiles 实际有该日记录时标记快照；任一成员出现该日快照不意味着所有成员/日流程完成。多文件读取并非跨文件事务快照。
- 本次交易为 `date_time >= start_date` 的记录数；初始化历史另外显示。未识别来源时显示缺失而非伪造 0。
- 资产价格含初始化历史，使用真实收盘价折线；不画缺少数据支撑的 K 线。资产包权重不等于成员实际组合权重。
- Agent Group、Market Environment、外部连接管理仍属于 P1；P0 只允许新建运行所需的非敏感参数，模型密钥不从 API 返回。
- 当前数据规模下采用 20 条服务端分页和最多 180 个行情点；没有并发写入压力测试或长期监控可靠性验证。

## 验证

```sh
./script/check.sh
```

浏览器检查覆盖四路由、浏览器历史/刷新、成员搜索/分页/抽屉、图表切换、轮询暂停、断连保留与恢复、1024/390 宽度无页面横向溢出、无前端写请求与 POST 拒绝。截图在 `qa/`；设计检查见 `design-qa.md`。

## 组件与许可证

React 19 + Vite；Animal Island UI 1.10.0 的 Button、Tag、Progress、Icon；Lucide 1.45.0；ECharts 6.1.0。壳层、表格、焦点约束抽屉自建。通过 `glyph` 统一图标接入。

Animal Island UI：© guokaigdg，CC BY-NC 4.0，https://github.com/guokaigdg/animal-island-ui 。本原型为非商业本地评估；商业化前需另行核对授权。本项目新增适配代码不改变任何第三方许可证。

对应产品设计：`../docs/UI_DESIGN_ANIMAL_ISLAND_ZH.md`。
