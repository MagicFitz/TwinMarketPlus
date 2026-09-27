import { useState } from "react";
import { Bot, Search } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ErrorState, PageSkeleton, StateView } from "@/components/state-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import type { AgentMember } from "@/lib/api-types";
import { displayValue, formatNumber } from "@/lib/utils";

export function AgentsPage() {
  const [params, setParams] = useSearchParams(); const runId = params.get("run") || "template"; const search = params.get("q") || "";
  const [draft, setDraft] = useState(search); const [selected, setSelected] = useState<AgentMember | null>(null);
  const state = useResource((signal) => api.runs.agents(runId, search, 1, signal), [runId, search]);
  return <>
    <PageHeader eyebrow="Read-only entry" title="Agent 群体" description="从模板或指定 Run 的只读数据库快照查看投资者画像；此入口不会修改仿真状态。" />
    <Card><CardContent className="pt-6"><form className="mb-5 flex flex-col gap-2 sm:flex-row" onSubmit={(event) => { event.preventDefault(); setParams({ ...(runId !== "template" ? { run: runId } : {}), ...(draft ? { q: draft } : {}) }); }}><Input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="搜索 Agent ID、类型或地区" aria-label="搜索 Agent" /><Input value={runId} onChange={(event) => setParams({ run: event.target.value || "template", ...(search ? { q: search } : {}) })} placeholder="Run ID 或 template" aria-label="Run ID" className="sm:max-w-64" /><Button type="submit"><Search className="h-4 w-4" />搜索</Button></form>{state.loading ? <PageSkeleton /> : state.error ? <ErrorState message={state.error.message} retry={state.reload} /> : !state.data?.items.length ? <StateView icon={<Bot className="h-8 w-8 text-muted-foreground" />} title="没有匹配的 Agent" description="更换搜索词，或确认 Run 已生成 Agent 数据库。" /> : <Table><TableHeader><TableRow><TableHead>Agent ID</TableHead><TableHead>类型</TableHead><TableHead>地区</TableHead><TableHead>现金</TableHead><TableHead>总资产</TableHead><TableHead>收益率</TableHead></TableRow></TableHeader><TableBody>{state.data.items.map((agent) => <TableRow key={agent.user_id} className="cursor-pointer" onClick={async () => { try { setSelected(await api.runs.agent(runId, agent.user_id)); } catch { setSelected(agent); } }}><TableCell className="font-mono">{agent.user_id}</TableCell><TableCell>{agent.user_type || "—"}</TableCell><TableCell>{agent.location || "—"}</TableCell><TableCell>{formatNumber(agent.current_cash)}</TableCell><TableCell>{formatNumber(agent.total_value)}</TableCell><TableCell>{formatNumber(agent.return_rate)}</TableCell></TableRow>)}</TableBody></Table>}</CardContent></Card>
    <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}><DialogContent><DialogHeader><DialogTitle>Agent {selected?.user_id}</DialogTitle><DialogDescription>最新只读快照，敏感模型输入不在此接口返回。</DialogDescription></DialogHeader><dl className="grid grid-cols-2 gap-3">{selected && Object.entries(selected).map(([key, value]) => <div key={key} className="rounded-md bg-muted/50 p-3"><dt className="text-xs text-muted-foreground">{key}</dt><dd className="mt-1 break-all text-sm">{displayValue(value)}</dd></div>)}</dl></DialogContent></Dialog>
  </>;
}
