import { useEffect, useState } from "react";
import { Activity, BookOpen, Bot, Menu, Moon, PanelLeftClose, PanelLeftOpen, Plus, Settings2, Sun, TrendingUp } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerTitle } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/runs", label: "运行实例", hint: "创建、启动与观察", icon: Activity },
  { to: "/agents", label: "Agent", hint: "投资者群体快照", icon: Bot },
  { to: "/market", label: "Market", hint: "市场资产与行情", icon: TrendingUp },
  { to: "/settings", label: "设置", hint: "模型与连接配置", icon: Settings2 },
  { to: "/doc", label: "Documentation", hint: "已发布项目文档", icon: BookOpen },
];

function Navigation({ close, collapsed = false }: { close?: () => void; collapsed?: boolean }) {
  return <nav className="grid gap-1 px-3" aria-label="主导航">{nav.map((item) => <NavLink key={item.to} to={item.to} onClick={close} className={({ isActive }) => cn("group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors hover:bg-sidebar-accent", isActive ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground", collapsed && "justify-center px-2")} title={collapsed ? item.label : undefined}><item.icon className="h-4 w-4 shrink-0" /><span className={cn("grid", collapsed && "hidden")}><strong className="font-medium text-current">{item.label}</strong><small className="text-[11px] opacity-70">{item.hint}</small></span></NavLink>)}</nav>;
}

export function AppShell() {
  const [mobile, setMobile] = useState(false);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("twinmarket:sidebar") === "collapsed");
  const [dark, setDark] = useState(() => localStorage.getItem("twinmarket:theme") === "dark" || (!localStorage.getItem("twinmarket:theme") && matchMedia("(prefers-color-scheme: dark)").matches));
  const location = useLocation();
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); localStorage.setItem("twinmarket:theme", dark ? "dark" : "light"); }, [dark]);
  useEffect(() => setMobile(false), [location.pathname]);
  const setSidebar = () => setCollapsed((value) => { localStorage.setItem("twinmarket:sidebar", value ? "expanded" : "collapsed"); return !value; });

  return <div className={cn("min-h-screen md:grid", collapsed ? "md:grid-cols-[72px_1fr]" : "md:grid-cols-[256px_1fr]")}>
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[inherit] border-r bg-card/95 backdrop-blur md:flex md:flex-col">
      <NavLink to="/runs" className={cn("flex h-16 items-center gap-3 border-b px-5", collapsed && "justify-center px-2")}><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm"><Activity className="h-5 w-5" /></span><span className={cn("leading-tight", collapsed && "hidden")}><strong className="block">TwinMarket</strong><small className="text-[10px] font-semibold tracking-[0.18em] text-muted-foreground">OBSERVATORY</small></span></NavLink>
      <div className="flex-1 py-4"><Navigation collapsed={collapsed} /></div>
      <div className="border-t p-3"><Button variant="ghost" size={collapsed ? "icon" : "default"} className={cn(!collapsed && "w-full justify-start")} onClick={setSidebar}>{collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" />收起侧栏</>}</Button></div>
    </aside>
    <div className="min-w-0 md:col-start-2">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b bg-background/90 px-4 backdrop-blur sm:px-6">
        <div className="flex items-center gap-2"><Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobile(true)} aria-label="打开导航"><Menu className="h-5 w-5" /></Button><div><p className="text-xs text-muted-foreground">Research control plane</p><strong className="text-sm">本地 Runtime API</strong></div></div>
        <div className="flex items-center gap-2"><Button asChild size="sm"><NavLink to="/runs/new"><Plus className="h-4 w-4" />新建实例</NavLink></Button><Button variant="outline" size="icon" onClick={() => setDark((value) => !value)} aria-label={dark ? "切换浅色主题" : "切换深色主题"}>{dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</Button></div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] p-4 sm:p-6 lg:p-8"><Outlet /></main>
    </div>
    <Drawer open={mobile} onOpenChange={setMobile}><DrawerContent className="left-0 right-auto border-l-0 border-r p-0"><DrawerTitle className="sr-only">主导航</DrawerTitle><div className="flex h-16 items-center gap-3 border-b px-5"><span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground"><Activity className="h-5 w-5" /></span><strong>TwinMarket</strong></div><div className="py-4"><Navigation close={() => setMobile(false)} /></div></DrawerContent></Drawer>
  </div>;
}
