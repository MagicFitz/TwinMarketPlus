import { useEffect, useState, type FormEvent } from "react";
import { Braces, KeyRound, Save, Sparkles, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorState, PageSkeleton } from "@/components/state-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField, FormInput, FormSelect } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import type { EmbeddingModelSettings, EmbeddingModelUpdate, LanguageModelSettings, LanguageModelUpdate } from "@/lib/api-types";

function toLanguageForm(value: LanguageModelSettings): LanguageModelUpdate {
  return { api_type: value.api_type || "openai", provider: value.provider, model_name: value.model_name, base_url: value.base_url, timeout: value.timeout };
}

function toEmbeddingForm(value: EmbeddingModelSettings): EmbeddingModelUpdate {
  return { provider: value.provider, model_name: value.model_name, base_url: value.base_url, endpoint: value.endpoint, timeout: value.timeout, max_retries: value.max_retries };
}

export function SettingsPage() {
  const resource = useResource((signal) => api.settings.models(signal), []);
  const toast = useToast();
  const [language, setLanguage] = useState<LanguageModelUpdate | null>(null);
  const [embedding, setEmbedding] = useState<EmbeddingModelUpdate | null>(null);
  const [languageKey, setLanguageKey] = useState("");
  const [embeddingKey, setEmbeddingKey] = useState("");
  const [clearLanguageKey, setClearLanguageKey] = useState(false);
  const [clearEmbeddingKey, setClearEmbeddingKey] = useState(false);
  const [saving, setSaving] = useState<"language" | "embedding" | null>(null);

  useEffect(() => {
    if (!resource.data) return;
    setLanguage(toLanguageForm(resource.data.language));
    setEmbedding(toEmbeddingForm(resource.data.embedding));
    setLanguageKey(""); setEmbeddingKey("");
    setClearLanguageKey(false); setClearEmbeddingKey(false);
  }, [resource.data]);

  if (resource.loading) return <PageSkeleton />;
  if (resource.error || !resource.data) return <ErrorState message={resource.error?.message || "模型设置不可用"} retry={resource.reload} />;
  if (!language || !embedding) return <PageSkeleton />;
  const settings = resource.data;

  const saveLanguage = async (event: FormEvent) => {
    event.preventDefault();
    const payload: LanguageModelUpdate = { ...language };
    if (clearLanguageKey) payload.api_key = "";
    else if (languageKey.trim()) payload.api_key = languageKey.trim();
    setSaving("language");
    try {
      const next = await api.settings.updateLanguage(payload);
      setLanguage(toLanguageForm(next)); setLanguageKey(""); setClearLanguageKey(false);
      toast({ tone: "success", title: "大语言模型设置已保存", description: "后续新建实例将使用这份配置。" });
    } catch (error) {
      toast({ tone: "error", title: "保存失败", description: error instanceof Error ? error.message : "请检查输入后重试。" });
    } finally { setSaving(null); }
  };

  const saveEmbedding = async (event: FormEvent) => {
    event.preventDefault();
    const payload: EmbeddingModelUpdate = { ...embedding };
    if (clearEmbeddingKey) payload.api_key = "";
    else if (embeddingKey.trim()) payload.api_key = embeddingKey.trim();
    setSaving("embedding");
    try {
      const next = await api.settings.updateEmbedding(payload);
      setEmbedding(toEmbeddingForm(next)); setEmbeddingKey(""); setClearEmbeddingKey(false);
      toast({ tone: "success", title: "嵌入模型设置已保存", description: "下次构建新闻索引或启动新进程时会读取它。" });
    } catch (error) {
      toast({ tone: "error", title: "保存失败", description: error instanceof Error ? error.message : "请检查输入后重试。" });
    } finally { setSaving(null); }
  };

  return <>
    <PageHeader eyebrow="Global configuration" title="模型设置" description="在本机保存大语言模型与嵌入模型连接。密钥只写入本地配置文件，页面不会回显。" />
    <div className="mb-6 rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm text-muted-foreground"><p className="flex items-center gap-2 font-medium text-foreground"><Braces className="h-4 w-4 text-primary" />配置生效范围</p><p className="mt-1 leading-6">运行中的任务保留其启动时已加载的配置；保存后，新建任务会使用新的大语言模型配置，重新构建索引或启动新的进程会使用新的嵌入模型配置。</p></div>
    <div className="grid gap-6 xl:grid-cols-2">
      <form onSubmit={saveLanguage}><Card className="h-full"><CardHeader><div className="mb-2 grid h-10 w-10 place-items-center rounded-lg bg-primary/10 text-primary"><Sparkles className="h-5 w-5" /></div><CardTitle>大语言模型</CardTitle><CardDescription>用于 Agent 的市场判断、互动与交易决策。</CardDescription></CardHeader><CardContent className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2"><FormField label="API 类型"><FormSelect value={language.api_type} onChange={(event) => setLanguage({ ...language, api_type: event.target.value })}><option value="openai">OpenAI 兼容</option><option value="openrouter">OpenRouter</option><option value="vllm">vLLM</option><option value="ollama">Ollama</option><option value="local">本地模型</option></FormSelect></FormField><FormField label="Provider"><FormInput required placeholder="例如：openai、vllm" value={language.provider} onChange={(event) => setLanguage({ ...language, provider: event.target.value })} /></FormField></div>
        <FormField label="模型名称"><FormInput required placeholder="例如：gpt-4o、qwen3-30b" value={language.model_name} onChange={(event) => setLanguage({ ...language, model_name: event.target.value })} /></FormField>
        <div className="grid gap-4 sm:grid-cols-[1fr_140px]"><FormField label="服务地址" hint="使用 OpenAI 兼容接口时通常以 /v1 结尾。"><FormInput type="url" placeholder="https://api.example.com/v1" value={language.base_url} onChange={(event) => setLanguage({ ...language, base_url: event.target.value })} /></FormField><FormField label="超时（秒）"><FormInput type="number" min={0} value={language.timeout ?? ""} onChange={(event) => setLanguage({ ...language, timeout: event.target.value === "" ? null : Number(event.target.value) })} /></FormField></div>
        <SecretField configured={settings.language.api_key_configured} value={languageKey} clear={clearLanguageKey} onChange={setLanguageKey} onClear={setClearLanguageKey} />
        <Button type="submit" disabled={saving === "language"}>{saving === "language" ? "正在保存…" : <><Save className="h-4 w-4" />保存大语言模型</>}</Button>
      </CardContent></Card></form>
      <form onSubmit={saveEmbedding}><Card className="h-full"><CardHeader><div className="mb-2 grid h-10 w-10 place-items-center rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-400"><KeyRound className="h-5 w-5" /></div><CardTitle>嵌入模型</CardTitle><CardDescription>用于新闻向量索引与检索，不会替换已有索引。</CardDescription></CardHeader><CardContent className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2"><FormField label="Provider"><FormInput required placeholder="例如：ollama、siliconflow" value={embedding.provider} onChange={(event) => setEmbedding({ ...embedding, provider: event.target.value })} /></FormField><FormField label="模型名称"><FormInput required placeholder="例如：bge-m3" value={embedding.model_name} onChange={(event) => setEmbedding({ ...embedding, model_name: event.target.value })} /></FormField></div>
        <FormField label="服务地址"><FormInput type="url" placeholder="http://localhost:11434" value={embedding.base_url} onChange={(event) => setEmbedding({ ...embedding, base_url: event.target.value })} /></FormField>
        <div className="grid gap-4 sm:grid-cols-[1fr_120px_120px]"><FormField label="嵌入 Endpoint"><FormInput type="url" placeholder="http://localhost:11434/api/embed" value={embedding.endpoint} onChange={(event) => setEmbedding({ ...embedding, endpoint: event.target.value })} /></FormField><FormField label="超时（秒）"><FormInput type="number" min={0} value={embedding.timeout ?? ""} onChange={(event) => setEmbedding({ ...embedding, timeout: event.target.value === "" ? null : Number(event.target.value) })} /></FormField><FormField label="重试次数"><FormInput type="number" min={0} value={embedding.max_retries ?? ""} onChange={(event) => setEmbedding({ ...embedding, max_retries: event.target.value === "" ? null : Number(event.target.value) })} /></FormField></div>
        <SecretField configured={settings.embedding.api_key_configured} value={embeddingKey} clear={clearEmbeddingKey} onChange={setEmbeddingKey} onClear={setClearEmbeddingKey} />
        <Button type="submit" disabled={saving === "embedding"}>{saving === "embedding" ? "正在保存…" : <><Save className="h-4 w-4" />保存嵌入模型</>}</Button>
      </CardContent></Card></form>
    </div>
  </>;
}

function SecretField({ configured, value, clear, onChange, onClear }: { configured: boolean; value: string; clear: boolean; onChange: (value: string) => void; onClear: (value: boolean) => void }) {
  return <div className="rounded-md border bg-muted/25 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">API Key</p><span className={configured ? "text-xs text-emerald-700 dark:text-emerald-400" : "text-xs text-muted-foreground"}>{configured ? "已在本地配置" : "未配置"}</span></div><p className="mt-1 text-xs leading-5 text-muted-foreground">留空并保存会保留现有密钥；新值只会写入本机，绝不回显。</p><FormInput className="mt-3" type="password" autoComplete="new-password" placeholder="输入新密钥以替换" disabled={clear} value={value} onChange={(event) => onChange(event.target.value)} /><label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={clear} onChange={(event) => { onClear(event.target.checked); if (event.target.checked) onChange(""); }} /><Trash2 className="h-3.5 w-3.5" />移除本地保存的 API Key</label></div>;
}
