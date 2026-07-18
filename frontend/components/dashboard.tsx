"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, Bot, Check, CircleAlert, Command, Database, Lightbulb, Loader2, MessageSquareText, RotateCcw, Search, Sparkles, Target } from "lucide-react";
import { useSearchParams } from "next/navigation";

import { useAsk, useForgeStats, useForgeStatus } from "@/hooks/use-forge-api";
import { cn, formatModel, formatNumber } from "@/lib/utils";
import { AppShell } from "@/components/app-shell";
import { EvidenceList } from "@/components/evidence-list";
import { InvestigationSummary } from "@/components/investigation-summary";
import { HealthDashboard } from "@/components/health-dashboard";
import { PerformanceCard } from "@/components/performance-card";
import { SystemStatus } from "@/components/system-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const HISTORY_KEY = "forge-investigations";
const suggestions = ["Summarize login issues", "What are the top complaint categories?", "Why are users unhappy?", "How many payment issues occurred?"];

function isEvidenceExplanationQuestion(value: string): boolean {
  const lowered = value.toLowerCase();
  return lowered.includes("selected") && (lowered.includes("explain") || lowered.includes("ticket id")) || lowered.includes("explain the evidence");
}

export function Dashboard() {
  const params = useSearchParams();
  const [question, setQuestion] = useState("");
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const ask = useAsk();
  const status = useForgeStatus();
  const stats = useForgeStats();

  useEffect(() => {
    const query = params.get("q");
    if (query) setQuestion(query);
  }, [params]);

  const isReady = Boolean(status.data?.semantic_ready);
  const currentError = ask.error?.message || (status.isError ? "Forge could not reach the backend." : "");
  const response = ask.data;
  const statusLine = useMemo(() => {
    if (ask.isPending) return "Forge is searching the indexed evidence";
    if (response) return "Investigation complete";
    return "Ready when you are";
  }, [ask.isPending, response]);

  function saveHistory(value: string) {
    const current = JSON.parse(window.localStorage.getItem(HISTORY_KEY) || "[]") as string[];
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify([value, ...current.filter((item) => item !== value)].slice(0, 8)));
    window.dispatchEvent(new Event("forge-history-updated"));
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const value = question.trim();
    if (!value || ask.isPending) return;
    setHasSubmitted(true);
    saveHistory(value);
    const investigationContext = isEvidenceExplanationQuestion(value) && response
      ? { retrieval_strategy: response.retrieval_strategy, evidence: response.evidence }
      : undefined;
    ask.mutate({ question: value, maxEvidence: 5, investigationContext });
  }

  return <AppShell><div className="mx-auto max-w-[1440px] px-4 py-7 sm:px-6 lg:px-10 lg:py-10">
    <div className="mb-8 flex flex-col justify-between gap-5 md:flex-row md:items-end"><div><div className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.18em] text-accent"><span className="size-1.5 rounded-full bg-accent" /> AI support investigation</div><h1 className="text-balance text-3xl font-semibold tracking-[-.04em] text-ink sm:text-4xl">Ask your support data<br className="hidden sm:block" /> <span className="text-muted">something difficult.</span></h1><p className="mt-3 max-w-xl text-sm leading-6 text-muted">Forge turns support records into grounded answers, with every conclusion tied back to indexed evidence.</p></div><div className="flex items-center gap-2 text-xs text-muted"><span className="flex items-center gap-1.5 rounded-full border border-line bg-panel px-3 py-2"><Database size={13} className="text-accent" /> {formatNumber(stats.data?.total_tickets)} tickets</span><span className="hidden items-center gap-1.5 rounded-full border border-line bg-panel px-3 py-2 sm:flex"><Sparkles size={13} className="text-accent" /> {formatModel(status.data?.embedding_model || "BGE local")}</span></div></div>

    {status.isError && <Card className="mb-5 border-danger/20 bg-danger/5"><div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center"><CircleAlert className="text-danger" size={20} /><div className="flex-1"><p className="text-sm font-medium text-ink">Backend unavailable</p><p className="mt-1 text-xs text-muted">Start FastAPI with <code className="rounded bg-black/20 px-1.5 py-0.5 text-danger">uvicorn forge.api.app:app --reload</code>, then retry.</p></div><Button size="sm" onClick={() => { status.refetch(); stats.refetch(); }}><RotateCcw size={13} /> Retry</Button></div></Card>}

    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-5">
        <Card className="overflow-hidden border-accent/15 shadow-glow"><div className="border-b border-line px-5 pb-4 pt-5 sm:px-6"><div className="flex items-center gap-2"><span className="flex size-7 items-center justify-center rounded-lg bg-accent text-black"><MessageSquareText size={14} /></span><span className="text-sm font-semibold text-ink">New investigation</span><Badge className="ml-auto border-success/20 bg-success/10 text-success"><span className="mr-1.5 size-1.5 rounded-full bg-success" /> Grounded mode</Badge></div></div><form onSubmit={submit} className="p-4 sm:p-5"><div className="rounded-xl border border-line bg-canvas/70 transition focus-within:border-accent/50 focus-within:shadow-[0_0_0_3px_rgba(249,115,22,.08)]"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submit(); }} placeholder="Ask about your support data..." rows={3} className="w-full resize-none bg-transparent px-4 pt-4 text-sm leading-6 text-ink outline-none placeholder:text-muted/60" aria-label="Investigation question" /><div className="flex items-center justify-between px-3 pb-3 pt-2"><span className="hidden items-center gap-1.5 text-[10px] text-muted sm:flex"><Command size={11} /> Enter to run</span><span className="ml-auto text-[10px] text-muted">{question.length}/4000</span><Button type="submit" variant="primary" size="sm" className="ml-3" disabled={!question.trim() || ask.isPending}>{ask.isPending ? <Loader2 size={14} className="animate-spin" /> : <ArrowUp size={15} />} {ask.isPending ? "Investigating" : "Investigate"}</Button></div></div><div className="mt-3 flex flex-wrap gap-2">{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setQuestion(suggestion)} className="rounded-full border border-line bg-panel px-2.5 py-1.5 text-[11px] text-muted transition hover:border-accent/30 hover:bg-accent/10 hover:text-accent">{suggestion}</button>)}</div></form></Card>

        <AnimatePresence mode="wait">
          {ask.isPending && <motion.div key="loading" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}><Card><div className="flex items-center gap-3 border-b border-line px-5 py-4"><span className="flex size-7 items-center justify-center rounded-lg bg-accent/10 text-accent"><Bot size={15} /></span><div><p className="text-sm font-medium text-ink">Investigating your question</p><p className="mt-0.5 text-xs text-muted">Searching semantic evidence, then grounding the answer <span className="inline-flex w-5"><span className="animate-pulse">...</span></span></p></div></div><div className="space-y-3 p-5"><Skeleton className="h-3 w-11/12" /><Skeleton className="h-3 w-4/5" /><Skeleton className="h-3 w-3/5" /></div></Card></motion.div>}
          {currentError && !ask.isPending && <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><Card className="border-danger/20 bg-danger/5"><div className="flex gap-3 p-5"><CircleAlert className="shrink-0 text-danger" size={18} /><div><p className="text-sm font-medium text-ink">Investigation failed</p><p className="mt-1 text-xs leading-5 text-muted">{currentError}</p><Button variant="danger" size="sm" className="mt-4" onClick={() => submit()}><RotateCcw size={13} /> Try again</Button></div></div></Card></motion.div>}
          {response && !ask.isPending && !currentError && <motion.div key="response" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .35 }} className="space-y-5"><Card><div className="border-b border-line px-5 py-4 sm:px-6"><div className="flex flex-wrap items-center gap-2"><span className="flex size-7 items-center justify-center rounded-lg bg-accent/10 text-accent"><Bot size={15} /></span><span className="text-sm font-medium text-ink">Forge answer</span><Badge className="border-success/20 bg-success/10 text-success"><Check size={11} className="mr-1" /> {statusLine}</Badge><span className="ml-auto flex items-center gap-1.5 text-[11px] text-muted"><Target size={13} className="text-accent" /> {response.retrieval_strategy.replace("_", " ")}</span></div></div><div className="px-5 py-5 sm:px-6"><p className="mb-3 text-xs font-medium text-muted">{response.question}</p><InvestigationSummary answer={response.answer} /><div className="mt-6 flex flex-wrap gap-2 border-t border-line pt-4"><Badge className="border-accent/20 bg-accent/10 text-accent">Confidence {(response.confidence * 100).toFixed(0)}%</Badge><Badge>{response.retrieval_strategy.replace("_", " ")}</Badge><Badge>{response.reasoning_provider} reasoning</Badge></div></div></Card><div><div className="mb-3 flex items-center justify-between"><div><h2 className="text-sm font-semibold text-ink">Evidence</h2><p className="mt-1 text-xs text-muted">The records Forge used to ground this answer.</p></div><span className="font-mono text-[11px] text-muted">{response.evidence.length} sources</span></div><EvidenceList evidence={response.evidence} /></div></motion.div>}
        </AnimatePresence>

        {!hasSubmitted && <div className="grid gap-3 pt-1 sm:grid-cols-3"><div className="rounded-xl border border-line bg-panel/60 p-4"><Lightbulb size={16} className="text-accent" /><p className="mt-3 text-xs font-semibold text-ink">Ask naturally</p><p className="mt-1 text-xs leading-5 text-muted">Use synonyms like authentication, billing, or slow.</p></div><div className="rounded-xl border border-line bg-panel/60 p-4"><Search size={16} className="text-blue-300" /><p className="mt-3 text-xs font-semibold text-ink">Search semantically</p><p className="mt-1 text-xs leading-5 text-muted">BGE embeddings find related tickets beyond exact words.</p></div><div className="rounded-xl border border-line bg-panel/60 p-4"><Target size={16} className="text-success" /><p className="mt-3 text-xs font-semibold text-ink">Stay grounded</p><p className="mt-1 text-xs leading-5 text-muted">Every answer shows the evidence behind it.</p></div></div>}
      </div>
      <aside className="space-y-5"><PerformanceCard timings={response?.timings} /><SystemStatus /><HealthDashboard /></aside>
    </div>
  </div></AppShell>;
}
