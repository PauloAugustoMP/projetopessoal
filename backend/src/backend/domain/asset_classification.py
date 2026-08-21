"""Infers an asset's category from what the B3 statement itself shows
(docs/business-rules.md §7) — used when the import meets a ticker that is not
in the catalog yet.

Evidence beats pattern: a `Rendimento` payout means a REIT, while
`Dividendo`/`JCP` means a company. Only when a ticker has no payout in the file
do we fall back to the ticker's shape, where the suffix is a decent signal:
`11` is usually a REIT (though it is also used by Units, hence evidence first),
and `3`/`4`/`5`/`6` are company shares. `12`/`13` are subscription rights and
receipts derived from an `11`.
"""

import re

from .entities import AssetCategory

REIT_SUFFIX = re.compile(r"^[A-Z]{4}1[123]$")
STOCK_SUFFIX = re.compile(r"^[A-Z]{4}[3456]$")


def infer_category(ticker: str, dividend_types: set[str] | None = None) -> AssetCategory:
    evidence = dividend_types or set()
    if "reit_income" in evidence:
        return "reit"
    if evidence & {"dividend", "jcp"}:
        return "stock"

    normalized = ticker.strip().upper()
    if REIT_SUFFIX.match(normalized):
        return "reit"
    if STOCK_SUFFIX.match(normalized):
        return "stock"
    return "stock"
