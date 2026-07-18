const SECTION_HEADINGS = new Set([
  "recurring pattern",
  "root causes",
  "affected users",
  "recommended actions",
  "supporting evidence",
]);

function headingKey(value: string): string {
  return value.replace(/:$/, "").trim().toLowerCase();
}

function bulletText(value: string): string | null {
  const match = value.match(/^[•·*-]\s*(.+)$/);
  return match?.[1] || null;
}

export function InvestigationSummary({ answer }: { answer: string }) {
  const lines = answer.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const structured = lines.some((line) => {
    const key = headingKey(line);
    return key === "investigation summary" || SECTION_HEADINGS.has(key);
  });

  if (!structured) {
    return <div className="space-y-4"><h3 className="text-base font-semibold tracking-tight text-ink">Investigation Summary</h3><p className="text-[15px] leading-7 text-ink">{answer}</p></div>;
  }

  return (
    <div className="space-y-4">
      {lines.map((line, index) => {
        const key = headingKey(line);
        const bullet = bulletText(line);

        if (key === "investigation summary") {
          return <h3 key={`${line}-${index}`} className="text-base font-semibold tracking-tight text-ink">{line.replace(/:$/, "")}</h3>;
        }

        if (SECTION_HEADINGS.has(key)) {
          return <h4 key={`${line}-${index}`} className="pt-2 text-[10px] font-semibold uppercase tracking-[.16em] text-accent">{line.replace(/:$/, "")}</h4>;
        }

        if (bullet) {
          return <div key={`${line}-${index}`} className="flex gap-2 text-[15px] leading-7 text-ink"><span className="mt-[11px] size-1.5 shrink-0 rounded-full bg-accent" /> <span>{bullet}</span></div>;
        }

        return <p key={`${line}-${index}`} className="text-[15px] leading-7 text-ink">{line}</p>;
      })}
    </div>
  );
}
