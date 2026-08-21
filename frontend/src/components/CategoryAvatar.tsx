import { CATEGORY_COLORS } from "../lib/format";

/** Logo when the provider gave one; otherwise an initials avatar colored by
 * category (docs/openapi/openapi.yaml, Asset.logoUrl). */
export default function CategoryAvatar({
  ticker,
  category,
  logoUrl,
}: {
  ticker: string;
  category: string;
  logoUrl?: string | null;
}) {
  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt=""
        className="size-8 rounded-full bg-white object-contain ring-1 ring-slate-200"
      />
    );
  }
  return (
    <span
      aria-hidden
      className="flex size-8 items-center justify-center rounded-full text-xs font-bold text-white"
      style={{ backgroundColor: CATEGORY_COLORS[category] ?? "#475569" }}
    >
      {ticker.slice(0, 2)}
    </span>
  );
}
