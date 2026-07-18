"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, FileText, Hash, Sparkles } from "lucide-react";
import { useState } from "react";

import type { EvidenceItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export function EvidenceList({ evidence }: { evidence: EvidenceItem[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!evidence.length) return <div className="rounded-xl border border-dashed border-line bg-panel/50 p-8 text-center text-xs text-muted">No supporting evidence was returned for this investigation.</div>;
  return <div className="space-y-2">{evidence.map((item, index) => { const open = expanded === item.ticket_id; return <motion.div layout key={`${item.ticket_id}-${index}`} className="overflow-hidden rounded-xl border border-line bg-panel transition hover:border-white/20 hover:bg-panel-raised/70"><button className="flex w-full items-center gap-3 px-4 py-3.5 text-left" onClick={() => setExpanded(open ? null : item.ticket_id)} aria-expanded={open}><span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent"><FileText size={15} /></span><span className="min-w-0 flex-1"><span className="flex items-center gap-2"><span className="font-mono text-xs font-semibold text-ink">Ticket {item.ticket_id}</span>{index === 0 && <Badge className="border-accent/20 bg-accent/10 px-1.5 text-accent">Top match</Badge>}</span><span className="mt-1 block truncate text-xs text-muted">{item.summary}</span></span><span className="hidden items-center gap-1.5 sm:flex"><Sparkles size={12} className="text-accent" /><span className="font-mono text-xs text-ink">{item.score.toFixed(3)}</span></span><ChevronDown size={15} className={cn("shrink-0 text-muted transition", open && "rotate-180 text-ink")} /></button><AnimatePresence initial={false}>{open && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="border-t border-line"><div className="grid gap-3 px-4 py-4 sm:grid-cols-[1fr_auto]"><div><p className="mb-1 text-[10px] font-semibold uppercase tracking-[.14em] text-muted">Indexed summary</p><p className="text-xs leading-6 text-ink">{item.summary}</p></div><div className="flex items-start gap-1.5 text-xs text-muted"><Hash size={13} className="mt-0.5 text-accent" /> {item.ticket_id}</div></div></motion.div>}</AnimatePresence></motion.div>; })}</div>;
}
