"""Running without a market data token is a supported state, not a broken one:
the SDK refuses to build a client without an api_key, so the composition root
substitutes a null provider and every consumer degrades to cost basis."""

import pytest

from backend.infrastructure.market_data.factory import (
    get_market_data_provider,
    market_data_is_configured,
    set_market_data_provider,
)
from backend.ports.market_data_provider import MarketDataUnavailableError
from tests.factories import transaction_payload


@pytest.fixture
def without_token(monkeypatch):
    from backend.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "brapi_api_token", "", raising=False)
    set_market_data_provider(None)  # force the factory to rebuild
    yield
    set_market_data_provider(None)


def test_the_factory_falls_back_to_a_null_provider(without_token):
    assert market_data_is_configured() is False
    with pytest.raises(MarketDataUnavailableError):
        get_market_data_provider().get_quotes(["ITSA4"])


def test_the_dashboard_still_works_without_a_token(client, auth_headers, without_token):
    client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10),
        headers=auth_headers,
    )

    positions = client.get("/api/positions", headers=auth_headers)
    assert positions.status_code == 200
    assert positions.json()[0]["currentPrice"] is None

    summary = client.get("/api/portfolio/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json()["totalValue"] == 1000.0  # cost basis


def test_price_poll_is_not_scheduled_without_a_token(without_token):
    from backend.infrastructure.jobs.scheduler import build_scheduler

    scheduler = build_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "price_poll" not in job_ids
    assert "daily_snapshot" in job_ids  # snapshots still run, valued at cost
