"""Shared test-data factories (docs/testing-strategy.md §5)."""


def transaction_payload(**overrides) -> dict:
    payload = {
        "ticker": "ITSA4",
        "type": "buy",
        "quantity": 100,
        "pricePerShare": 9.10,
        "date": "2026-01-10",
        "fees": 0,
    }
    payload.update(overrides)
    return payload
