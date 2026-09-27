import type { ReactNode } from "react";
import { CircleAlert, Inbox, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Skeleton } from "./ui/skeleton";

export function PageSkeleton() {
  return <div className="grid gap-4" aria-label="正在载入"><Skeleton className="h-10 w-64" /><div className="grid gap-4 md:grid-cols-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div><Skeleton className="h-72" /></div>;
}

export function StateView({ icon, title, description, action }: { icon?: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <Card className="grid min-h-56 place-items-center border-dashed p-8 text-center"><div className="grid max-w-md justify-items-center gap-3">{icon || <Inbox className="h-8 w-8 text-muted-foreground" />}<div><h2 className="font-semibold">{title}</h2><p className="mt-1 text-sm text-muted-foreground">{description}</p></div>{action}</div></Card>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <StateView icon={<CircleAlert className="h-8 w-8 text-destructive" />} title="数据暂不可用" description={message} action={retry && <Button variant="outline" onClick={retry}><RefreshCw className="h-4 w-4" />重试</Button>} />;
}
