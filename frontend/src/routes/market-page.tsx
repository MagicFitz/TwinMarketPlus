import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ErrorState, PageSkeleton, StateView } from "@/components/state-view";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormSelect } from "@/components/ui/form";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

export function MarketPage() {
  const [params, setParams] = useSearchParams(); const runId = params.get("run") || "template"; const asset = params.get("asset") || undefined;
  const state = useResource((signal) => api.runs.market(runId, asset, signal), [runId, asset]);
  if (state.loading) return <PageSkeleton />;
  if (state.error || !state.data) return <ErrorState message={state.error?.message || "市场数据不可用"} retry={state.reload} />;
  const current = state.data.assets.find((item) => item.stock_id === state.data?.selected);
  return <><PageHeader eyebrow="Read-only entry" title="Market" description={`来源：${state.data.source}`} actions={<FormSelect aria-label="选择资产" value={state.data.selected} onChange={(event) => setParams({ ...(runId !== "template" ? { run: runId } : {}), asset: event.target.value })}>{state.data.assets.map((item) => <option key={item.stock_id} value={item.stock_id}>{item.stock_id} · {item.name}</option>)}</FormSelect>} /><div className="grid gap-4 lg:grid-cols-[320px_1fr]"><Card><CardHeader><CardTitle>{current?.name || state.data.selected}</CardTitle></CardHeader><CardContent className="grid gap-3 text-sm"><Fact label="资产代码" value={current?.stock_id} /><Fact label="行业" value={current?.industry} /><Fact label="权重" value={current?.weight} /><Fact label="说明" value={current?.description} /></CardContent></Card><Card><CardHeader><CardTitle>历史行情</CardTitle></CardHeader><CardContent>{!state.data.prices.length ? <StateView title="没有行情记录" description="该资产暂未返回历史价格。" /> : <Table><TableHeader><TableRow><TableHead>日期</TableHead><TableHead>收盘价</TableHead><TableHead>涨跌幅</TableHead><TableHead>成交量</TableHead></TableRow></TableHeader><TableBody>{state.data.prices.slice(-60).reverse().map((price) => <TableRow key={price.date}><TableCell>{price.date}</TableCell><TableCell>{formatNumber(price.close_price)}</TableCell><TableCell>{formatNumber(price.pct_chg)}%</TableCell><TableCell>{formatNumber(price.vol, 0)}</TableCell></TableRow>)}</TableBody></Table>}</CardContent></Card></div></>;
}
function Fact({ label, value }: { label: string; value: unknown }) { return <div><span className="text-xs text-muted-foreground">{label}</span><p className="mt-1">{value == null || value === "" ? "—" : String(value)}</p></div>; }
