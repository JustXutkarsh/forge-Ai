"use client";

import { Database, ExternalLink, Layers3, Server, Sparkles } from "lucide-react";

import { useForgeStats, useForgeStatus } from "@/hooks/use-forge-api";
import { formatModel, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function SystemStatus() {
  const status = useForgeStatus();
  const stats = useForgeStats();
  const loading = status.isLoading || stats.isLoading;
  const items = [
    { label: "API status", value: status.data?.semantic_ready ? "Operational" : status.isError ? "Unavailable" : "Checking", icon: Server, tone: status.data?.semantic_ready ? "text-success" : status.isError ? "text-danger" : "text-warning" },
    { label: "Embedding provider", value: status.data?.embedding_provider || "—", icon: Sparkles, tone: "text-accent" },
    { label: "Embedding model", value: formatModel(status.data?.embedding_model || "—"), icon: Layers3, tone: "text-blue-300" },
    { label: "LLM provider", value: status.data?.llm_provider || "—", icon: Database, tone: "text-violet-300" },
  ];

  return (
    <Card className="overflow-hidden">
      <CardHeader><div><CardTitle>System status</CardTitle><p className="mt-1 text-xs text-muted">Live signals from the Forge runtime.</p></div><Badge className={status.data?.semantic_ready ? "border-success/20 bg-success/10 text-success" : "border-warning/20 bg-warning/10 text-warning"}>{status.data?.semantic_ready ? "Healthy" : "Degraded"}</Badge></CardHeader>
      <CardContent>
        <div className="grid gap-2 sm:grid-cols-2">
          {items.map(({ label, value, icon: Icon, tone }) => <div key={label} className="rounded-lg border border-line bg-panel-raised/60 p-3"><div className="flex items-center justify-between"><span className="text-[11px] text-muted">{label}</span><Icon size={14} className={tone} /></div>{loading ? <Skeleton className="mt-2 h-4 w-24" /> : <p className="mt-2 truncate text-sm font-medium text-ink">{value}</p>}</div>)}
        </div>
        <div className="mt-2 flex items-center justify-between rounded-lg border border-line bg-panel-raised/60 px-3 py-3"><div><p className="text-[11px] text-muted">Indexed collection</p><p className="mt-1 text-lg font-semibold tracking-tight text-ink">{stats.isLoading ? "—" : formatNumber(stats.data?.chroma_collection_count)} <span className="text-xs font-normal text-muted">vectors</span></p></div><div className="flex size-8 items-center justify-center rounded-lg bg-accent/10 text-accent"><Layers3 size={16} /></div></div>
        {status.data?.semantic_ready && <a href="/about" className="mt-3 flex items-center gap-1 text-[11px] text-muted transition hover:text-accent">Runtime is serving semantic retrieval <ExternalLink size={11} /></a>}
      </CardContent>
    </Card>
  );
}
