interface KpiTileProps {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "positive" | "negative";
  testId?: string;
}

/** Um número de destaque. O número é o gráfico. */
export function KpiTile({ label, value, hint, tone = "neutral", testId }: KpiTileProps) {
  const toneClass = tone === "positive" ? "text-emerald-400" : tone === "negative" ? "text-red-400" : "text-neutral-100";
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4" data-testid={testId}>
      <p className="text-sm text-neutral-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`} data-testid={testId ? `${testId}-value` : undefined}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-neutral-500">{hint}</p>}
    </div>
  );
}
