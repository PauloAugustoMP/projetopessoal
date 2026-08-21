"""APScheduler wiring (docs/architecture.md §2: jobs run inside the FastAPI
process — no separate worker at single-user scale)."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.api.websocket import broadcaster
from backend.config import get_settings
from backend.infrastructure.jobs.daily_snapshot import run_daily_snapshot
from backend.infrastructure.jobs.price_poll import poll_prices
from backend.infrastructure.market_data.factory import get_market_data_provider
from backend.infrastructure.persistence.database import get_session_factory

logger = logging.getLogger(__name__)


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")

    scheduler.add_job(
        lambda: poll_prices(
            get_session_factory(), get_market_data_provider(), broadcaster.broadcast_from_thread
        ),
        IntervalTrigger(seconds=settings.price_poll_interval_seconds),
        id="price_poll",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: run_daily_snapshot(get_session_factory(), get_market_data_provider()),
        CronTrigger(hour=settings.daily_snapshot_hour, minute=0),
        id="daily_snapshot",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
