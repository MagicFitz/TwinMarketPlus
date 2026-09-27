import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { CheckCircle2, CircleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToastItem { id: number; title: string; description?: string; tone: "success" | "error" }
const ToastContext = createContext<(toast: Omit<ToastItem, "id">) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const toast = useCallback((item: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.random();
    setItems((current) => [...current, { ...item, id }]);
    window.setTimeout(() => setItems((current) => current.filter((value) => value.id !== id)), 4500);
  }, []);
  const value = useMemo(() => toast, [toast]);
  return <ToastContext.Provider value={value}>{children}<div className="fixed bottom-4 right-4 z-[80] grid w-[min(380px,calc(100%-2rem))] gap-2" role="region" aria-label="通知">{items.map((item) => <div key={item.id} className={cn("flex gap-3 rounded-lg border bg-popover p-4 text-popover-foreground shadow-lift", item.tone === "error" && "border-destructive/40")} role={item.tone === "error" ? "alert" : "status"}>{item.tone === "success" ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" /> : <CircleAlert className="mt-0.5 h-5 w-5 text-destructive" />}<div className="min-w-0 flex-1"><p className="font-semibold">{item.title}</p>{item.description && <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>}</div><button onClick={() => setItems((current) => current.filter((value) => value.id !== item.id))} aria-label="关闭通知"><X className="h-4 w-4" /></button></div>)}</div></ToastContext.Provider>;
}

export function useToast() { return useContext(ToastContext); }
