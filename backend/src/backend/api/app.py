from fastapi import FastAPI

app = FastAPI(
    title="Investment Tracker API",
    description="Personal, single-user investment tracking backend. See docs/openapi/openapi.yaml for the full contract.",
    version="0.1.0",
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
