"use client";

import { Clock3, Cpu, Gauge, Network } from "lucide-react";
import { motion } from "framer-motion";

import type { Timings } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const metrics = [
  { key: "embedding_ms", label: "Embedding", icon: Cpu, color: "bg-accent" },
  { key: "retrieval_ms", label: "Retrieval", icon: Network, color: "bg-blue-400" },
  { key: "reasoning_ms", label: "Reasoning", icon: Gauge, color: "bg-violet-400" },
  { key: "total_ms", label: "Total", icon: Clock3, color: "bg-success" },
] as const;

export function PerformanceCard({ timings }: { timings?: Timings }) {
  const max = Math.max(...metrics.map(({ key }) => timings?.[key] || 0), 1);
  return <Card><CardHeader><div><CardTitle>Request performance</CardTitle><p className="mt-1 text-xs text-muted">Stage timing from the investigation request.</p></div><Gauge size={16} className="text-muted" /></CardHeader><CardContent><div className="space-y-4">{metrics.map(({ key, label, icon: Icon, color }) => { const value = timings?.[key] || 0; return <div key={key}><div className="mb-1.5 flex items-center gap-2"><Icon size={13} className="text-muted" /><span className="text-xs text-muted">{label}</span><span className="ml-auto font-mono text-xs text-ink">{timings ? `${value.toFixed(0)} ms` : "—"}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-white/[.07]"><motion.div initial={{ width: 0 }} animate={{ width: `${(value / max) * 100}%` }} transition={{ duration: .65, ease: "easeOut" }} className={`h-full rounded-full ${color}`} /></div></div>; })}</div></CardContent></Card>;
}
