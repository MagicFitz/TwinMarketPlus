import { CheckCircle2, CircleAlert, CircleDashed, Clock3, LoaderCircle, PauseCircle, RotateCw, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { HealthStatus, RunStatus, StageStatus } from "@/lib/api-types";

type Status = RunStatus | HealthStatus | StageStatus | "open" | "connecting" | "retrying" | "closed";
const labels: Record<string, string> = {
  draft: "草稿", queued: "排队中", running: "运行中", stopping: "停止中", completed: "已完成", failed: "失败", cancelled: "已取消",
  healthy: "健康", degraded: "降级", stale: "已停滞", unavailable: "不可用", pending: "待处理", retrying: "重试中", skipped: "已跳过",
  open: "实时已连接", connecting: "正在连接", closed: "连接已关闭",
};

export function statusLabel(value?: string | null) { return value ? labels[value] || value : "未知"; }

export function StatusBadge({ value }: { value?: Status | string | null }) {
  const state = value || "unavailable";
  const Icon = state === "completed" || state === "healthy" || state === "open" ? CheckCircle2
    : state === "failed" || state === "unavailable" ? CircleAlert
      : state === "running" || state === "queued" || state === "connecting" ? LoaderCircle
        : state === "retrying" ? RotateCw
          : state === "degraded" || state === "stale" ? ShieldAlert
            : state === "skipped" || state === "cancelled" || state === "stopping" ? PauseCircle
              : state === "draft" ? Clock3 : CircleDashed;
  const variant = state === "completed" || state === "healthy" || state === "open" ? "success"
    : state === "failed" || state === "unavailable" ? "destructive"
      : state === "running" || state === "queued" || state === "retrying" || state === "connecting" ? "warning" : "outline";
  return <Badge variant={variant}><Icon className={state === "running" || state === "connecting" ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} aria-hidden="true" />{statusLabel(state)}</Badge>;
}
