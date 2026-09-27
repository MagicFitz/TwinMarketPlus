import { ArrowLeft, Download, RefreshCw } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ErrorState, PageSkeleton, StateView } from "@/components/state-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import { apiUrl } from "@/lib/runtime-config";
import { displayValue, formatDate } from "@/lib/utils";

type ResultKind = "summary" | "trades" | "agents";
const tabs: Array<[ResultKind, string]> = [["summary", "每日汇总"], ["trades", "成交明细"], ["agents", "Agent 结果"]];

export function ResultsPage() {
  const { runId = "" } = useParams(); const [params, setParams] = useSearchParams();
  const kind = (tabs.some(([id]) => id === params.get("view")) ? params.get("view") : "summary") as ResultKind;
  const state = useResource((signal) => api.runs.results(runId, kind, 1, signal), [runId, kind]);
  const rows = state.data?.items || []; const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 10);
  return <>
    <PageHeader eyebrow="Run results" title="结果数据表" description={`Run ID: ${runId} · 仅展示后端读取到的真实运行产物。`} actions={<Button variant="outline" asChild><Link to={`/runs/${runId}/live`}><ArrowLeft className="h-4 w-4" />返回 Observatory</Link></Button>} />
    <Card><CardHeader className="flex-row flex-wrap items-center justify-between gap-3"><Tabs value={kind} onValueChange={(value) => setParams({ view: value })}><TabsList>{tabs.map(([id, label]) => <TabsTrigger key={id} value={id}>{label}</TabsTrigger>)}</TabsList></Tabs><div className="flex items-center gap-2">{kind === "trades" && <><Button variant="outline" size="sm" asChild><a href={apiUrl(`/runs/${encodeURIComponent(runId)}/results/trades/export?format=csv`)}><Download className="h-3.5 w-3.5" />CSV</a></Button><Button variant="outline" size="sm" asChild><a href={apiUrl(`/runs/${encodeURIComponent(runId)}/results/trades/export?format=json`)}><Download className="h-3.5 w-3.5" />JSON</a></Button></>}<Button size="sm" variant="ghost" onClick={state.reload}><RefreshCw className={state.refreshing ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />刷新</Button></div></CardHeader><CardContent>
      {state.loading ? <PageSkeleton /> : state.error && !state.data ? <ErrorState message={state.error.message} retry={state.reload} /> : !rows.length ? <StateView title="暂无结果产物" description="运行完成相应阶段后，这个视图才会出现真实数据；空状态不会伪造示例行。" /> : <><div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground"><span>来源：{state.data?.source || "simulation artifacts"}</span><span>记录：{state.data?.total ?? rows.length}</span><span>读取：{formatDate(state.data?.updated_at || new Date().toISOString())}</span></div><Table><TableHeader><TableRow>{columns.map((column) => <TableHead key={column}>{column}</TableHead>)}</TableRow></TableHeader><TableBody>{rows.map((row, index) => <TableRow key={index}>{columns.map((column) => <TableCell key={column} className="max-w-64 truncate font-mono text-xs" title={displayValue(row[column])}>{displayValue(row[column])}</TableCell>)}</TableRow>)}</TableBody></Table></>}
    </CardContent></Card>
  </>;
}
