import { Activity, ArrowRight, CalendarDays, Plus, Users } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ErrorState, PageSkeleton, StateView } from "@/components/state-view";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { FormSelect } from "@/components/ui/form";
import { api } from "@/lib/api";
import type { RunStatus } from "@/lib/api-types";
import { formatDate } from "@/lib/utils";
import { useResource } from "@/hooks/use-resource";

const filters: Array<[string, string]> = [["", "全部状态"], ["draft", "草稿"], ["queued", "排队中"], ["running", "运行中"], ["completed", "已完成"], ["failed", "失败"], ["cancelled", "已取消"]];

export function RunsPage() {
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") || undefined) as RunStatus | undefined;
  const state = useResource((signal) => api.runs.list({ status, signal }), [status], 5000);
  if (state.loading) return <PageSkeleton />;
  if (state.error && !state.data) return <ErrorState message={state.error.message} retry={state.reload} />;
  const runs = state.data?.items || [];
  const active = runs.filter((run) => ["queued", "running", "stopping"].includes(run.status)).length;
  return <>
    <PageHeader eyebrow="Experiment" title="运行实例" description="从一个可复现的草稿出发，启动仿真、实时观察每个阶段，再查看真实产物。" actions={<><FormSelect aria-label="状态筛选" value={status || ""} onChange={(event) => setParams(event.target.value ? { status: event.target.value } : {})}>{filters.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</FormSelect><Button asChild><Link to="/runs/new"><Plus className="h-4 w-4" />创建实例</Link></Button></>} />
    <div className="mb-6 grid gap-3 sm:grid-cols-3">
      <Metric label="当前结果" value={state.data?.total || 0} note="筛选后的实例数" icon={<Activity />} />
      <Metric label="活动实例" value={active} note="queued / running / stopping" icon={<ArrowRight />} />
      <Metric label="自动刷新" value={state.refreshing ? "同步中" : "5 秒"} note="刷新不会影响后台任务" icon={<CalendarDays />} />
    </div>
    {state.error && <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive" role="alert">刷新失败：{state.error.message}，当前保留上一份数据。</div>}
    {!runs.length ? <StateView title="还没有运行实例" description="创建一个 10 Agent、2 交易日的实例即可开始完整闭环。" action={<Button asChild><Link to="/runs/new"><Plus className="h-4 w-4" />创建首个实例</Link></Button>} /> : <div className="grid gap-4 lg:grid-cols-2">{runs.map((run) => <Card key={run.run_id} className="group transition hover:-translate-y-0.5 hover:shadow-lift"><CardHeader className="flex-row items-start justify-between gap-4"><div className="min-w-0"><p className="truncate font-semibold">{run.name}</p><p className="mt-1 truncate font-mono text-xs text-muted-foreground">{run.run_id}</p></div><div className="flex flex-wrap justify-end gap-1.5"><StatusBadge value={run.status} /><StatusBadge value={run.health} /></div></CardHeader><CardContent><p className="mb-5 line-clamp-2 min-h-10 text-sm text-muted-foreground">{run.description || "没有实例说明。"}</p><div className="grid grid-cols-2 gap-3 rounded-md bg-muted/55 p-3 text-xs sm:grid-cols-3"><span><Users className="mr-1 inline h-3.5 w-3.5" />{run.config.user_count} Agents</span><span>{run.config.start_date} → {run.config.end_date}</span><span className="col-span-2 text-muted-foreground sm:col-span-1">{formatDate(run.created_at)}</span></div><Button asChild variant="ghost" className="mt-3 w-full justify-between"><Link to={`/runs/${encodeURIComponent(run.run_id)}`}>打开实例<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></Link></Button></CardContent></Card>)}</div>}
  </>;
}

function Metric({ label, value, note, icon }: { label: string; value: string | number; note: string; icon: React.ReactNode }) {
  return <Card className="p-4"><div className="flex items-start justify-between"><div><p className="text-xs font-medium text-muted-foreground">{label}</p><strong className="mt-1 block text-2xl">{value}</strong><p className="mt-1 text-xs text-muted-foreground">{note}</p></div><span className="grid h-9 w-9 place-items-center rounded-md bg-primary/10 text-primary [&>svg]:h-4 [&>svg]:w-4">{icon}</span></div></Card>;
}
