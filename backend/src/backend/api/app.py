from fastapi import APIRouter, FastAPI

from backend.api.errors import register_error_handlers
from backend.api.routes import assets, auth, positions, transactions

app = FastAPI(
    title="Investment Tracker API",
    description="Personal, single-user investment tracking backend. See docs/openapi/openapi.yaml for the full contract.",
    version="0.1.0",
)

register_error_handlers(app)

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(assets.router)
api.include_router(transactions.router)
api.include_router(positions.router)


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)
