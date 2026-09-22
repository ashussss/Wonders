"""ShowUp.ai — slim FastAPI app factory. Routes live in routes_*.py."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import CORS_ORIGINS
from database import client, scheduler
from routes_webinars import router as webinars_router, limiter as web_limiter
from routes_auth import router as auth_router
from routes_settings import router as settings_router
from routes_delivery import router as delivery_router, scheduler_tick

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("showup")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler.add_job(scheduler_tick, "interval", minutes=1, id="touch-tick", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        client.close()
        logger.info("Scheduler stopped")


app = FastAPI(title="ShowUp.ai API", lifespan=lifespan)
app.state.limiter = web_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(webinars_router)
app.include_router(settings_router)
app.include_router(delivery_router)


@app.get("/api/")
async def root():
    return {"app": "ShowUp.ai", "ok": True}


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    """Health check endpoint — supports GET and HEAD for UptimeRobot."""
    return {"status": "ok", "service": "showup-ai"}
