"use client";

import { RefreshCw, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <div className="max-w-md rounded-xl2 border border-line bg-panel p-8 text-center shadow-panel">
        <TriangleAlert className="mx-auto mb-4 text-warning" size={28} />
        <h1 className="text-xl font-semibold text-ink">The console hit a snag</h1>
        <p className="mt-2 text-sm leading-6 text-muted">Your Forge backend is safe. Try rendering this view again.</p>
        <Button className="mt-6" onClick={reset}><RefreshCw size={15} /> Try again</Button>
      </div>
    </main>
  );
}
