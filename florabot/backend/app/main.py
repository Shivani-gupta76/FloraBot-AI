from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.analysis import finish_interrupted_analyses
from app.config import get_settings
from app.db import Base, engine
from app.devices import build_device
from app.disease import build_classifier
from app.ratelimit import RateLimiter
from app.routes import ai, analyses, care, connect, device, hardware
from app.vision import build_provider


class RevalidatedStaticFiles(StaticFiles):
    """Static files that browsers re-check (cheaply, by ETag) on every load."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(engine)
    finish_interrupted_analyses()
    app.state.vision = build_provider(settings)
    app.state.device = build_device(settings)
    app.state.disease = build_classifier(settings)
    app.state.rate_limiters = {
        name: RateLimiter(settings.rate_limit_per_minute) for name in ("analyses", "care")
    }
    await app.state.device.start()
    try:
        yield
    finally:
        await app.state.device.stop()


app = FastAPI(title="FloraBOT AI", lifespan=lifespan)
for module in (ai, analyses, care, connect, device, hardware):
    app.include_router(module.router)
app.mount("/", RevalidatedStaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
