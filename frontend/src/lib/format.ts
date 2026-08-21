export function formatBRL(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits).replace(".", ",")}%`;
}

export function formatShortDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year.slice(2)}`;
}

export const CATEGORY_LABELS: Record<string, string> = {
  stock: "Ações",
  reit: "FIIs",
  fixed_income: "Renda Fixa",
  crypto: "Cripto",
};

export const CATEGORY_COLORS: Record<string, string> = {
  stock: "#2563eb",
  reit: "#059669",
  fixed_income: "#d97706",
  crypto: "#7c3aed",
};
