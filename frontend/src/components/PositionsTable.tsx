import type { Position } from "../api/endpoints";
import { CATEGORY_LABELS, formatBRL, formatPercent } from "../lib/format";
import CategoryAvatar from "./CategoryAvatar";

export default function PositionsTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return (
      <div className="rounded-xl bg-white p-8 text-center text-sm text-slate-500 shadow-sm">
        Nenhuma posição ainda — registre uma transação ou importe seu extrato da B3.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl bg-white shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Ativo</th>
            <th className="px-4 py-3 text-right">Quantidade</th>
            <th className="px-4 py-3 text-right">Preço médio</th>
            <th className="px-4 py-3 text-right">Cotação</th>
            <th className="px-4 py-3 text-right">Rentabilidade</th>
            <th className="px-4 py-3 text-right">% carteira</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const profit = position.profitPercentage;
            return (
              <tr
                key={position.ticker}
                className="border-b border-slate-100 last:border-0 hover:bg-slate-50"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <CategoryAvatar
                      ticker={position.ticker ?? ""}
                      category={position.category ?? "stock"}
                    />
                    <div>
                      <p className="font-semibold">{position.ticker}</p>
                      <p className="text-xs text-slate-500">
                        {CATEGORY_LABELS[position.category ?? ""] ?? position.category}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{position.quantity}</td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatBRL(position.averagePrice)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatBRL(position.currentPrice)}
                </td>
                <td
                  className={`px-4 py-3 text-right font-medium tabular-nums ${
                    profit == null ? "" : profit >= 0 ? "text-emerald-600" : "text-red-600"
                  }`}
                >
                  {formatPercent(profit)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {position.portfolioPercentage == null
                    ? "—"
                    : `${position.portfolioPercentage.toFixed(1).replace(".", ",")}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
