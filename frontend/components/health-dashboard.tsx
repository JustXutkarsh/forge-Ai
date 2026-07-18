"use client";

import { CheckCircle2, CircleAlert, Database, Gauge, RefreshCw, Server, Waypoints } from "lucide-react";

import { useRetrievalHealth } from "@/hooks/use-forge-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function Signal({ label, healthy, icon: Icon }: { label: string; healthy: boolean; icon: typeof Server }) {
  return <div className="flex items-center justify-between rounded-lg border border-line bg-panel-raised/60 px-3 py-2.5"><div className="flex items-center gap-2.5"><Icon size={14} className="text-muted" /><span className="text-xs text-ink">{label}</span></div><span className={healthy ? "flex items-center gap-1 text-[11px] text-success" : "flex items-center gap-1 text-[11px] text-danger"}>{healthy ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />} {healthy ? "Ready" : "Offline"}</span></div>;
}

export function HealthDashboard() {
  const health = useRetrievalHealth();
  return <Card><CardHeader><div><CardTitle>Retrieval health</CardTitle><p className="mt-1 text-xs text-muted">A lightweight semantic readiness probe.</p></div><Button variant="ghost" size="sm" onClick={() => health.refetch()} disabled={health.isFetching}><RefreshCw size={13} className={health.isFetching ? "animate-spin" : ""} /> Check</Button></CardHeader><CardContent><div className="space-y-2">{health.isLoading ? <><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></> : <><Signal label="SQLite metadata" healthy={Boolean(health.data?.sqlite_reachable)} icon={Database} /><Signal label="Chroma vector store" healthy={Boolean(health.data?.chroma_reachable)} icon={Waypoints} /><Signal label="Embedding model" healthy={Boolean(health.data?.embedding_model_loaded)} icon={Server} /></>}</div><div className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-panel-raised/60 px-3 py-2.5 text-xs text-muted"><Gauge size={14} className="text-accent" /> Probe latency <span className="ml-auto font-semibold text-ink">{health.data?.latency_ms ?? "—"}{health.data ? " ms" : ""}</span></div></CardContent></Card>;
}
