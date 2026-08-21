import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PortfolioSnapshot } from "../api/endpoints";
import { formatBRL, formatShortDate } from "../lib/format";

export default function GrowthChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  if (snapshots.length < 2) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl bg-white text-sm text-slate-500 shadow-sm">
        O gráfico de evolução aparece após alguns dias de snapshots diários.
      </div>
    );
  }

  const data = snapshots.map((snapshot) => ({
    date: snapshot.date as string,
    total: snapshot.totalValue ?? 0,
  }));

  return (
    <div className="rounded-xl bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Evolução do patrimônio</h2>
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="growth" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tickFormatter={formatShortDate}
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickLine={false}
            axisLine={false}
            minTickGap={32}
          />
          <YAxis
            tickFormatter={(value: number) =>
              value >= 1000 ? `${(value / 1000).toFixed(0)}k` : String(value)
            }
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <Tooltip
            formatter={(value) => [formatBRL(Number(value)), "Total"]}
            labelFormatter={formatShortDate}
          />
          <Area
            type="monotone"
            dataKey="total"
            stroke="#2563eb"
            strokeWidth={2}
            fill="url(#growth)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
