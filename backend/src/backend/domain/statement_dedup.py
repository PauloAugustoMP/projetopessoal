"""Deduplication of imported statement lines (docs/business-rules.md §7):
a line is equivalent to an existing transaction when ticker, date, quantity and
price all match (price within a cent's tolerance). Exactly one equivalent =>
duplicate (skip). More than one candidate => ambiguous (manual review)."""

from typing import Literal

from .entities import Transaction

PRICE_TOLERANCE = 0.01
QUANTITY_TOLERANCE = 1e-9

MatchOutcome = Literal["new", "duplicate", "ambiguous"]


def match_transaction(candidate: Transaction, existing: list[Transaction]) -> MatchOutcome:
    matches = [
        t
        for t in existing
        if t.ticker == candidate.ticker
        and t.type == candidate.type
        and t.date == candidate.date
        and abs(t.quantity - candidate.quantity) <= QUANTITY_TOLERANCE
        and abs(t.price_per_share - candidate.price_per_share) <= PRICE_TOLERANCE
    ]
    if not matches:
        return "new"
    if len(matches) == 1:
        return "duplicate"
    return "ambiguous"
