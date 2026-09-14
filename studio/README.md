# TwinMarket Read-only Studio

四个主路由：`/studio/Experiment`、`/studio/Agent`、`/studio/Market`、`/studio/Setting`。

独立于仓库根目录的论文主页，不改变模拟入口、数据库结构或已有运行。原型使用真实本地数据，不生成示例实验、虚构实时价格或测试分数。

## 本地运行

前端已在 `http://127.0.0.1:5173/studio/Experiment` 启动，数据适配器在 `127.0.0.1:8766`。重启时在两个终端执行：

```sh
cd /Users/fitz/Projects/TwinMarket/studio
python3 server.py
```

```sh
cd /Users/fitz/Projects/TwinMarket/studio
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Python 3.10+，Node 18+；浏览器自动化测试使用本机已安装的 Google Chrome。`npm run build` 验证前端构建；没有配置生产 Python API 部署，不能仅发布静态文件就得到数据服务。

## 可验证体验

- Experiment：切换本地运行、查看配置、5 秒轮询、暂停/手动读取、日期快照、成员档案、行情曲线/数据表、日志事件与产物数量。
- Agent：1,000 人基础模板、类型分布、搜索与分页、成员详情；行为金融测试仅预留流程入口。
- Market：环境预览、现有撮合机制、行业指数包、本地行情/新闻/索引库存。
- Setting：模型名称与配置文件存在性、数据源接入规划、浏览器本地密度偏好；不自动测试模型或外部连接。
- 舒适/紧凑保留相同信息，改变留白与行高；断连保留上次数据，错误提示与日志陈旧提示相互独立。

## 数据口径与边界

- `logs_*` 目录暂按一实验/一运行导入；没有编造 Experiment、Group 或 Environment 版本注册表。
- SQLite 使用 `mode=ro` + `PRAGMA query_only=ON`。API 无写入路由；POST/PUT/PATCH/DELETE 返回 405。
- 仅绑定 loopback；禁止将这个无鉴权的开发服务转发到公网。Vite 开发代理把 `/api` 指向本机适配器。
- 配置只输出白名单参数、模型名称和文件存在性；日志仅抽取正则匹配的运行事件，不返回原始响应、凭据或 HTTP 请求详情。PKL 只检查文件存在性与大小，不反序列化。
- “近期有更新”只表示日志文件新鲜，不表示进程存活。“已完成”必须检测到结束标记。120 秒未更新标记“日志未更新”，不自动判定失败。
- 日期格只在 Profiles 实际有该日记录时标记快照；任一成员出现该日快照不意味着所有成员/日流程完成。多文件读取并非跨文件事务快照。
- 本次交易为 `date_time >= start_date` 的记录数；初始化历史另外显示。未识别来源时显示缺失而非伪造 0。
- 资产价格含初始化历史，使用真实收盘价折线；不画缺少数据支撑的 K 线。资产包权重不等于成员实际组合权重。
- 资源创建、编辑、同步、连接测试、实验启停均只展示规划说明，不执行动作。结果页目前只读行情与产物计数，不声称已完成完整分析工作台。
- 当前数据规模下采用 20 条服务端分页和最多 180 个行情点；没有并发写入压力测试或长期监控可靠性验证。

## 验证

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
node scripts/smoke.mjs
npm run build
npm run test:sites
```

浏览器检查覆盖四路由、浏览器历史/刷新、成员搜索/分页/抽屉、图表切换、轮询暂停、断连保留与恢复、1024/390 宽度无页面横向溢出、无前端写请求与 POST 拒绝。截图在 `qa/`；设计检查见 `design-qa.md`。

## 组件与许可证

React 19 + Vite；Animal Island UI 1.10.0 的 Button、Tag、Progress、Icon；Lucide 1.45.0；ECharts 6.1.0。壳层、表格、焦点约束抽屉自建。通过 `glyph` 统一图标接入。

Animal Island UI：© guokaigdg，CC BY-NC 4.0，https://github.com/guokaigdg/animal-island-ui 。本原型为非商业本地评估；商业化前需另行核对授权。本项目新增适配代码不改变任何第三方许可证。

对应产品设计：`../docs/UI_DESIGN_ANIMAL_ISLAND_ZH.md`。
