"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, ChevronRight, CircleHelp, Command, History, Menu, Moon, PanelLeftClose, Plus, Settings, Sparkles, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useForgeStatus } from "@/hooks/use-forge-api";
import { cn, formatModel } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const HISTORY_KEY = "forge-investigations";

const primaryNav = [
  { href: "/", label: "New investigation", icon: Plus },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/about", label: "About Forge", icon: CircleHelp },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [light, setLight] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const status = useForgeStatus();

  useEffect(() => {
    const loadHistory = () => setHistory(JSON.parse(window.localStorage.getItem(HISTORY_KEY) || "[]"));
    loadHistory();
    window.addEventListener("forge-history-updated", loadHistory);
    return () => window.removeEventListener("forge-history-updated", loadHistory);
  }, []);

  function toggleTheme() {
    setLight((current) => {
      const next = !current;
      document.documentElement.classList.toggle("light", next);
      return next;
    });
  }

  const sidebar = (
    <aside className="flex h-full w-[250px] shrink-0 flex-col border-r border-line bg-panel/80 px-3 py-4 backdrop-blur-xl">
      <div className="flex items-center justify-between px-2 pb-7">
        <Link href="/" className="flex items-center gap-2.5" onClick={() => setMobileOpen(false)}>
          <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-black shadow-glow"><Sparkles size={16} strokeWidth={2.5} /></span>
          <span className="text-sm font-semibold tracking-tight text-ink">Forge<span className="text-accent">.</span></span>
        </Link>
        <button className="hidden rounded-md p-1.5 text-muted transition hover:bg-white/[.06] hover:text-ink lg:block" aria-label="Collapse sidebar"><PanelLeftClose size={16} /></button>
        <button className="rounded-md p-1.5 text-muted transition hover:bg-white/[.06] hover:text-ink lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={17} /></button>
      </div>

      <Link href="/" onClick={() => setMobileOpen(false)} className="mb-6 flex items-center gap-2 rounded-lg border border-accent/20 bg-accent/10 px-3 py-2.5 text-xs font-semibold text-accent transition hover:bg-accent/15">
        <Plus size={15} /> New investigation <Command className="ml-auto opacity-60" size={13} />
      </Link>

      <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[.16em] text-muted/70">Workspace</p>
      <nav className="space-y-1">
        {primaryNav.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} onClick={() => setMobileOpen(false)} className={cn("flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium transition", pathname === href ? "bg-white/[.07] text-ink" : "text-muted hover:bg-white/[.04] hover:text-ink")}>
            <Icon size={16} className={pathname === href ? "text-accent" : ""} /> {label}
            {pathname === href && <ChevronRight size={14} className="ml-auto text-muted" />}
          </Link>
        ))}
      </nav>

      <div className="mt-8 flex min-h-0 flex-1 flex-col">
        <div className="mb-2 flex items-center gap-2 px-2 text-[10px] font-semibold uppercase tracking-[.16em] text-muted/70"><History size={13} /> Previous investigations</div>
        <div className="space-y-0.5 overflow-y-auto pr-1">
          {history.length ? history.slice(0, 8).map((question) => (
            <Link key={question} href={`/?q=${encodeURIComponent(question)}`} onClick={() => setMobileOpen(false)} className="block truncate rounded-lg px-3 py-2 text-xs text-muted transition hover:bg-white/[.04] hover:text-ink">{question}</Link>
          )) : <p className="px-3 py-2 text-xs leading-5 text-muted/60">Your recent investigations will appear here.</p>}
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-line bg-panel-raised/70 p-3">
        <div className="flex items-center gap-2 text-xs font-medium text-ink"><Activity size={14} className="text-success" /> Retrieval statistics</div>
        <div className="mt-3 flex items-end justify-between"><span className="text-[11px] text-muted">Collection</span><span className="text-xs font-semibold text-ink">{status.data?.semantic_ready ? "Ready" : "Checking"}</span></div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[.08]"><motion.div initial={{ width: 0 }} animate={{ width: status.data?.semantic_ready ? "100%" : "28%" }} className={cn("h-full rounded-full", status.data?.semantic_ready ? "bg-success" : "bg-warning")} /></div>
        <div className="mt-2 flex items-center justify-between text-[10px] text-muted"><span>Provider</span><span>{formatModel(status.data?.embedding_model || "local")}</span></div>
      </div>
    </aside>
  );

  return (
    <div className="min-h-screen bg-canvas">
      <div className="fixed inset-0 -z-0 grid-fade opacity-40" />
      <div className="relative z-10 flex min-h-screen">
        <div className="hidden lg:block">{sidebar}</div>
        <AnimatePresence>{mobileOpen && <><motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 bg-black/65 lg:hidden" onClick={() => setMobileOpen(false)} /><motion.div initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }} className="fixed inset-y-0 left-0 z-50 lg:hidden">{sidebar}</motion.div></>}</AnimatePresence>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-[65px] items-center justify-between border-b border-line bg-canvas/80 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <button className="rounded-lg border border-line bg-panel p-2 text-muted lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={17} /></button>
              <span className="text-xs text-muted">Workspace <span className="mx-1 text-muted/40">/</span> <span className="text-ink">{pathname === "/" ? "Investigation" : pathname.slice(1).replace("/", " ")}</span></span>
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              <div className="hidden items-center gap-2 text-xs text-muted sm:flex"><span className={cn("size-1.5 rounded-full", status.isError ? "bg-danger" : status.data?.semantic_ready ? "bg-success" : "bg-warning")} /> {status.isError ? "Backend offline" : status.data?.semantic_ready ? "API online" : "Connecting"}</div>
              <Badge className="hidden border-accent/20 bg-accent/10 text-accent sm:inline-flex">{formatModel(status.data?.embedding_model || "local BGE")}</Badge>
              <button onClick={toggleTheme} className="rounded-lg p-2 text-muted transition hover:bg-white/[.06] hover:text-ink" aria-label="Toggle dark mode">{light ? <Moon size={16} /> : <Sun size={16} />}</button>
              <div className="flex size-8 items-center justify-center rounded-full border border-line bg-panel-raised text-[10px] font-bold text-accent">U</div>
            </div>
          </header>
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </div>
    </div>
  );
}
