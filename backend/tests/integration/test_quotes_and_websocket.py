import pytest

from backend.api.websocket import broadcaster
from backend.infrastructure.market_data.factory import set_market_data_provider
from backend.infrastructure.persistence.database import get_session_factory
from backend.ports.market_data_provider import Quote
from tests.factories import transaction_payload
from tests.fakes import FakeMarketDataProvider


@pytest.fixture(autouse=True)
def fake_provider():
    provider = FakeMarketDataProvider(
        quotes={
            "ITSA4": Quote(ticker="ITSA4", price=11.0, change_percent=2.0),
        }
    )
    set_market_data_provider(provider)
    yield provider
    set_market_data_provider(None)


def test_positions_are_enriched_with_live_quotes(client, auth_headers, fake_provider):
    client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10),
        headers=auth_headers,
    )
    positions = client.get("/api/positions", headers=auth_headers).json()
    position = positions[0]

    assert position["currentPrice"] == 11.0
    assert position["profitPercentage"] == pytest.approx(10.0)  # 10 -> 11
    assert position["portfolioPercentage"] == pytest.approx(100.0)


def test_portfolio_summary_uses_quotes_and_counts_assets(client, auth_headers, fake_provider):
    client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10),
        headers=auth_headers,
    )
    summary = client.get("/api/portfolio/summary", headers=auth_headers).json()

    assert summary["totalValue"] == pytest.approx(100 * 11.0)
    assert summary["todayChangePercentage"] == pytest.approx(2.0)
    assert summary["assetCount"] == 1


def test_a_provider_outage_degrades_to_cost_basis_instead_of_failing(client, auth_headers):
    from backend.ports.market_data_provider import MarketDataUnavailableError

    class DownProvider:
        def get_quotes(self, tickers):
            raise MarketDataUnavailableError("down")

        def get_price_history(self, ticker, from_date, to_date):
            raise MarketDataUnavailableError("down")

    set_market_data_provider(DownProvider())
    client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10),
        headers=auth_headers,
    )
    positions = client.get("/api/positions", headers=auth_headers).json()
    assert positions[0]["currentPrice"] is None

    summary = client.get("/api/portfolio/summary", headers=auth_headers).json()
    assert summary["totalValue"] == pytest.approx(1000.0)  # cost basis


def test_websocket_rejects_a_missing_or_invalid_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/quotes"):
            pass
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/quotes?token=garbage"):
            pass


def test_websocket_delivers_a_price_update_to_a_connected_client(client, auth_headers):
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/quotes?token={token}") as websocket:
        # Same path the price_poll job uses from the scheduler thread.
        broadcaster.broadcast_from_thread(
            {"type": "quotes", "quotes": {"ITSA4": {"price": 11.5, "changePercent": 1.0}}}
        )
        message = websocket.receive_json()

    assert message["type"] == "quotes"
    assert message["quotes"]["ITSA4"]["price"] == 11.5


def test_price_poll_broadcasts_quotes_for_held_tickers(client, auth_headers, fake_provider):
    from backend.infrastructure.jobs.price_poll import poll_prices

    client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10),
        headers=auth_headers,
    )

    received: list[dict] = []
    poll_prices(get_session_factory(), fake_provider, received.append, force=True)

    assert len(received) == 1
    assert received[0]["quotes"]["ITSA4"]["price"] == 11.0
    assert fake_provider.quote_calls == [["ITSA4"]]


def test_an_expired_token_is_rejected(client):
    """The access token lives 15 minutes and the socket carries it in the
    handshake URL, so an expired one is rejected before the connection opens —
    there is no 401 for the client to react to. The frontend refreshes ahead of
    every attempt for exactly this reason."""
    from datetime import datetime, timedelta, timezone

    import jwt

    from backend.config import get_settings

    expired = jwt.encode(
        {
            "sub": "user",
            "type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=1),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=45),
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/quotes?token={expired}"):
            pass


def test_a_refresh_token_cannot_open_the_quote_channel(client):
    login = client.post("/api/auth/login", json={"password": "test-password"}).json()
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/quotes?token={login['refreshToken']}"):
            pass
