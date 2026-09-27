import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ErrorState, PageSkeleton, StateView } from "@/components/state-view";
import { Card, CardContent } from "@/components/ui/card";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export function DocumentationPage() {
  const [params, setParams] = useSearchParams();
  const list = useResource((signal) => api.documentation.list(signal), []);
  const selected = params.get("doc") || list.data?.items[0]?.path || "";
  const detail = useResource((signal) => selected ? api.documentation.get(selected, signal) : Promise.resolve(null), [selected]);
  if (list.loading) return <PageSkeleton />;
  if (list.error) return <ErrorState message={list.error.message} retry={list.reload} />;
  return <><PageHeader eyebrow="Read-only entry" title="Documentation" description="仅展示后端明确标记 published: true 的 Markdown 文档。" /><div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]"><Card className="h-fit"><CardContent className="grid gap-1 p-3">{list.data?.items.length ? list.data.items.map((item) => <button key={item.path} onClick={() => setParams({ doc: item.path })} className={cn("rounded-md p-3 text-left hover:bg-muted", selected === item.path && "bg-primary text-primary-foreground")}><strong className="block text-sm">{item.title}</strong><span className="mt-1 block text-xs opacity-70">{item.category}</span></button>) : <StateView icon={<BookOpen className="h-8 w-8" />} title="暂无已发布文档" description="文档需在 frontmatter 中明确 published: true。" />}</CardContent></Card><Card><CardContent className="p-6 sm:p-8">{detail.loading ? <PageSkeleton /> : detail.error ? <ErrorState message={detail.error.message} retry={detail.reload} /> : detail.data ? <article className="prose max-w-none"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ href, children }) => { const target = href?.split("#")[0]; const published = list.data?.items.some((item) => item.path === target); return published ? <a href={`?doc=${encodeURIComponent(target || "")}`} onClick={(event) => { event.preventDefault(); if (target) setParams({ doc: target }); }}>{children}</a> : <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noreferrer">{children}</a>; } }}>{detail.data.content || ""}</ReactMarkdown></article> : <StateView title="选择文档" description="从左侧打开一篇已发布文档。" />}</CardContent></Card></div></>;
}
