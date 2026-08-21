import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_error_handlers
from backend.api.routes import (
    assets,
    auth,
    corporate_actions,
    imports,
    portfolio,
    positions,
    transactions,
)
from backend.api.websocket import broadcaster
from backend.api.websocket import router as websocket_router
from backend.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    broadcaster.set_loop(asyncio.get_running_loop())
    scheduler = None

    if settings.enable_jobs:
        from backend.application.startup_catchup import run_startup_catchup
        from backend.infrastructure.jobs.scheduler import build_scheduler
        from backend.infrastructure.market_data.brapi_provider import today_isoformat
        from backend.infrastructure.market_data.factory import get_market_data_provider
        from backend.infrastructure.persistence.database import get_session_factory

        def catchup() -> None:
            try:
                run_startup_catchup(
                    get_session_factory(), get_market_data_provider(), today_isoformat()
                )
            except Exception:
                logger.exception("Startup snapshot catch-up failed — will retry on next start.")

        # Catch-up must not block the API from serving requests (architecture §4.4).
        threading.Thread(target=catchup, name="startup-catchup", daemon=True).start()

        scheduler = build_scheduler()
        scheduler.start()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Investment Tracker API",
    description="Personal, single-user investment tracking backend. See docs/openapi/openapi.yaml for the full contract.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

register_error_handlers(app)

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(assets.router)
api.include_router(transactions.router)
api.include_router(positions.router)
api.include_router(portfolio.router)
api.include_router(imports.router)
api.include_router(corporate_actions.router)


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)
app.include_router(websocket_router)
