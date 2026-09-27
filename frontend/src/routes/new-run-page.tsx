import { useState, type FormEvent } from "react";
import { ArrowLeft, ChevronDown, ChevronUp, FlaskConical } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField, FormInput, FormTextarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api";
import type { RunConfig } from "@/lib/api-types";

const defaults: RunConfig = { user_count: 10, start_date: "2023-06-15", end_date: "2023-06-16", max_workers: 1, activate_prob: 0.2, prob_of_technical: 0.3, random_seed: 20260916 };

export function NewRunPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("10 Agent 观察运行");
  const [description, setDescription] = useState("");
  const [config, setConfig] = useState(defaults);
  const [advanced, setAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const change = <K extends keyof RunConfig>(key: K, value: RunConfig[K]) => setConfig((current) => ({ ...current, [key]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const run = await api.runs.create({ name, description, config });
      toast({ title: "实例已创建", description: `${run.run_id} 已保存为草稿。`, tone: "success" });
      navigate(`/runs/${encodeURIComponent(run.run_id)}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "创建失败"); } finally { setSaving(false); }
  };
  return <>
    <PageHeader eyebrow="New run" title="创建运行实例" description="创建时冻结非敏感参数和输入文件指纹；模型凭据不会出现在浏览器中。" actions={<Button variant="ghost" asChild><Link to="/runs"><ArrowLeft className="h-4 w-4" />返回列表</Link></Button>} />
    <form onSubmit={submit} className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <Card><CardHeader><CardTitle>实验配置</CardTitle><CardDescription>推荐从小规模运行开始，确认事件和结果链路后再放大 Agent 数量。</CardDescription></CardHeader><CardContent className="grid gap-5"><FormField label="实例名称"><FormInput required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></FormField><FormField label="说明" hint="可选，用于记录实验假设。"><FormTextarea maxLength={2000} value={description} onChange={(event) => setDescription(event.target.value)} /></FormField><div className="grid gap-4 sm:grid-cols-2"><FormField label="Agent 数量"><FormInput type="number" min={1} max={1000} required value={config.user_count} onChange={(event) => change("user_count", Number(event.target.value))} /></FormField><FormField label="并发 Worker"><FormInput type="number" min={1} required value={config.max_workers} onChange={(event) => change("max_workers", Number(event.target.value))} /></FormField><FormField label="开始日期"><FormInput type="date" required value={config.start_date} onChange={(event) => change("start_date", event.target.value)} /></FormField><FormField label="结束日期"><FormInput type="date" required min={config.start_date} value={config.end_date} onChange={(event) => change("end_date", event.target.value)} /></FormField></div><Button type="button" variant="ghost" className="justify-between" onClick={() => setAdvanced((value) => !value)} aria-expanded={advanced}>高级参数{advanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</Button>{advanced && <div className="grid gap-4 rounded-md border bg-muted/30 p-4 sm:grid-cols-3"><FormField label="激活概率"><FormInput type="number" min={0} max={1} step={0.05} value={config.activate_prob} onChange={(event) => change("activate_prob", Number(event.target.value))} /></FormField><FormField label="技术面概率"><FormInput type="number" min={0} max={1} step={0.05} value={config.prob_of_technical} onChange={(event) => change("prob_of_technical", Number(event.target.value))} /></FormField><FormField label="随机种子"><FormInput type="number" value={config.random_seed} onChange={(event) => change("random_seed", Number(event.target.value))} /></FormField></div>}{error && <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive" role="alert">{error}</div>}<Button type="submit" disabled={saving}>{saving ? "正在创建…" : "创建草稿"}</Button></CardContent></Card>
      <Card className="h-fit xl:sticky xl:top-24"><CardHeader><span className="mb-2 grid h-10 w-10 place-items-center rounded-lg bg-primary/10 text-primary"><FlaskConical className="h-5 w-5" /></span><CardTitle>本次运行</CardTitle></CardHeader><CardContent className="grid gap-3 text-sm"><Summary label="Agent" value={config.user_count} /><Summary label="交易区间" value={`${config.start_date} → ${config.end_date}`} /><Summary label="Worker" value={config.max_workers} /><Summary label="随机种子" value={config.random_seed} /><p className="mt-2 border-t pt-4 text-xs leading-5 text-muted-foreground">实例创建后仍是草稿。你可以在详情页复核输入，再明确启动。</p></CardContent></Card>
    </form>
  </>;
}

function Summary({ label, value }: { label: string; value: string | number }) { return <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">{label}</span><strong className="text-right font-mono text-xs">{value}</strong></div>; }
