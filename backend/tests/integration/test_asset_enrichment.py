"""The statement gives us ticker, name and category; the provider adds the logo
and, when we have nothing better, a display name. It must never regress the
catalog nor fail the import."""

import pytest

from backend.application.enrich_assets import enrich_assets
from backend.infrastructure.market_data.factory import set_market_data_provider
from backend.infrastructure.persistence.database import get_session_factory
from backend.infrastructure.persistence.models import AssetModel
from backend.ports.market_data_provider import MarketDataUnavailableError, Quote
from tests.fakes import FakeMarketDataProvider

STATEMENT = (
    "Entrada/Saída;Data;Movimentação;Produto;Instituição;Quantidade;Preço unitário;Valor da Operação\n"
    "Credito;10/01/2026;Compra;TRXF11 - TRX REAL ESTATE FDO INV IMOB;COR;10;R$ 100,00;R$ 1.000,00\n"
).encode("utf-8")


def _asset(ticker: str) -> AssetModel:
    with get_session_factory()() as session:
        return session.get(AssetModel, ticker)


@pytest.fixture
def provider():
    fake = FakeMarketDataProvider(
        quotes={
            "TRXF11": Quote(
                ticker="TRXF11",
                price=101.0,
                logo_url="https://icons.brapi.dev/icons/TRXF11.svg",
                name="TRX Real Estate FII",
            )
        }
    )
    set_market_data_provider(fake)
    yield fake
    set_market_data_provider(None)


def test_the_import_fills_in_the_logo_from_the_provider(client, auth_headers, provider):
    client.post(
        "/api/import/b3-statement",
        files={"file": ("extrato.csv", STATEMENT, "text/csv")},
        headers=auth_headers,
    )
    # TestClient runs background tasks before returning.
    assert _asset("TRXF11").logo_url == "https://icons.brapi.dev/icons/TRXF11.svg"


def test_the_name_from_the_statement_is_not_overwritten(client, auth_headers, provider):
    client.post(
        "/api/import/b3-statement",
        files={"file": ("extrato.csv", STATEMENT, "text/csv")},
        headers=auth_headers,
    )
    # B3's wording is what the user recognizes; enrichment must not rewrite it.
    assert _asset("TRXF11").name == "TRX REAL ESTATE FDO INV IMOB"


def test_a_placeholder_name_is_replaced_by_the_provider_one(client, auth_headers, provider):
    # A statement row without a product name leaves the ticker as the name.
    statement = (
        "Entrada/Saída;Data;Movimentação;Produto;Instituição;Quantidade;Preço unitário;Valor da Operação\n"
        "Credito;10/01/2026;Compra;TRXF11;COR;10;R$ 100,00;R$ 1.000,00\n"
    ).encode("utf-8")
    client.post(
        "/api/import/b3-statement",
        files={"file": ("extrato.csv", statement, "text/csv")},
        headers=auth_headers,
    )
    assert _asset("TRXF11").name == "TRX Real Estate FII"


def test_a_provider_outage_leaves_the_catalog_as_the_statement_wrote_it(client, auth_headers):
    class DownProvider:
        def get_quotes(self, tickers):
            raise MarketDataUnavailableError("down")

        def get_price_history(self, ticker, from_date, to_date):
            raise MarketDataUnavailableError("down")

    set_market_data_provider(DownProvider())
    response = client.post(
        "/api/import/b3-statement",
        files={"file": ("extrato.csv", STATEMENT, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["assetsCreated"] == 1
    asset = _asset("TRXF11")
    assert asset.name == "TRX REAL ESTATE FDO INV IMOB"
    assert asset.logo_url is None
    set_market_data_provider(None)


def test_assets_that_need_nothing_do_not_call_the_provider(client, auth_headers, provider):
    client.post(
        "/api/import/b3-statement",
        files={"file": ("extrato.csv", STATEMENT, "text/csv")},
        headers=auth_headers,
    )
    calls_after_import = len(provider.quote_calls)

    # Everything is already filled in; a second pass must be a no-op.
    assert enrich_assets(get_session_factory(), provider, ["TRXF11"]) == 0
    assert len(provider.quote_calls) == calls_after_import
