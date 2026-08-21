"""Composition root for the market data provider: brapi.dev behind the quote
cache, or a null stand-in when no token is configured. Tests swap the whole
thing through set_market_data_provider."""

import logging

from backend.config import get_settings
from backend.infrastructure.market_data.brapi_provider import BrapiProvider
from backend.infrastructure.market_data.null_provider import NullMarketDataProvider
from backend.infrastructure.market_data.quote_cache import (
    CachedMarketDataProvider,
    make_cache_backend,
)
from backend.ports.market_data_provider import MarketDataProvider

logger = logging.getLogger(__name__)

_provider: MarketDataProvider | None = None


def market_data_is_configured() -> bool:
    return bool(get_settings().brapi_api_token)


def get_market_data_provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if not settings.brapi_api_token:
            logger.warning(
                "BRAPI_API_TOKEN is not set — quotes, price history and logos are "
                "disabled. Positions fall back to cost basis."
            )
            _provider = NullMarketDataProvider()
        else:
            _provider = CachedMarketDataProvider(
                inner=BrapiProvider(api_token=settings.brapi_api_token),
                backend=make_cache_backend(settings.redis_url),
                ttl_seconds=settings.quote_cache_ttl_seconds,
            )
    return _provider


def set_market_data_provider(provider: MarketDataProvider | None) -> None:
    global _provider
    _provider = provider
