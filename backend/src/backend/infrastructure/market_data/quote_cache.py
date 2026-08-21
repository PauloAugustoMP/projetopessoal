"""Quote cache in front of the provider (docs/architecture.md §4.1): avoids
burning the free tier's rate limit when several reads happen close together.

Redis is the intended backend; when it is unreachable the cache degrades to an
in-process dict so the app keeps working (single-user scale makes that loss
acceptable) — the fallback is logged once.
"""

import json
import logging
import time

from backend.ports.market_data_provider import MarketDataProvider, Quote

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30


class _InMemoryBackend:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._data[key] = (time.monotonic() + ttl_seconds, value)


class _RedisBackend:
    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, socket_connect_timeout=1)
        self._client.ping()  # fail fast so the caller can fall back

    def get(self, key: str) -> str | None:
        value = self._client.get(key)
        return value.decode() if value is not None else None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.set(key, value, ex=ttl_seconds)


def make_cache_backend(redis_url: str):
    try:
        return _RedisBackend(redis_url)
    except Exception:
        logger.warning("Redis unavailable at %s — falling back to in-memory quote cache.", redis_url)
        return _InMemoryBackend()


class CachedMarketDataProvider:
    """Decorator over any MarketDataProvider: caches get_quotes per ticker."""

    def __init__(
        self,
        inner: MarketDataProvider,
        backend,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._inner = inner
        self._backend = backend
        self._ttl = ttl_seconds

    def get_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        quotes: dict[str, Quote] = {}
        missing: list[str] = []
        for ticker in tickers:
            cached = self._backend.get(f"quote:{ticker}")
            if cached is not None:
                data = json.loads(cached)
                quotes[ticker] = Quote(**data)
            else:
                missing.append(ticker)

        if missing:
            fresh = self._inner.get_quotes(missing)
            for ticker, quote in fresh.items():
                self._backend.set(
                    f"quote:{ticker}",
                    json.dumps(quote.__dict__),
                    self._ttl,
                )
            quotes.update(fresh)
        return quotes

    def get_price_history(self, ticker: str, from_date: str, to_date: str):
        # Historical prices are cached in Postgres (price_history table), not here.
        return self._inner.get_price_history(ticker, from_date, to_date)
