"""Contract tests for the brapi.dev adapter (docs/testing-strategy.md §3):
recorded JSON fixtures, never the live API."""

import json
from pathlib import Path

import httpx
import pytest

from backend.infrastructure.market_data.brapi_provider import BrapiProvider
from backend.infrastructure.market_data.quote_cache import (
    CachedMarketDataProvider,
    _InMemoryBackend,
)
from backend.ports.market_data_provider import MarketDataUnavailableError
from tests.fakes import FakeMarketDataProvider
from backend.ports.market_data_provider import Quote

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _provider_returning(status_code: int = 200, body: dict | str = "") -> BrapiProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(body, dict):
            return httpx.Response(status_code, json=body)
        return httpx.Response(status_code, text=body)

    # The SDK accepts an injected httpx client, so the adapter is exercised
    # against recorded responses with no network involved.
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BrapiProvider(api_token="test-token", http_client=client)


def test_maps_quotes_including_a_missing_logo():
    body = json.loads((FIXTURES / "brapi_quote_response.json").read_text())
    quotes = _provider_returning(body=body).get_quotes(["ITSA4", "MXRF11"])

    assert quotes["ITSA4"].price == 11.42
    assert quotes["ITSA4"].change_percent == 1.15
    assert quotes["ITSA4"].logo_url == "https://icons.brapi.dev/icons/ITSA4.svg"
    # Missing logourl maps to None — the UI falls back to an initials avatar.
    assert quotes["MXRF11"].logo_url is None


def test_price_history_filters_the_range_and_skips_days_without_a_close():
    body = json.loads((FIXTURES / "brapi_history_response.json").read_text())
    history = _provider_returning(body=body).get_price_history(
        "ITSA4", "2026-01-01", "2026-01-31"
    )
    assert [(p.date, p.price) for p in history] == [
        ("2026-01-03", 11.2),
        ("2026-01-04", 11.1),
    ]


def test_rate_limit_surfaces_as_the_known_domain_error():
    with pytest.raises(MarketDataUnavailableError):
        _provider_returning(status_code=429, body={}).get_quotes(["ITSA4"])


def test_server_errors_and_non_json_responses_surface_as_the_known_domain_error():
    with pytest.raises(MarketDataUnavailableError):
        _provider_returning(status_code=500, body={}).get_quotes(["ITSA4"])
    with pytest.raises(MarketDataUnavailableError):
        _provider_returning(status_code=200, body="<html>maintenance</html>").get_quotes(["ITSA4"])


def test_the_cache_avoids_hitting_the_provider_twice_within_the_ttl():
    fake = FakeMarketDataProvider(quotes={"ITSA4": Quote(ticker="ITSA4", price=11.0)})
    cached = CachedMarketDataProvider(fake, _InMemoryBackend(), ttl_seconds=60)

    first = cached.get_quotes(["ITSA4"])
    second = cached.get_quotes(["ITSA4"])

    assert first["ITSA4"].price == second["ITSA4"].price == 11.0
    assert len(fake.quote_calls) == 1


def test_authentication_and_connection_failures_also_surface_as_the_known_error():
    """Every SDK failure mode collapses into one error the app knows how to
    degrade from — callers never import the SDK's exception taxonomy."""
    with pytest.raises(MarketDataUnavailableError):
        _provider_returning(status_code=401, body={}).get_quotes(["ITSA4"])

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = BrapiProvider(
        api_token="t", http_client=httpx.Client(transport=httpx.MockTransport(refuse))
    )
    with pytest.raises(MarketDataUnavailableError):
        provider.get_quotes(["ITSA4"])


def test_a_ticker_the_provider_does_not_know_is_absent_rather_than_an_error():
    body = {"results": [{"symbol": "XXXX9"}]}  # no price
    assert _provider_returning(body=body).get_quotes(["XXXX9"]) == {}


def test_price_history_is_empty_when_the_provider_returns_no_results():
    assert _provider_returning(body={"results": []}).get_price_history(
        "ITSA4", "2026-01-01", "2026-01-31"
    ) == []
