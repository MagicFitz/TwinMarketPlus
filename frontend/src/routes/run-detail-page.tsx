import { Activity, ArrowLeft, BarChart3, CalendarRange, Copy, Play, RotateCcw, Square, Users } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ErrorState, PageSkeleton } from "@/components/state-view";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export function RunDetailPage() {
  const { runId = "" } = useParams(); const navigate = useNavigate(); const toast = useToast();
  const state = useResource((signal) => api.runs.get(runId, signal), [runId], 4000);
  if (state.loading) return <PageSkeleton />;
  if (!state.data) return <ErrorState message={state.error?.message || "找不到实例"} retry={state.reload} />;
  const run = state.data;
  const action = async (name: "start" | "stop" | "resume" | "copy") => {
    try { const changed = await api.runs.action(runId, name); toast({ title: name === "copy" ? "已创建副本" : "请求已接受", description: name === "start" ? "Worker 正在排队启动。" : undefined, tone: "success" }); if (name === "copy") navigate(`/runs/${changed.run_id}`); else { state.reload(); if (name === "start" || name === "resume") navigate(`/runs/${runId}/live`); } } catch (reason) { toast({ title: "操作失败", description: reason instanceof Error ? reason.message : "未知错误", tone: "error" }); }
  };
  const canStart = run.status === "draft"; const canResume = run.status === "failed" || run.status === "cancelled"; const canStop = ["queued", "running", "stopping"].includes(run.status);
  return <>
    <PageHeader eyebrow="Run detail" title={run.name} description={run.description || `Run ID: ${run.run_id}`} actions={<><StatusBadge value={run.status} /><StatusBadge value={run.health} />{canStart && <Button onClick={() => action("start")}><Play className="h-4 w-4" />启动</Button>}{canResume && <Button onClick={() => action("resume")}><RotateCcw className="h-4 w-4" />续跑</Button>}{canStop && <Button variant="destructive" onClick={() => action("stop")}><Square className="h-4 w-4" />停止</Button>}</>} />
    {state.error && <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{state.error.message}</div>}
    <div className="mb-5 flex flex-wrap gap-2"><Button variant="outline" asChild><Link to="/runs"><ArrowLeft className="h-4 w-4" />实例列表</Link></Button><Button variant="outline" asChild><Link to={`/runs/${runId}/live`}><Activity className="h-4 w-4" />Runtime Observatory</Link></Button><Button variant="outline" asChild><Link to={`/runs/${runId}/results`}><BarChart3 className="h-4 w-4" />查看结果</Link></Button><Button variant="ghost" onClick={() => action("copy")}><Copy className="h-4 w-4" />复制配置</Button></div>
    <div className="grid gap-4 lg:grid-cols-3"><Card className="lg:col-span-2"><CardHeader><CardTitle>运行配置</CardTitle></CardHeader><CardContent className="grid gap-3 sm:grid-cols-2"><Fact icon={<Users />} label="Agent 数量" value={run.config.user_count} /><Fact icon={<CalendarRange />} label="交易区间" value={`${run.config.start_date} → ${run.config.end_date}`} /><Fact label="并发 Worker" value={run.config.max_workers} /><Fact label="激活 / 技术面概率" value={`${run.config.activate_prob} / ${run.config.prob_of_technical}`} /><Fact label="随机种子" value={run.config.random_seed} /><Fact label="模型配置" value={run.config.config_path || "后端默认"} /></CardContent></Card><Card><CardHeader><CardTitle>生命周期</CardTitle></CardHeader><CardContent className="grid gap-3"><Fact label="创建" value={formatDate(run.created_at)} /><Fact label="开始" value={formatDate(run.started_at)} /><Fact label="结束" value={formatDate(run.ended_at)} /><Fact label="Checkpoint" value={run.checkpoint.next_date || "—"} /><Fact label="最后事件" value={`#${run.last_event_id}`} /><Fact label="PID / exit" value={`${run.pid ?? "—"} / ${run.exit_code ?? "—"}`} /></CardContent></Card></div>
    {run.failure_reason && <Card className="mt-4 border-destructive/30"><CardHeader><CardTitle className="text-destructive">失败原因</CardTitle></CardHeader><CardContent className="text-sm">{run.failure_reason}</CardContent></Card>}
  </>;
}

function Fact({ icon, label, value }: { icon?: React.ReactNode; label: string; value: React.ReactNode }) { return <div className="rounded-md border bg-muted/20 p-3"><span className="flex items-center gap-1.5 text-xs text-muted-foreground">{icon && <span className="[&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>}{label}</span><strong className="mt-1.5 block break-all text-sm">{value}</strong></div>; }
