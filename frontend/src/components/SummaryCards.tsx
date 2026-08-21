import type { PortfolioSummary } from "../api/endpoints";
import { formatBRL, formatPercent } from "../lib/format";

function Card({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "up" | "down";
}) {
  const accentClass =
    accent === "up" ? "text-emerald-600" : accent === "down" ? "text-red-600" : "";
  return (
    <div className="rounded-xl bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-xl font-bold ${accentClass}`}>{value}</p>
    </div>
  );
}

export default function SummaryCards({ summary }: { summary: PortfolioSummary }) {
  const accentFor = (value?: number | null) =>
    value == null ? undefined : value >= 0 ? "up" : "down";

  return (
    <section
      aria-label="Resumo da carteira"
      className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5"
    >
      <Card label="Patrimônio total" value={formatBRL(summary.totalValue)} />
      <Card
        label="Variação hoje"
        value={formatPercent(summary.todayChangePercentage)}
        accent={accentFor(summary.todayChangePercentage)}
      />
      <Card
        label="Rentabilidade no mês"
        value={formatPercent(summary.monthProfitPercentage)}
        accent={accentFor(summary.monthProfitPercentage)}
      />
      <Card label="Proventos no mês" value={formatBRL(summary.monthDividends)} />
      <Card label="DY médio (12m)" value={formatPercent(summary.averageDy)} />
    </section>
  );
}
