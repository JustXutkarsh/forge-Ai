"use client";

import { useState } from "react";
import { Check, Database, ExternalLink, KeyRound, Save, Server, Sparkles } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { HealthDashboard } from "@/components/health-dashboard";
import { SystemStatus } from "@/components/system-status";
import { useApiUrl } from "@/components/api-url-provider";
import { useForgeStats, useForgeStatus } from "@/hooks/use-forge-api";
import { formatModel, formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  const { apiUrl, setApiUrl } = useApiUrl();
  const [draft, setDraft] = useState(apiUrl);
  const [saved, setSaved] = useState(false);
  const status = useForgeStatus();
  const stats = useForgeStats();

  function save() {
    setApiUrl(draft);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  }

  return <AppShell><div className="mx-auto max-w-[1100px] px-4 py-8 sm:px-6 lg:px-10 lg:py-12"><div className="mb-8"><p className="mb-3 text-[10px] font-semibold uppercase tracking-[.18em] text-accent">Workspace configuration</p><h1 className="text-3xl font-semibold tracking-[-.04em] text-ink">Settings</h1><p className="mt-2 max-w-xl text-sm leading-6 text-muted">Configure the connection to your existing Forge API and inspect the active investigation runtime.</p></div><div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]"><div className="space-y-5"><Card><CardHeader><div><CardTitle>Backend connection</CardTitle><p className="mt-1 text-xs text-muted">The frontend never stores credentials. It only calls these API routes.</p></div><Server size={16} className="text-accent" /></CardHeader><CardContent><label className="text-xs font-medium text-ink" htmlFor="api-url">FastAPI base URL</label><div className="mt-2 flex gap-2"><input id="api-url" value={draft} onChange={(event) => setDraft(event.target.value)} className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-canvas px-3 text-sm text-ink outline-none transition placeholder:text-muted focus:border-accent/60" /><Button onClick={save} variant="primary" size="sm">{saved ? <Check size={14} /> : <Save size={14} />} {saved ? "Saved" : "Save"}</Button></div><p className="mt-2 text-[11px] text-muted">Default: <code>{apiUrl}</code></p></CardContent></Card><Card><CardHeader><div><CardTitle>Runtime configuration</CardTitle><p className="mt-1 text-xs text-muted">Read-only values reported by Forge.</p></div><Sparkles size={16} className="text-accent" /></CardHeader><CardContent><div className="divide-y divide-line">{[["Embedding provider", status.data?.embedding_provider || "—"], ["Embedding model", formatModel(status.data?.embedding_model || "—")], ["LLM provider", status.data?.llm_provider || "—"], ["Vector dimension", stats.data?.vector_dimension ? String(stats.data.vector_dimension) : "—"]].map(([label, value]) => <div key={label} className="flex items-center justify-between py-3 first:pt-0 last:pb-0"><span className="text-xs text-muted">{label}</span><span className="max-w-[60%] truncate text-right text-xs font-medium text-ink">{value}</span></div>)}</div></CardContent></Card><Card><CardHeader><div><CardTitle>Security boundary</CardTitle><p className="mt-1 text-xs text-muted">Secrets stay on the FastAPI server.</p></div><KeyRound size={16} className="text-success" /></CardHeader><CardContent><div className="rounded-lg border border-success/15 bg-success/5 p-3 text-xs leading-5 text-muted">OpenAI credentials, local model files, SQLite, and Chroma remain backend-owned. The browser receives only structured investigation responses.</div></CardContent></Card></div><div className="space-y-5"><SystemStatus /><HealthDashboard /><div className="rounded-xl border border-line bg-panel p-4 text-xs text-muted"><div className="flex items-center gap-2 text-ink"><Database size={14} className="text-accent" /> API documentation <ExternalLink size={12} className="ml-auto" /></div><p className="mt-2 leading-5">Explore the live contract in FastAPI Swagger at <code className="text-accent">{apiUrl}/docs</code>.</p><p className="mt-3 font-medium text-ink">{formatNumber(stats.data?.chroma_collection_count)} vectors indexed</p></div></div></div></div></AppShell>;
}
