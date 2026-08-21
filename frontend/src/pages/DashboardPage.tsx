import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { clearTokens } from "../api/client";
import {
  fetchPositions,
  fetchSnapshots,
  fetchSummary,
  type PortfolioSnapshot,
  type PortfolioSummary,
  type Position,
} from "../api/endpoints";
import AllocationChart from "../components/AllocationChart";
import GrowthChart from "../components/GrowthChart";
import PositionsTable from "../components/PositionsTable";
import SummaryCards from "../components/SummaryCards";
import { useLiveQuotes } from "../hooks/useLiveQuotes";

export default function DashboardPage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    // `stale` guards against a response landing after the component unmounted
    // (or after a re-run), which would otherwise update dead state.
    let stale = false;

    async function load() {
      try {
        const [summaryData, positionsData, snapshotsData] = await Promise.all([
          fetchSummary(),
          fetchPositions(),
          fetchSnapshots(),
        ]);
        if (stale) return;
        setSummary(summaryData);
        setPositions(positionsData);
        setSnapshots(snapshotsData);
        setError(null);
      } catch {
        if (stale) return;
        setError("Não foi possível carregar os dados. Verifique se a API local está no ar.");
      } finally {
        if (!stale) setLoading(false);
      }
    }

    void load();
    return () => {
      stale = true;
    };
  }, []);

  const liveQuotes = useLiveQuotes(!loading && error === null);

  /** Live prices refine what the REST call returned, without a refetch. */
  const livePositions = useMemo(
    () =>
      positions.map((position) => {
        const quote = position.ticker ? liveQuotes[position.ticker] : undefined;
        if (!quote) return position;
        const averagePrice = position.averagePrice ?? 0;
        return {
          ...position,
          currentPrice: quote.price,
          profitPercentage:
            averagePrice > 0 ? ((quote.price - averagePrice) / averagePrice) * 100 : null,
        };
      }),
    [positions, liveQuotes],
  );

  function handleLogout() {
    clearTokens();
    navigate("/login", { replace: true });
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-slate-500">
        Carregando...
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl space-y-4 p-4 md:p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Minha Carteira</h1>
          <p className="text-sm text-slate-500">
            {Object.keys(liveQuotes).length > 0 ? "Cotações ao vivo" : "Dados da carteira"}
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
        >
          Sair
        </button>
      </header>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {summary && <SummaryCards summary={summary} />}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <GrowthChart snapshots={snapshots} />
        </div>
        <AllocationChart positions={livePositions} />
      </div>

      <section aria-label="Posições">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Meus ativos</h2>
        <PositionsTable positions={livePositions} />
      </section>
    </main>
  );
}
