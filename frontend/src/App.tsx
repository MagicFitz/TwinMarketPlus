import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/app-shell";
import { PageSkeleton, StateView } from "@/components/state-view";

const RunsPage = lazy(() => import("@/routes/runs-page").then((module) => ({ default: module.RunsPage })));
const NewRunPage = lazy(() => import("@/routes/new-run-page").then((module) => ({ default: module.NewRunPage })));
const RunDetailPage = lazy(() => import("@/routes/run-detail-page").then((module) => ({ default: module.RunDetailPage })));
const RuntimePage = lazy(() => import("@/routes/runtime-page").then((module) => ({ default: module.RuntimePage })));
const ResultsPage = lazy(() => import("@/routes/results-page").then((module) => ({ default: module.ResultsPage })));
const AgentsPage = lazy(() => import("@/routes/agents-page").then((module) => ({ default: module.AgentsPage })));
const MarketPage = lazy(() => import("@/routes/market-page").then((module) => ({ default: module.MarketPage })));
const DocumentationPage = lazy(() => import("@/routes/documentation-page").then((module) => ({ default: module.DocumentationPage })));
const SettingsPage = lazy(() => import("@/routes/settings-page").then((module) => ({ default: module.SettingsPage })));

export function App() {
  return <Suspense fallback={<div className="p-6"><PageSkeleton /></div>}>
    <Routes>
      <Route element={<AppShell />}>
      <Route index element={<Navigate to="/runs" replace />} />
      <Route path="runs" element={<RunsPage />} />
      <Route path="runs/new" element={<NewRunPage />} />
      <Route path="runs/:runId" element={<RunDetailPage />} />
      <Route path="runs/:runId/live" element={<RuntimePage />} />
      <Route path="runs/:runId/results" element={<ResultsPage />} />
      <Route path="agents" element={<AgentsPage />} />
      <Route path="market" element={<MarketPage />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="doc" element={<DocumentationPage />} />
      <Route path="*" element={<StateView title="页面不存在" description="该地址不属于 TwinMarket 前端。" />} />
    </Route>
    </Routes>
  </Suspense>;
}
