"""Composition root for the market data provider: brapi.dev wrapped in the
quote cache. Tests swap the whole thing via set_market_data_provider."""

from backend.config import get_settings
from backend.infrastructure.market_data.brapi_provider import BrapiProvider
from backend.infrastructure.market_data.quote_cache import (
    CachedMarketDataProvider,
    make_cache_backend,
)
from backend.ports.market_data_provider import MarketDataProvider

_provider: MarketDataProvider | None = None


def get_market_data_provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        _provider = CachedMarketDataProvider(
            inner=BrapiProvider(api_token=settings.brapi_api_token),
            backend=make_cache_backend(settings.redis_url),
            ttl_seconds=settings.quote_cache_ttl_seconds,
        )
    return _provider


def set_market_data_provider(provider: MarketDataProvider | None) -> None:
    global _provider
    _provider = provider
