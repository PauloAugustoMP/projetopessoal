"""Sprint 3 definition of done: 'the app was off for 5 days' → the 5 missing
snapshots get backfilled on startup, resumably, with the provider mocked."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from backend.application.snapshot_service import LAST_SNAPSHOT_DATE_KEY
from backend.application.startup_catchup import run_startup_catchup
from backend.infrastructure.persistence.database import get_session_factory
from backend.infrastructure.persistence.models import (
    PortfolioSnapshotModel,
    SystemStateModel,
    TransactionModel,
)
from backend.infrastructure.persistence.repositories import SystemStateRepository
from backend.ports.market_data_provider import HistoricalPrice
from tests.fakes import FakeMarketDataProvider

TODAY = date(2026, 8, 20)


def _seed(last_snapshot_days_ago: int) -> None:
    factory = get_session_factory()
    with factory() as session:
        session.add(
            TransactionModel(
                id=uuid.uuid4(),
                ticker="ITSA4",
                type="buy",
                quantity=100,
                price_per_share=9.0,
                date=date(2026, 1, 10),
                fees=0,
                source="manual",
            )
        )
        SystemStateRepository(session).set(
            LAST_SNAPSHOT_DATE_KEY, (TODAY - timedelta(days=last_snapshot_days_ago)).isoformat()
        )
        session.commit()


def _fake_provider() -> FakeMarketDataProvider:
    history = [
        HistoricalPrice(date=(TODAY - timedelta(days=offset)).isoformat(), price=10.0 + offset)
        for offset in range(0, 10)
    ]
    return FakeMarketDataProvider(histories={"ITSA4": history})


def test_five_days_off_backfills_five_snapshots(client, auth_headers):
    _seed(last_snapshot_days_ago=5)
    provider = _fake_provider()

    backfilled = run_startup_catchup(get_session_factory(), provider, TODAY.isoformat())

    assert len(backfilled) == 5
    with get_session_factory()() as session:
        snapshots = session.scalars(
            select(PortfolioSnapshotModel).order_by(PortfolioSnapshotModel.date)
        ).all()
        assert [s.date for s in snapshots] == [
            TODAY - timedelta(days=4),
            TODAY - timedelta(days=3),
            TODAY - timedelta(days=2),
            TODAY - timedelta(days=1),
            TODAY,
        ]
        # Each day valued at that day's price (100 shares x price of the day).
        assert float(snapshots[-1].total_value) == pytest.approx(100 * 10.0)
        assert float(snapshots[0].total_value) == pytest.approx(100 * 14.0)
        state = SystemStateRepository(session)
        assert state.get(LAST_SNAPSHOT_DATE_KEY) == TODAY.isoformat()


def test_catchup_is_resumable_and_idempotent(client, auth_headers):
    _seed(last_snapshot_days_ago=5)
    provider = _fake_provider()

    run_startup_catchup(get_session_factory(), provider, TODAY.isoformat())
    # Running again finds nothing missing and changes nothing.
    second = run_startup_catchup(get_session_factory(), provider, TODAY.isoformat())

    assert second == []
    with get_session_factory()() as session:
        count = len(session.scalars(select(PortfolioSnapshotModel)).all())
    assert count == 5


def test_first_ever_run_has_no_catchup(client, auth_headers):
    backfilled = run_startup_catchup(
        get_session_factory(), _fake_provider(), TODAY.isoformat()
    )
    assert backfilled == []


def test_historical_prices_are_cached_locally_and_not_refetched(client, auth_headers):
    _seed(last_snapshot_days_ago=5)
    provider = _fake_provider()

    run_startup_catchup(get_session_factory(), provider, TODAY.isoformat())

    # One history fetch for the whole backfill, not one per day.
    assert len(provider.history_calls) == 1


def test_snapshot_endpoints_serve_the_backfilled_series(client, auth_headers):
    _seed(last_snapshot_days_ago=5)
    run_startup_catchup(get_session_factory(), _fake_provider(), TODAY.isoformat())

    response = client.get(
        "/api/portfolio/snapshots",
        params={"from": (TODAY - timedelta(days=2)).isoformat(), "to": TODAY.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert body[-1]["date"] == TODAY.isoformat()
    assert body[-1]["valueByCategory"] == {"stock": 1000.0}

    breakdown = client.get(
        "/api/portfolio/growth-breakdown",
        params={"from": (TODAY - timedelta(days=4)).isoformat(), "to": TODAY.isoformat()},
        headers=auth_headers,
    ).json()
    # No contributions or reinvestments in the window: the change is pure appreciation.
    assert breakdown["totalChange"] == pytest.approx(1000.0 - 1400.0)
    assert breakdown["contributions"] == 0
    assert breakdown["appreciation"] == pytest.approx(breakdown["totalChange"])
