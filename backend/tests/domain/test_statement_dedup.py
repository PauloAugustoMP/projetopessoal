from backend.domain.entities import Transaction
from backend.domain.statement_dedup import match_transaction


def _transaction(id: str = "t1", price: float = 9.10, **overrides) -> Transaction:
    defaults = dict(
        id=id, ticker="ITSA4", type="buy", quantity=100, price_per_share=price, date="2026-01-10"
    )
    defaults.update(overrides)
    return Transaction(**defaults)  # type: ignore[arg-type]


def test_a_line_with_no_equivalent_is_new():
    assert match_transaction(_transaction(), []) == "new"
    assert match_transaction(_transaction(), [_transaction(id="e1", date="2026-01-11")]) == "new"
    assert match_transaction(_transaction(), [_transaction(id="e1", quantity=99)]) == "new"
    assert match_transaction(_transaction(), [_transaction(id="e1", type="sell")]) == "new"


def test_one_equivalent_within_a_cent_is_a_duplicate():
    assert match_transaction(_transaction(price=9.10), [_transaction(id="e1", price=9.10)]) == "duplicate"
    assert match_transaction(_transaction(price=9.10), [_transaction(id="e1", price=9.105)]) == "duplicate"


def test_a_price_differing_by_more_than_a_cent_is_not_a_duplicate():
    assert match_transaction(_transaction(price=9.10), [_transaction(id="e1", price=9.13)]) == "new"


def test_more_than_one_candidate_is_ambiguous():
    existing = [_transaction(id="e1"), _transaction(id="e2")]
    assert match_transaction(_transaction(), existing) == "ambiguous"
