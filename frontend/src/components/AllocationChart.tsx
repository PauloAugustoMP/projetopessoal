import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Position } from "../api/endpoints";
import { CATEGORY_COLORS, CATEGORY_LABELS, formatBRL } from "../lib/format";

export default function AllocationChart({ positions }: { positions: Position[] }) {
  const byCategory = new Map<string, number>();
  for (const position of positions) {
    const category = position.category ?? "stock";
    const value =
      (position.quantity ?? 0) * (position.currentPrice ?? position.averagePrice ?? 0);
    byCategory.set(category, (byCategory.get(category) ?? 0) + value);
  }
  const data = [...byCategory.entries()].map(([category, value]) => ({
    category,
    name: CATEGORY_LABELS[category] ?? category,
    value,
  }));

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl bg-white text-sm text-slate-500 shadow-sm">
        Sem posições ainda.
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Alocação por categoria</h2>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={55}
            outerRadius={80}
            paddingAngle={2}
          >
            {data.map((entry) => (
              <Cell
                key={entry.category}
                fill={CATEGORY_COLORS[entry.category] ?? "#475569"}
              />
            ))}
          </Pie>
          <Tooltip formatter={(value) => formatBRL(Number(value))} />
        </PieChart>
      </ResponsiveContainer>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        {data.map((entry) => (
          <li key={entry.category} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="size-2.5 rounded-full"
              style={{ backgroundColor: CATEGORY_COLORS[entry.category] ?? "#475569" }}
            />
            {entry.name}
          </li>
        ))}
      </ul>
    </div>
  );
}
