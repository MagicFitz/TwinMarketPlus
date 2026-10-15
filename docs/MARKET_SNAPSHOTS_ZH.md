---
title: Tushare 日级市场快照使用指南
published: true
category: 使用指南
order: 36
---

# Tushare 日级市场快照

本次实现设计文档中的阶段 0 与阶段 1：手动连接 Tushare、同步收盘后行情、合成现有 10 个自定义指数、发布不可变快照，并固定 Run 的市场输入。新闻、资金流、申万基准、盘中预览和自动调度仍属于后续阶段。

## 使用流程

1. 在 Studio 的 Setting → 金融数据源新增 Tushare Token，保存后测试交易日历、日线和估值接口。Token 不回显。测试表示接口权限可用，数据完整性由同步校验决定。
2. 在 Market → 数据工作台选择增量更新或指定日期回补。交易日历和日线必选，估值可选。明确允许无新闻环境后创建同步任务。
3. 独立 Worker 拉取数据，保存原始成功响应和请求清单，生成兼容文件，完成质量校验后原子发布。页面每 3 秒读取持久化进度，刷新页面不会丢失任务。取消在请求之间和重试等待中检查，已发布快照不受影响。
4. 查看快照的质量报告、文件指纹、成分与权重，点击“设为新实验默认”。也可激活旧快照来回退默认环境。
5. 创建实验时选择市场环境快照并明确允许无新闻模式。日期须在可运行覆盖范围内，并有至少 30 个先前交易日。快照缺失或日期越界时不能创建或启动实验。

同步不会覆盖 `data/stock_data.csv`、基础用户数据库或既有 Run。新默认只影响以后创建的实验，复制旧 Run 默认沿用原快照。Run 离开 draft 后不可修改配置。

## 数据语义

- `data/market_assets.yaml` 固定现有 50 只成分股。科技与通信、金融服务原百分比存在万分之一舍入误差，定义记录原始权重并按比例归一到 1。快照记录定义文件指纹。
- 日线按交易日拉取全市场截面，仅持久化这 50 只股票。达到接口行数上限时分页，重复页面直接失败，避免静默截断。
- 采用固定权重收益率链式计算，首个同步日期桥接前一日期的旧指数收盘点位；缺失成分贡献 0 收益，不重新归一。有效权重低于 80% 阻止发布，低于 95% 给出警告。
- 成交量从“手”转换为“股”，成交额从“千元”转换为“元”。旧历史没有可信成交量单位，保留原值，不把旧成交额冒充新增成分股成交量；单位限制记录在快照中。
- 正 PE/PB/PS 使用倒数加权，估值有效权重不足 80% 时为空；股息率按有效权重求和。每日估值无权限时降级为空，限流或网络故障重试，最终失败保留旧快照。
- MA5/10/30 和成交量均线只从截至对应日期的指数序列计算。资金流在本期新增日期为空值。
- 本期整个快照的新闻容器为空，历史新闻也不沿用。模拟进程使用空新闻检索器，不读取旧年份索引、不初始化嵌入客户端、不在快照目录创建文件。Run 清单及运行台记录此研究限制。
- 增量重拉最近 3 个交易日，供应商修订只进入新快照。日历存在缺口、交易日行情不齐、重复主键、无效价格或指纹不符时拒绝发布/使用。
- 单一 Tushare 数据源同一时间只允许一个写任务，避免相互重叠及基准切换。失败 staging 保留在本地供诊断，可在任务终止后由运维清理。

官方协议与字段依据：[HTTP API](https://tushare.pro/document/2?doc_id=40)、[日线](https://tushare.pro/document/2?doc_id=27)、[交易日历](https://tushare.pro/document/2?doc_id=26)、[每日指标](https://tushare.pro/document/2?doc_id=32)。

## 本地存储与凭据

- Registry：配置 Run Registry 同目录下的 `market.sqlite3`，保存任务、能力测试和快照元数据，不保存 Token。
- 凭据优先读取 `TUSHARE_TOKEN`；否则保存到 `config/data_sources.yaml`，权限 `0600`。API 省略 `token` 保留，空字符串或 null 清除本地值；环境变量优先级不变。更新 Token 会重置旧能力测试。
- `data/market_staging/<job_id>` 保存未发布数据；`data/market_snapshots/<snapshot_id>` 保存发布数据。
- 发布目录包含兼容 CSV/Pickle、版本化资产定义、压缩 JSONL 原始和规范化数据、请求清单及 `snapshot.json`。发布文件设为只读，使用前检查 SHA-256。
- 服务端固定使用 Tushare 官方 HTTPS API，禁止自定义 URL；不记录供应商原始错误文本或网络异常中的敏感请求信息。
- 凭据、staging 和快照均已加入 Git 忽略。实际行情与新闻不随代码 PR 发布。

## Run 数据隔离

Run 创建时写入 `market_snapshot_id`、数据能力、转换版本、资产定义哈希、文件指纹和质量警告。Worker 开始/续跑前复查完整性，然后显式传递 `TWINMARKET_DATA_DIR` 和快照标识；Tushare Token 从模拟 Worker 环境中移除。

准备脚本仅在 Run 私有数据库中替换 `StockData`，写入开始日前的历史，并把用户初始账户对齐到前一自然日、按可观察收盘价重算当前持仓价值。模拟当天真实收盘只用于撮合后的基准校准。开市判断使用 `cal_date` 与 `is_open`，空新闻日期安全返回空列表。

新建 Run 与续跑现在通过显式 `--checkpoint` 区分，开始日期不再硬编码到 2023-06-15。旧 shell 契约续跑时自动传递该参数；直接调用 `simulation.py` 续跑时需显式添加 `--checkpoint`。

## CLI

```sh
python script/sync_market_data.py --allow-missing-news
python script/sync_market_data.py --start-date 2025-01-13 --end-date 2025-01-14 --allow-missing-news
python script/sync_market_data.py --allow-missing-news --without-valuations --activate
```

没有 `--activate` 时只生成快照。结束日期不得晚于 Asia/Shanghai 最近可用的收盘日；当天数据在 18:45 后才允许同步。接口实际入库不足时仍会被质量门槛阻止。

## 验证

离线测试使用固定假 Tushare 响应，覆盖凭据保留/替换/清除、权限和限流、分页、单位、链式指数、空值、日历、发布、取消、重复同步、重启持久化、快照损坏、默认切换和 Run 日期边界。

烟雾测试从真实模板复制 1 个用户，运行 2 个交易日，使用假模型响应，执行真实感知、订单生成、撮合、结算和结果查询。测试分别确认观察截止于 2025-01-10 和 2025-01-13，不泄漏当日或未来收盘数据。单用户没有对手方，零成交是预期结果。

```sh
python -m unittest discover -s backend/tests -q
python -m unittest discover -s tests -q
npm run build --prefix studio
npm run test:sites --prefix studio
npm run build --prefix frontend
npm run test --prefix frontend
```

运行接口测试需要安装 `httpx`。外部 Tushare 账户授权和真实供应商入库仍需使用账户 Token 验收；离线测试不会消耗账户额度。
