import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.cache import cache
from app.core.config import get_settings
from app.models.registry import registry

settings = get_settings()
base_dir = Path(__file__).resolve().parent.parent
log_dir = base_dir / "logs"
log_dir.mkdir(exist_ok=True)

root_logger = logging.getLogger()
root_logger.setLevel(settings.log_level.upper())
root_logger.handlers.clear()

formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
root_logger.addHandler(stream_handler)

file_handler = RotatingFileHandler(
    log_dir / "translation_service.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger("translation_service.main")

app = FastAPI(title="Translation Service", version="1.0.0")

# Allows the React frontend (a different origin - e.g. localhost:5173 in dev)
# to call this API. Tighten allow_origins to your actual frontend domain(s)
# before deploying publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def on_startup():
    # Models and cache connection are set up ONCE here, not per request.
    registry.load_all()
    await cache.connect()
    logger.info("Translation service ready.")


@app.on_event("shutdown")
async def on_shutdown():
    await cache.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
