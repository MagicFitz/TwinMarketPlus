import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, BarChart3, Bug, Crosshair, Play, Radio, RotateCcw, Square } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { PageSkeleton, ErrorState, StateView } from "@/components/state-view";
import { StatusBadge, statusLabel } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle, DrawerTrigger } from "@/components/ui/drawer";
import { useToast } from "@/components/ui/toast";
import { useResource } from "@/hooks/use-resource";
import { useRunEvents } from "@/hooks/use-run-events";
import { api } from "@/lib/api";
import type { AgentSnapshot, RuntimeEvent, StageSnapshot, WorkerSnapshot } from "@/lib/api-types";
import { cn, formatDate, formatNumber } from "@/lib/utils";

const DAY_STAGES = [["prepare", "Prepare"], ["agents", "Agents"], ["market", "Market"], ["social", "Social"], ["commit", "Commit"]] as const;
const AGENT_STAGES = [["state", "State"], ["perception", "Perception"], ["interpretation", "Interpretation"], ["decision", "Decision"], ["action", "Action"], ["commit", "Commit"]] as const;

export function RuntimePage() {
  const { runId = "" } = useParams(); const toast = useToast();
  const runState = useResource((signal) => api.runs.get(runId, signal), [runId], 3000);
  const runtimeState = useResource((signal) => api.runs.runtime(runId, signal), [runId], 2000);
  const stream = useRunEvents(runId, runtimeState.data?.last_event_id || 0);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [autoFollow, setAutoFollow] = useState(true);
  useEffect(() => { const latest = stream.events[0]; if (latest) { runtimeState.reload(); if (autoFollow && latest.agent_id) setFocusId(latest.agent_id); } }, [stream.events[0]?.event_id]);
  const focusAgent = useMemo(() => runtimeState.data?.agents.find((agent) => agent.agent_id === focusId) || runtimeState.data?.agents.slice().sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")))[0], [runtimeState.data?.agents, focusId]);
  const action = async (name: "start" | "stop" | "resume") => { try { await api.runs.action(runId, name); toast({ title: "运行请求已接受", description: name === "stop" ? "Worker 正在安全停止。" : "Runtime 将自动刷新。", tone: "success" }); runState.reload(); runtimeState.reload(); } catch (reason) { toast({ title: "运行操作失败", description: reason instanceof Error ? reason.message : "未知错误", tone: "error" }); } };
  if ((runState.loading && !runState.data) || (runtimeState.loading && !runtimeState.data)) return <PageSkeleton />;
  if (!runState.data || !runtimeState.data) return <ErrorState message={runState.error?.message || runtimeState.error?.message || "Runtime 不可用"} retry={() => { runState.reload(); runtimeState.reload(); }} />;
  const run = runState.data; const snapshot = runtimeState.data;
  return <section className="grid gap-4">
    <div className="flex flex-col gap-4 rounded-lg border bg-card p-5 shadow-soft lg:flex-row lg:items-start lg:justify-between"><div><Button variant="ghost" size="sm" asChild className="-ml-3 mb-2"><Link to={`/runs/${runId}`}><ArrowLeft className="h-4 w-4" />实例详情</Link></Button><div className="flex flex-wrap items-center gap-2"><h1 className="text-2xl font-bold">{run.name}</h1><StatusBadge value={run.status} /><StatusBadge value={run.health} /></div><p className="mt-2 font-mono text-xs text-muted-foreground">{runId} · 模拟日期 {snapshot.day.date || "尚未开始"}</p></div><div className="flex flex-wrap items-center gap-2"><StatusBadge value={stream.connection} />{run.status === "draft" && <Button onClick={() => action("start")}><Play className="h-4 w-4" />启动</Button>}{["failed", "cancelled"].includes(run.status) && <Button onClick={() => action("resume")}><RotateCcw className="h-4 w-4" />续跑</Button>}{["queued", "running", "stopping"].includes(run.status) && <Button variant="destructive" onClick={() => action("stop")}><Square className="h-4 w-4" />停止</Button>}<Button variant="outline" asChild><Link to={`/runs/${runId}/results`}><BarChart3 className="h-4 w-4" />结果</Link></Button><Diagnostics run={run} diagnostics={snapshot.diagnostics} /></div></div>
    {(runState.error || runtimeState.error) && <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm" role="alert">实时刷新暂时失败，界面保留上一份快照：{runState.error?.message || runtimeState.error?.message}</div>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Run" value={statusLabel(run.status)} detail={`健康状态：${statusLabel(run.health)}`} /><Metric label="Day" value={snapshot.day.date || "等待事件"} detail={`Checkpoint: ${run.checkpoint.next_date || "—"}`} /><Metric label="Agents" value={`${snapshot.agents.length} 已观察`} detail={`${snapshot.agent_counts.completed || 0} 已完成`} /><Metric label="Event cursor" value={`#${Math.max(snapshot.last_event_id, stream.cursor)}`} detail={formatDate(run.last_heartbeat)} /></div>
    <DayCycle day={snapshot.day} />
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,.65fr)]"><FocusAgent agent={focusAgent} /><WorkerLanes workers={snapshot.workers} focusId={focusAgent?.agent_id} autoFollow={autoFollow} setAutoFollow={setAutoFollow} setFocus={setFocusId} /></div>
    <div className="grid gap-4 xl:grid-cols-2"><TodaySummary values={snapshot.today_summary} /><RecentEvents events={stream.events} setFocus={setFocusId} /></div>
  </section>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) { return <Card className="p-4"><span className="text-xs font-medium text-muted-foreground">{label}</span><strong className="mt-1 block text-lg">{value}</strong><span className="mt-1 block truncate text-xs text-muted-foreground">{detail}</span></Card>; }

function DayCycle({ day }: { day: { date: string | null; stages: Record<string, StageSnapshot> } }) {
  return <Card><CardHeader className="flex-row items-center justify-between"><CardTitle>Day Cycle</CardTitle><span className="text-sm text-muted-foreground">{day.date || "尚未开始"}</span></CardHeader><CardContent><div className="grid gap-2 overflow-x-auto pb-1 sm:grid-cols-5">{DAY_STAGES.map(([key, label], index) => <StageCard key={key} number={index + 1} label={label} stage={day.stages?.[key]} />)}</div></CardContent></Card>;
}

function StageCard({ number, label, stage = { status: "pending" } }: { number: number; label: string; stage?: StageSnapshot }) {
  return <article className={cn("min-w-36 rounded-md border p-3", stage.status === "running" && "border-amber-500/50 bg-amber-500/5", stage.status === "completed" && "border-emerald-500/40", stage.status === "failed" && "border-destructive/40")} aria-label={`${label}: ${statusLabel(stage.status)}`}><div className="mb-3 flex items-center justify-between"><span className="grid h-6 w-6 place-items-center rounded-full bg-muted font-mono text-[11px]">{number}</span><StatusBadge value={stage.status} /></div><strong className="text-sm">{label}</strong><p className="mt-1 line-clamp-2 min-h-8 text-xs text-muted-foreground">{stage.substage || stage.message || "等待 RuntimeEvent"}</p></article>;
}

function FocusAgent({ agent }: { agent?: AgentSnapshot }) {
  return <Card><CardHeader className="flex-row items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-wider text-primary">Focus Agent</p><CardTitle className="mt-1 font-mono">{agent?.agent_id || "等待 Agent"}</CardTitle></div>{agent && <StatusBadge value={agent.stages.commit?.status || "pending"} />}</CardHeader><CardContent>{!agent ? <StateView title="等待 Agent RuntimeEvent" description="运行进入 Agents 阶段后，这里会显示六阶段流水线。" /> : <div className="grid gap-2">{AGENT_STAGES.map(([key, label], index) => { const stage = agent.stages[key] || { status: "pending" }; return <article key={key} className={cn("grid gap-3 rounded-md border p-3 sm:grid-cols-[36px_1fr_auto] sm:items-center", stage.status === "running" && "border-amber-500/50 bg-amber-500/5")}><span className="grid h-8 w-8 place-items-center rounded-full bg-muted font-mono text-xs">{index + 1}</span><div><div className="flex items-center gap-2"><strong className="text-sm">{label}</strong><StatusBadge value={stage.status} /></div><p className="mt-1 text-xs text-muted-foreground">{stage.substage || stage.message || stageHint(key)}</p></div><span className="text-right font-mono text-xs text-muted-foreground">{stage.duration_ms == null ? "—" : `${formatNumber(stage.duration_ms / 1000, 1)}s`}<br />attempt {stage.attempt || 1}</span></article>; })}</div>}</CardContent></Card>;
}

function stageHint(key: string) { return ({ state: "读取 Agent 当前状态", perception: "构造可见信息", interpretation: "生成脱敏信号摘要", decision: "形成认知意图", action: "转换为可执行动作", commit: "写入模拟世界事实" } as Record<string, string>)[key] || "等待"; }

function eventStatus(event: RuntimeEvent["event"]) {
  return ({ stage_started: "running", stage_completed: "completed", stage_skipped: "skipped", stage_failed: "failed", stage_retrying: "retrying" } as const)[event];
}

function WorkerLanes({ workers, focusId, autoFollow, setAutoFollow, setFocus }: { workers: WorkerSnapshot[]; focusId?: string; autoFollow: boolean; setAutoFollow: (value: boolean) => void; setFocus: (id: string) => void }) {
  return <Card><CardHeader className="flex-row items-center justify-between"><div><CardTitle>Worker Lanes</CardTitle><p className="mt-1 text-xs text-muted-foreground">点击 Worker 固定 Focus Agent</p></div><Button size="sm" variant={autoFollow ? "secondary" : "outline"} onClick={() => setAutoFollow(!autoFollow)}><Crosshair className="h-3.5 w-3.5" />Auto {autoFollow ? "on" : "off"}</Button></CardHeader><CardContent className="grid gap-2">{workers.length ? workers.map((worker) => <button key={worker.worker_id} className={cn("grid grid-cols-[1fr_auto] gap-1 rounded-md border p-3 text-left transition hover:bg-muted", worker.agent_id === focusId && "border-primary bg-primary/5")} onClick={() => { setFocus(worker.agent_id); setAutoFollow(false); }}><strong className="text-sm">{worker.worker_id}</strong><StatusBadge value={worker.status} /><span className="text-xs text-muted-foreground">{worker.agent_id} · {worker.stage}</span></button>) : <StateView title="没有活跃 Worker" description="单 Worker 模式会在开始处理 Agent 后显示当前任务。" />}</CardContent></Card>;
}

function TodaySummary({ values }: { values: Record<string, number> }) { return <Card><CardHeader><CardTitle>Today Summary</CardTitle></CardHeader><CardContent><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{Object.entries(values).map(([key, value]) => <div key={key} className="rounded-md bg-muted/60 p-3"><strong className="block text-xl">{formatNumber(value, 0)}</strong><span className="text-xs capitalize text-muted-foreground">{key}</span></div>)}</div></CardContent></Card>; }

function RecentEvents({ events, setFocus }: { events: RuntimeEvent[]; setFocus: (id: string) => void }) { return <Card><CardHeader className="flex-row items-center justify-between"><CardTitle>Recent Events</CardTitle><Radio className="h-4 w-4 text-primary" /></CardHeader><CardContent className="max-h-80 space-y-2 overflow-y-auto">{events.length ? events.map((event) => <button key={event.event_id} className="grid w-full grid-cols-[1fr_auto] gap-1 rounded-md border p-3 text-left hover:bg-muted" onClick={() => event.agent_id && setFocus(event.agent_id)}><span className="font-mono text-[11px] text-muted-foreground">#{event.event_id} · {event.scope}/{event.stage}</span><StatusBadge value={eventStatus(event.event)} /><strong className="truncate text-xs font-medium">{event.message || event.substage || "Runtime event"}</strong></button>) : <p className="py-8 text-center text-sm text-muted-foreground">新事件会通过 SSE 出现在这里。</p>}</CardContent></Card>; }

function Diagnostics({ run, diagnostics }: { run: { pid: number | null; exit_code: number | null; failure_reason: string | null; last_heartbeat: string | null }; diagnostics: RuntimeEvent[] }) { return <Drawer><DrawerTrigger asChild><Button variant="outline"><Bug className="h-4 w-4" />Diagnostics</Button></DrawerTrigger><DrawerContent><DrawerHeader><DrawerTitle>Runtime Diagnostics</DrawerTitle><DrawerDescription>失败、重试及超过 30 秒的事件；不展示原始 prompt 或凭据。</DrawerDescription></DrawerHeader><div className="grid grid-cols-2 gap-3"><Metric label="PID" value={String(run.pid ?? "—")} detail={`heartbeat ${formatDate(run.last_heartbeat)}`} /><Metric label="Exit code" value={String(run.exit_code ?? "—")} detail={run.failure_reason || "没有运行级错误"} /></div><div className="mt-6 grid gap-2">{diagnostics.length ? diagnostics.slice().reverse().map((event) => <article key={event.event_id} className="rounded-md border p-3"><div className="flex items-center justify-between gap-2"><strong className="font-mono text-xs">#{event.event_id} {event.scope}/{event.stage}</strong><StatusBadge value={eventStatus(event.event)} /></div><p className="mt-2 text-sm text-muted-foreground">{event.message || event.error_code || "slow/retry event"}</p></article>) : <StateView title="没有诊断事件" description="当前没有失败、重试或慢阶段记录。" />}</div></DrawerContent></Drawer>; }
