import React, { useEffect, useRef, useState } from "react";
import {
  Button,
  Icon,
  Tag,
  Tooltip,
  Card,
  Background,
  Input,
  Select,
  Drawer,
  CodeBlock,
} from "animal-island-ui";
import { Documentation } from "./Documentation.jsx";
import {
  LiveSimulationView,
  RunComposer,
} from "../frontend/LiveSimulationView.jsx";

// animal-island-ui 使用字符串形式的图标名称；集中声明可避免在 JSX 中散落魔法字符串。
const FlaskConical = "Compass";
const Users = "User";
const ChartNoAxesCombined = "Globe";
const Settings2 = "Settings";
const ArrowUpRight = "Share";
const RefreshCw = "Refresh";
const Leaf = "Leaf";
const Search = "Search";
const ChevronRight = "Play";
const X = "Close";
const Database = "Folder";
const Radio = "Wifi";
const Layers = "Chat";
const CircleHelp = "Bulb";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

// 按需注册 ECharts 模块，避免引入未使用的图表类型和渲染器。
echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

// 左侧导航的路由段、显示名称和图标。
const spaces = [
  { id: "Experiment", name: "实验空间", icon: FlaskConical },
  { id: "Agent", name: "智能体群体", icon: Users },
  { id: "Market", name: "市场环境", icon: ChartNoAxesCombined },
  { id: "Setting", name: "全局设置", icon: Settings2 },
  { id: "Documentation", name: "文档", icon: "Book" },
];
// 统一处理空值与中文数字格式，保证表格、指标和提示中的展示口径一致。
const n = (value) =>
  value == null
    ? "—"
    : Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
const time = (value) =>
  value ? new Date(value).toLocaleTimeString("zh-CN", { hour12: false }) : "—";
const glyph = (icon, size = 18) => <Icon name={icon} size={size} />;

// 后端运行状态到界面文案的映射。
const statusNames = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  stopping: "正在停止",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  stale: "日志未更新",
  observed: "近期有更新",
  unknown: "状态未知",
  unavailable: "数据不可用",
};
function Badge({ children, tone = "app-teal" }) {
  return (
    <Tag size="small" color={tone} variant="soft">
      {children}
    </Tag>
  );
}

/**
 * 读取 Runtime API，并可选地按 interval 轮询。
 *
 * 保留同一 URL 的上一份数据，可让刷新过程避免闪烁；AbortController 和 alive 标记则
 * 防止组件卸载或请求切换后继续写入状态。
 */
function useData(url, refresh = 0, interval = 0) {
  const [state, set] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true,
      pending = false;
    const controller = new AbortController();
    set((s) => ({
      data: s.url === url ? s.data : null,
      url,
      error: null,
      loading: true,
    }));
    async function read() {
      if (pending || !url) return;
      pending = true;
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error("数据连接暂不可用");
        const data = await response.json();
        if (alive)
          set((previous) => ({
            data:
              previous.url === url &&
              JSON.stringify(previous.data) === JSON.stringify(data)
                ? previous.data
                : data,
            url,
            error: null,
            loading: false,
          }));
      } catch (error) {
        if (alive && error.name !== "AbortError")
          set((s) => ({ ...s, error: error.message, loading: false }));
      } finally {
        pending = false;
      }
    }
    read();
    const timer = interval ? setInterval(read, interval) : null;
    return () => {
      alive = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [url, refresh, interval]);
  return state.url && state.url !== url
    ? { data: null, error: null, loading: true }
    : state;
}

// 统一提示按钮的鼠标与键盘行为，使禁用操作也能通过 Tooltip 说明原因。
function HintAnchor({
  onMouseEnter,
  onMouseLeave,
  children,
  disabled = false,
  primary = false,
  ...props
}) {
  const events = {
    onMouseEnter,
    onMouseLeave,
    onFocus: onMouseEnter,
    onBlur: onMouseLeave,
    onClick: onMouseEnter,
    onKeyDown: (e) => {
      if (e.key === "Escape") onMouseLeave?.(e);
    },
  };
  if (disabled)
    return (
      <span {...props} {...events} tabIndex={0} className="disabled-action">
        <Button type={primary ? "primary" : "default"} disabled>
          {children}
        </Button>
      </span>
    );
  return (
    <Button {...props} {...events} type="text" size="small">
      {children}
    </Button>
  );
}

// 根据触发器距视窗边缘的位置调整提示框，避免长提示内容被裁切。
function Hint({ title, label = "查看说明", children, long = false }) {
  const [placement, setPlacement] = useState("bottom");
  const position = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    setPlacement(
      box.left < 180
        ? "bottom-start"
        : window.innerWidth - box.right < 180
          ? "bottom-end"
          : "bottom",
    );
  };
  return (
    <Tooltip
      title={title}
      variant={long ? "island" : "default"}
      bordered
      placement={placement}
    >
      <HintAnchor aria-label={label} onMouseEnter={position}>
        {children || glyph(CircleHelp, 16)}
      </HintAnchor>
    </Tooltip>
  );
}

// 当前尚未实现的写操作使用此组件，明确告知用户页面是只读的。
function PlannedButton({ children, primary = false }) {
  const [placement, setPlacement] = useState("bottom");
  const position = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    setPlacement(
      box.left < 180
        ? "bottom-start"
        : window.innerWidth - box.right < 180
          ? "bottom-end"
          : "bottom",
    );
  };
  return (
    <Tooltip title="只读模式，暂未开放。" bordered placement={placement}>
      <HintAnchor
        disabled
        primary={primary}
        onMouseEnter={position}
        aria-label={`${children}（暂未开放）`}
      >
        {children}
      </HintAnchor>
    </Tooltip>
  );
}

// 手动实现左右方向键、Home 和 End 的可访问 Tabs 键盘交互。
function Tabs({ items, value, onChange, panelId }) {
  return (
    <div
      className="tabs"
      role="tablist"
      aria-label="内容视图"
      onKeyDown={(e) => {
        const index = items.findIndex(([id]) => id === value);
        const next =
          e.key === "ArrowRight"
            ? (index + 1) % items.length
            : e.key === "ArrowLeft"
              ? (index + items.length - 1) % items.length
              : e.key === "Home"
                ? 0
                : e.key === "End"
                  ? items.length - 1
                  : null;
        if (next !== null) {
          e.preventDefault();
          onChange(items[next][0]);
          e.currentTarget.querySelectorAll('[role="tab"]')[next].focus();
        }
      }}
    >
      {items.map(([id, label]) => (
        <Button
          key={id}
          id={`${panelId}-${id}`}
          type={value === id ? "primary" : "text"}
          size="small"
          role="tab"
          aria-selected={value === id}
          aria-controls={panelId}
          tabIndex={value === id ? 0 : -1}
          onClick={() => onChange(id)}
        >
          {label}
        </Button>
      ))}
    </div>
  );
}

// 可复用的展示层组件：空状态、面板、指标卡、键值定义列表和详情抽屉。
function Empty({ state }) {
  return (
    <div className="empty">
      {state.error || (state.loading ? "读取中…" : "暂无数据")}
    </div>
  );
}
function Panel({ title, subtitle, action, children, className = "" }) {
  return (
    <Card className={`panel ${className}`}>
      <div className="panel-heading">
        <div className="inline">
          <h2>{title}</h2>
          {subtitle && (
            <Hint
              title={subtitle}
              label={`${title}说明`}
              long={subtitle.length > 35}
            />
          )}
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}
function Metric({ label, value, foot, icon }) {
  return (
    <Card className="metric">
      <div className="metric-label">
        <span>{label}</span>
        <Hint title={foot} label={`${label}口径`} long>
          {glyph(icon, 20)}
        </Hint>
      </div>
      <strong>{n(value)}</strong>
    </Card>
  );
}
function Definition({ values }) {
  return (
    <dl className="definitions">
      {values.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{value ?? "未记录"}</dd>
        </div>
      ))}
    </dl>
  );
}

function Inspector({ drawer, close }) {
  return (
    <Drawer
      open={!!drawer}
      title={drawer?.title}
      onClose={close}
      pushBackground={false}
      width="min(520px, 100vw)"
    >
      {drawer?.content}
    </Drawer>
  );
}

// 成员详情在打开抽屉后才请求，避免主列表为每位成员预加载完整持仓。
function AgentDetail({ run, id }) {
  const state = useData(
    `/api/runs/${encodeURIComponent(run)}/agents/${encodeURIComponent(id)}`,
  );
  if (!state.data) return <Empty state={state} />;
  const a = state.data;
  return (
    <>
      <Badge>数据库快照</Badge>
      <Definition
        values={[
          ["Agent ID", a.user_id],
          ["投资者类型", a.user_type],
          ["地区", a.location],
          ["处置效应", a.disposition],
          ["彩票偏好", a.lottery],
          ["分散投资特征", a.diversification],
          ["当前现金", n(a.current_cash)],
          ["总资产", n(a.total_value)],
          ["快照时间", a.created_at],
        ]}
      />
      <h3>当前持仓</h3>
      <CodeBlock code={JSON.stringify(a.positions, null, 2)} copyable={false} />
      <h3>策略摘要</h3>
      <p className="prose">{a.strategy || "该成员尚无策略记录。"}</p>
    </>
  );
}

// 搜索输入经 250ms 防抖后才更新查询参数，减少输入过程中的 API 请求。
function Agents({ run = "template", refresh = 0, open }) {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(search);
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);
  const state = useData(
    `/api/runs/${encodeURIComponent(run)}/agents?q=${encodeURIComponent(q)}&page=${page}`,
    refresh,
  );
  return (
    <Panel
      title="成员档案"
      subtitle="最新可用快照 · 点击成员查看行为特征与持仓"
      action={
        <div className="search">
          <Input
            size="small"
            prefix={glyph(Search, 16)}
            aria-label="搜索成员"
            placeholder="ID、类型或地区"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      }
    >
      {state.error && <p className="warning">{state.error}</p>}
      {state.data ? (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Agent ID</th>
                  <th>类型 / 地区</th>
                  <th>处置效应</th>
                  <th>彩票偏好</th>
                  <th className="number">总资产</th>
                  <th>快照日期</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {state.data.items.map((a) => (
                  <tr key={a.user_id}>
                    <td>
                      <Button
                        type="text"
                        className="text-link"
                        onClick={() =>
                          open({
                            title: `Agent ${a.user_id}`,
                            content: <AgentDetail run={run} id={a.user_id} />,
                          })
                        }
                      >
                        {a.user_id}
                      </Button>
                    </td>
                    <td>
                      {a.user_type}
                      <small>{a.location}</small>
                    </td>
                    <td>{a.disposition}</td>
                    <td>{a.lottery}</td>
                    <td className="number">{n(a.total_value)}</td>
                    <td className="muted">{a.created_at?.slice(0, 10)}</td>
                    <td>{glyph(ChevronRight, 14)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!state.data.items.length && (
              <div className="empty">没有匹配的成员</div>
            )}
          </div>
          <div className="pagination">
            <span>共 {n(state.data.total)} 位成员 · 每页 20 位</span>
            <div>
              <Button
                size="small"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                上一页
              </Button>
              <span>
                {page} / {Math.max(1, Math.ceil(state.data.total / 20))}
              </span>
              <Button
                size="small"
                disabled={page * 20 >= state.data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </Button>
            </div>
          </div>
        </>
      ) : (
        <Empty state={state} />
      )}
    </Panel>
  );
}

// ECharts 实例的创建、ResizeObserver 订阅和销毁都限定在同一个 effect 生命周期中。
function PriceChart({ prices }) {
  const el = useRef(null);
  useEffect(() => {
    const chart = echarts.init(el.current);
    chart.setOption({
      animation: false,
      grid: { left: 57, right: 20, top: 18, bottom: 30 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: prices.map((p) => p.date),
        boundaryGap: false,
        axisLabel: { color: "#878b7c", fontSize: 10 },
        axisLine: { lineStyle: { color: "#e7e9df" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#878b7c", fontSize: 10 },
        splitLine: { lineStyle: { color: "#edf0e8", type: "dashed" } },
      },
      series: [
        {
          type: "line",
          data: prices.map((p) => p.close_price),
          showSymbol: false,
          lineStyle: { color: "#479c83", width: 2.5 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#d0e9dc" },
              { offset: 1, color: "#ffffff00" },
            ]),
          },
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [prices]);
  return (
    <div
      ref={el}
      className="price-chart"
      role="img"
      aria-label={`收盘价曲线，共 ${prices.length} 个观测点；可切换数据表读取数值`}
    />
  );
}

// 行情组件支持在图表和可读取的表格间切换，二者共用同一份 API 数据。
function MarketChart({ run = "template", refresh = 0 }) {
  const [asset, setAsset] = useState("");
  const [table, setTable] = useState(false);
  const state = useData(
    `/api/runs/${encodeURIComponent(run)}/market?asset=${asset}`,
    refresh,
  );
  if (!state.data)
    return (
      <Panel title="行情观察">
        <Empty state={state} />
      </Panel>
    );
  const d = state.data,
    last = d.prices.at(-1);
  return (
    <Panel
      title="行情观察"
      subtitle={`${d.source}，最近 ${d.prices.length} 个观测点。包含初始化历史；非实时交易报价，使用收盘价而非 OHLC。`}
      action={
        <div className="inline">
          <div className="asset-select" aria-label="选择资产">
            <Select
              aria-label="选择资产"
              value={d.selected}
              onChange={setAsset}
              options={d.assets.map((a) => ({
                key: a.stock_id,
                label: `${a.name} · ${a.stock_id}`,
              }))}
            />
          </div>
          <Button
            type="text"
            className="text-link"
            onClick={() => setTable((v) => !v)}
          >
            {table ? "查看曲线" : "查看数据"}
          </Button>
        </div>
      }
    >
      {state.error && <p className="warning">{state.error}，保留上次数据</p>}
      <div className="chart-summary">
        <strong>{n(last?.close_price)}</strong>
        <span>收盘价</span>
        <Badge tone="default">截至 {last?.date || "—"}</Badge>
      </div>
      {table ? (
        <div className="table-wrap chart-table">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>收盘价</th>
                <th>变动 (%)</th>
                <th>成交量</th>
              </tr>
            </thead>
            <tbody>
              {[...d.prices].reverse().map((p) => (
                <tr key={p.date}>
                  <td>{p.date}</td>
                  <td>{n(p.close_price)}</td>
                  <td>{n(p.pct_chg)}</td>
                  <td>{n(p.vol)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <PriceChart prices={d.prices} />
      )}
    </Panel>
  );
}

// 页面级视图：实验、Agent 群体、市场和设置。
function PageHeading({ title, action }) {
  return (
    <div className="page-heading">
      <h1>{title}</h1>
      {action}
    </div>
  );
}
function Density({ compact, setCompact }) {
  return (
    <div className="density-control">
      <Button
        size="small"
        type={compact ? "text" : "default"}
        aria-pressed={!compact}
        onClick={() => setCompact(false)}
      >
        舒适
      </Button>
      <Button
        size="small"
        type={compact ? "default" : "text"}
        aria-pressed={compact}
        onClick={() => setCompact(true)}
      >
        紧凑
      </Button>
    </div>
  );
}
function Experiment({
  runs,
  selected,
  setSelected,
  refresh,
  open,
  onCreate,
  onOpenRun,
}) {
  const [tab, setTab] = useState("overview");
  const run = runs?.items.find((r) => r.id === selected);
  return (
    <>
      <PageHeading
        title="实验"
        action={
          <Button type="primary" onClick={onCreate}>
            创建实验
          </Button>
        }
      />
      <div className="run-picker">
        <div className="run-select" aria-label="选择实验">
          <Select
            aria-label="选择实验"
            value={selected}
            onChange={setSelected}
            options={
              runs?.items.map((r) => ({ key: r.id, label: r.name })) || []
            }
          />
        </div>
        <span>{runs?.items.length || 0} 个实验</span>
      </div>
      {!run ? (
        <div className="empty">暂无运行</div>
      ) : (
        <>
          <Card className="experiment-banner">
            <div className="experiment-mark">{glyph(FlaskConical, 30)}</div>
            <div className="grow">
              <div className="inline">
                <h2>{run.name}</h2>
                <Badge
                  tone={run.status === "stale" ? "app-orange" : "app-teal"}
                >
                  {statusNames[run.status]}
                </Badge>
                <Hint
                  long
                  label="运行状态说明"
                  title={
                    run.status === "stale"
                      ? `日志已 ${Math.floor((run.log_age_seconds || 0) / 60)} 分钟未更新。此状态不判断进程存活或失败。`
                      : run.state_note || "状态不可用"
                  }
                />
              </div>
              <p>
                {run.config?.start_date || "—"} — {run.config?.end_date || "—"}{" "}
                · {n(run.users)} Agents
              </p>
            </div>
            <div className="inline">
              <Button
                type="link"
                onClick={() =>
                  open({
                    title: "实验配置",
                    content: (
                      <Definition values={Object.entries(run.config || {})} />
                    ),
                  })
                }
              >
                配置 {glyph(ArrowUpRight, 16)}
              </Button>
              <Button
                type="primary"
                size="small"
                onClick={() => onOpenRun(run.id)}
              >
                打开运行台
              </Button>
            </div>
          </Card>
          <Tabs
            panelId="experiment-content"
            value={tab}
            onChange={setTab}
            items={[
              ["overview", "运行总览"],
              ["agents", "Agent 快照"],
              ["market", "行情与结果"],
              ["logs", "过程记录"],
            ]}
          />
          <div
            id="experiment-content"
            role="tabpanel"
            aria-labelledby={`experiment-content-${tab}`}
          >
            {tab === "overview" && (
              <>
                <div className="metrics">
                  <Metric
                    label="参与 Agent"
                    value={run.users}
                    foot="运行数据库中的独立成员数。"
                    icon={Users}
                  />
                  <Metric
                    label="本次模拟交易"
                    value={run.trades}
                    foot={`仅统计实验开始后的交易，另含 ${n(run.historical_trades)} 条初始化历史记录。`}
                    icon={ChartNoAxesCombined}
                  />
                  <Metric
                    label="论坛帖子"
                    value={run.posts}
                    foot={`论坛数据库中的帖子；另有 ${n(run.reactions)} 条互动记录。`}
                    icon={Layers}
                  />
                  <Metric
                    label="当前日对话"
                    value={run.conversations_today}
                    foot={`日志模拟日 ${run.current_date || "未知"} 目录下的对话文件数。`}
                    icon={Radio}
                  />
                </div>
                <div className="overview-grid">
                  <Panel
                    title="模拟日历"
                    subtitle={`最新快照：${run.snapshot_through || "未知"}。某日出现 Profiles 记录不等于所有成员或当天流程完成。`}
                    action={
                      <Badge>
                        {run.trading_days_done || 0} /{" "}
                        {run.trading_days_total || 0} 交易日
                      </Badge>
                    }
                  >
                    <div className="progress-heading">
                      <strong>{run.current_date || "—"}</strong>
                    </div>
                    <div className="calendar">
                      {run.days?.map((d) => (
                        <Tooltip
                          key={d.cal_date}
                          title={`${d.cal_date} · ${d.is_open === "open" ? "交易日" : "休市日"} · ${d.snapshotted ? "已有快照" : "无快照"}`}
                          bordered
                          placement="top"
                        >
                          <div
                            className={`day ${d.snapshotted ? "done" : ""} ${d.cal_date === run.current_date ? "today" : ""} ${d.is_open !== "open" ? "closed" : ""}`}
                          >
                            <span>{d.cal_date.slice(5)}</span>
                            {d.snapshotted ? (
                              glyph("Check", 13)
                            ) : (
                              <span className="day-mark">
                                {d.is_open === "open" ? "·" : "–"}
                              </span>
                            )}
                          </div>
                        </Tooltip>
                      ))}
                    </div>
                    <div className="legend">
                      <span>
                        <i />
                        已有快照
                      </span>
                      <span>
                        <i className="outline" />
                        当前日
                      </span>
                      <span>– 休市</span>
                    </div>
                  </Panel>
                  <Panel
                    title="实验资源"
                    subtitle="旧运行未记录资源版本。这里展示运行数据与当前内置实现的映射，不推断历史版本。"
                  >
                    <Definition
                      values={[
                        ["Agent Group", `${n(run.users)} 位`],
                        ["市场机制", "内置撮合 · 版本未记录"],
                        ["资产包", `${n(run.asset_count)} 个行业指数`],
                        ["运行标识", run.id],
                      ]}
                    />
                  </Panel>
                </div>
                <MarketChart key={selected} run={selected} refresh={refresh} />
              </>
            )}
            {tab === "agents" && (
              <Agents
                key={selected}
                run={selected}
                refresh={refresh}
                open={open}
              />
            )}
            {tab === "market" && (
              <>
                <MarketChart key={selected} run={selected} refresh={refresh} />
                <Panel
                  title="结果产物"
                  subtitle="文件数量，不代表实验已经完成。"
                >
                  <Definition
                    values={Object.entries(run.artifacts || {}).map(
                      ([key, value]) => [key, n(value)],
                    )}
                  />
                </Panel>
              </>
            )}
            {tab === "logs" && (
              <Panel
                title="过程记录"
                subtitle="只展示运行事件，不展示原始模型响应或凭据。"
              >
                <div className="log-list">
                  {run.logs?.length ? (
                    run.logs.map((line, i) => (
                      <div key={i}>
                        <span>{String(i + 1).padStart(2, "0")}</span>
                        <span>{line}</span>
                      </div>
                    ))
                  ) : (
                    <div className="empty">暂无事件</div>
                  )}
                </div>
              </Panel>
            )}
          </div>
        </>
      )}
    </>
  );
}
function AgentSpace({ catalog, open }) {
  const g = catalog.group;
  return (
    <>
      <PageHeading
        title="Agent 群体"
        action={<PlannedButton primary>创建群体</PlannedButton>}
      />
      <Panel
        title={g.name}
        subtitle={`来源：${g.source}。本地模板，尚未注册独立群体版本。`}
        action={<Badge>本地模板</Badge>}
      >
        <div className="group-summary">
          <div className="group-number">
            {n(g.users)}
            <span>位投资者</span>
          </div>
          <div className="distribution">
            {g.distributions.map((d) => (
              <div key={d.name}>
                <span>{d.name}</span>
                <strong>{n(d.value)}</strong>
              </div>
            ))}
          </div>
          <PlannedButton>行为金融测试</PlannedButton>
        </div>
      </Panel>
      <Agents open={open} />
    </>
  );
}
function MarketSpace({ catalog }) {
  const [tab, setTab] = useState("environment"),
    state = useData("/api/runs/template/market");
  return (
    <>
      <PageHeading
        title="市场"
        action={<PlannedButton primary>创建环境</PlannedButton>}
      />
      <Tabs
        panelId="market-content"
        items={[
          ["environment", "模拟环境"],
          ["mechanisms", "交易机制"],
          ["assets", "资产组合包"],
          ["data", "数据工作台"],
        ]}
        value={tab}
        onChange={setTab}
      />
      <div
        id="market-content"
        role="tabpanel"
        aria-labelledby={`market-content-${tab}`}
      >
        {tab === "environment" && (
          <>
            <Panel
              title="行业指数市场"
              subtitle="本地初始化数据库中的环境，尚未注册独立版本。"
              action={<Badge>本地模板</Badge>}
            >
              <div className="environment-grid">
                <Metric
                  label="可交易资产"
                  value={state.data?.assets.length}
                  foot="10 个行业指数，并非个股。"
                  icon={ChartNoAxesCombined}
                />
                <Metric
                  label="历史行情记录"
                  value={catalog.market_range.records}
                  foot={`${catalog.market_range.start} — ${catalog.market_range.end}`}
                  icon={Database}
                />
                <Definition
                  values={[
                    ["机制", "日级最大成交量撮合"],
                    ["数据起始", catalog.market_range.start],
                    ["数据截至", catalog.market_range.end],
                  ]}
                />
              </div>
            </Panel>
            <MarketChart />
          </>
        )}
        {tab === "mechanisms" && (
          <Panel
            title="内置撮合机制"
            subtitle="对应当前 matching_engine.py；旧运行未记录独立机制版本。"
          >
            <Definition
              values={[
                ["订单优先级", "价格优先、时间优先"],
                ["价格形成", "日级最大成交量撮合"],
                ["实现", "trader/matching_engine.py"],
                ["交易日历", "data/trading_days.csv"],
              ]}
            />
          </Panel>
        )}
        {tab === "assets" && (
          <Panel
            title="行业指数包"
            subtitle="权重为模板原值，不等于成员的实际持仓。"
          >
            {state.data ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>代码</th>
                      <th>名称</th>
                      <th>行业</th>
                      <th className="number">权重</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.data.assets.map((a) => (
                      <tr key={a.stock_id}>
                        <td>{a.stock_id}</td>
                        <td>{a.name}</td>
                        <td>{a.industry}</td>
                        <td className="number">{n(a.weight)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty state={state} />
            )}
          </Panel>
        )}
        {tab === "data" && (
          <Panel
            title="数据集"
            subtitle="只检查本地文件；存在不代表数据完整或索引可用。数据源凭据在 Setting 管理。"
            action={<PlannedButton>更新数据</PlannedButton>}
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>数据集</th>
                    <th>来源</th>
                    <th>大小</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {catalog.inventory.map((d) => (
                    <tr key={d.path}>
                      <td>{d.name}</td>
                      <td>{d.path}</td>
                      <td>
                        {d.bytes == null
                          ? "—"
                          : `${n(d.bytes / 1024 / 1024)} MB`}
                      </td>
                      <td>
                        <Badge tone={d.available ? "app-teal" : "app-orange"}>
                          {d.available ? "存在" : "缺失"}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </div>
    </>
  );
}
function SettingSpace({ catalog, compact, setCompact }) {
  return (
    <>
      <PageHeading title="设置" />
      <div className="settings-grid">
        <nav className="settings-nav">
          <a href="#models">模型连接</a>
          <a href="#sources">金融数据源</a>
          <a href="#preferences">界面偏好</a>
        </nav>
        <div>
          <section id="models">
            <Panel
              title="模型连接"
              subtitle="仅读取名称与配置文件存在性，不返回密钥。未测试不代表在线。"
            >
              {catalog.connections.map((c) => (
                <div className="connection" key={c.kind}>
                  <div className="connection-icon">
                    {glyph(c.kind === "language" ? Layers : Database, 24)}
                  </div>
                  <div className="grow">
                    <h3>{c.name}</h3>
                    <p>{c.model || "未识别"}</p>
                  </div>
                  <Badge tone="app-orange">
                    {c.configured ? "未测试" : "未配置"}
                  </Badge>
                  <PlannedButton>配置</PlannedButton>
                </div>
              ))}
            </Panel>
          </section>
          <section id="sources">
            <Panel
              title="金融数据源"
              subtitle="连接访问归 Setting；拉取、更新数据归 Market。"
            >
              <div className="connection">
                <span className="grow">暂无连接</span>
                <PlannedButton>添加数据源</PlannedButton>
              </div>
            </Panel>
          </section>
          <section id="preferences">
            <Panel
              title="界面偏好"
              subtitle="只保存到当前浏览器，不修改实验或系统配置。"
            >
              <div className="connection">
                <h3 className="grow">信息密度</h3>
                <Density compact={compact} setCompact={setCompact} />
              </div>
            </Panel>
          </section>
        </div>
      </div>
    </>
  );
}
export function App() {
  // URL 是导航的唯一来源；runRoute 识别运行台及其 live/results 子路由。
  const route = () =>
    spaces.some((s) => s.id === location.pathname.split("/")[2])
      ? location.pathname.split("/")[2]
      : "Experiment";
  const runRoute = (path) =>
    /^\/studio\/runs\/([^/]+)(?:\/(?:live|results))?\/?$/.exec(path)?.[1] ||
    null;
  const [space, setSpace] = useState(route),
    [viewPath, setViewPath] = useState(location.pathname),
    [compact, setCompactState] = useState(
      () => localStorage.getItem("twin-density") === "compact",
    );
  // live 控制实验列表的自动刷新；refresh 是所有数据源共享的手动刷新计数器。
  const [live, setLive] = useState(true),
    [refresh, setRefresh] = useState(0),
    [selected, setSelected] = useState(""),
    [drawer, setDrawer] = useState(null);
  // 实验空间开启时每 5 秒轮询，其他空间不启动无用的定时请求。
  const runs = useData(
      "/api/runs",
      refresh,
      live && space === "Experiment" ? 5000 : 0,
    ),
    catalog = useData("/api/catalog", refresh);
  // 后端 DTO 转为当前实验视图需要的形状；缺失字段保留安全的默认值。
  const runItems = runs.data
    ? {
        ...runs.data,
        items: runs.data.items.map((item) => ({
          ...item,
          id: item.run_id,
          users: item.config?.user_count,
          current_date: item.checkpoint?.next_date,
          days: [],
          artifacts: {},
        })),
      }
    : null;
  const currentRunId = runRoute(viewPath);
  // 首次取得运行列表后选择第一项；用户已选择时不覆盖其选择。
  useEffect(() => {
    if (!selected && runItems?.items.length) setSelected(runItems.items[0].id);
  }, [runItems, selected]);
  // 同步浏览器前进/后退，并将旧的 /studio 根地址重定向到实验空间。
  useEffect(() => {
    if (location.pathname === "/studio/" || location.pathname === "/studio") {
      history.replaceState({}, "", "/studio/Experiment");
      setViewPath("/studio/Experiment");
    }
    const pop = () => {
      setSpace(route());
      setViewPath(location.pathname);
    };
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  // 使用 History API 完成站内导航，同时保留修饰键打开新标签页的浏览器默认行为。
  const navigate = (e, id) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const path = `/studio/${id}`;
    history.pushState({}, "", path);
    setViewPath(path);
    setSpace(id);
    setDrawer(null);
    window.scrollTo(0, 0);
  };
  const openRun = (runId) => {
    const path = `/studio/runs/${encodeURIComponent(runId)}`;
    history.pushState({}, "", path);
    setViewPath(path);
    setSpace("Experiment");
    setDrawer(null);
    window.scrollTo(0, 0);
  };
  const setCompact = (v) => {
    setCompactState(v);
    localStorage.setItem("twin-density", v ? "compact" : "comfortable");
  };
  return (
    <div className={`app ${compact ? "compact" : ""}`}>
      <aside className="sidebar">
        <a
          className="brand"
          href="/studio/Experiment"
          onClick={(e) => navigate(e, "Experiment")}
        >
          {glyph(Leaf, 30)}
          <span>
            TwinMarket<small>RESEARCH STUDIO</small>
          </span>
        </a>
        <nav>
          {spaces.map((s) => (
            <a
              key={s.id}
              href={`/studio/${s.id}`}
              aria-current={space === s.id ? "page" : undefined}
              className={space === s.id ? "active" : ""}
              onClick={(e) => navigate(e, s.id)}
            >
              {glyph(s.icon, 23)}
              <span>
                {s.id}
                <small>{s.name}</small>
              </span>
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Badge tone="default">本地 · Runtime API</Badge>
        </div>
      </aside>
      <Background type="dots-dark-green" className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            {glyph(
              spaces.find((s) => s.id === space)?.icon || FlaskConical,
              18,
            )}
            <strong>{currentRunId ? "Runtime Observatory" : space}</strong>
          </div>
          <div className="toolbar">
            {space === "Experiment" && (
              <>
                <Button
                  size="small"
                  type="text"
                  aria-pressed={live}
                  onClick={() => setLive((v) => !v)}
                >
                  {glyph("Wifi", 16)}
                  {live ? "每 5 秒读取" : "已暂停"}
                </Button>
                <span className="update-time">
                  {time(runs.data?.observed_at)}
                </span>
              </>
            )}
            <Button
              size="small"
              type="text"
              aria-label="立即刷新"
              onClick={() => setRefresh((v) => v + 1)}
            >
              {glyph(RefreshCw, 18)}
            </Button>
            <Density compact={compact} setCompact={setCompact} />
          </div>
        </header>
        <main>
          {currentRunId ? (
            <LiveSimulationView
              runId={currentRunId}
              onBack={() =>
                navigate(
                  {
                    preventDefault() {},
                    metaKey: false,
                    ctrlKey: false,
                    shiftKey: false,
                    altKey: false,
                  },
                  "Experiment",
                )
              }
            />
          ) : (
            <>
              {space === "Experiment" && runs.error && (
                <div className="warning" role="status">
                  <span>连接中断 · 保留上次快照</span>
                  <Hint
                    long
                    title={`上次读取：${time(runs.data?.observed_at)}。可手动刷新重试；自动读取开启时会继续重试。`}
                  />
                </div>
              )}
              {space === "Experiment" &&
                (runs.data ? (
                  <Experiment
                    runs={runItems}
                    selected={selected}
                    setSelected={setSelected}
                    refresh={runs.data.observed_at}
                    open={setDrawer}
                    onCreate={() =>
                      setDrawer({
                        title: "新建运行实例",
                        content: <RunComposer onCreated={openRun} />,
                      })
                    }
                    onOpenRun={openRun}
                  />
                ) : (
                  <Empty state={runs} />
                ))}
              {["Agent", "Market", "Setting"].includes(space) &&
                !catalog.data && <Empty state={catalog} />}
              {space === "Agent" && catalog.data && (
                <AgentSpace catalog={catalog.data} open={setDrawer} />
              )}
              {space === "Market" && catalog.data && (
                <MarketSpace catalog={catalog.data} />
              )}
              {space === "Setting" && catalog.data && (
                <SettingSpace
                  catalog={catalog.data}
                  compact={compact}
                  setCompact={setCompact}
                />
              )}
              {space === "Documentation" && <Documentation refresh={refresh} />}
            </>
          )}
        </main>
      </Background>
      <Inspector drawer={drawer} close={() => setDrawer(null)} />
    </div>
  );
}
