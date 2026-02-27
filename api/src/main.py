from datetime import date, timedelta
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from src.config import settings
from src.db.connection import async_session, check_db_ready
from src.db.models import GarminActivity, GarminDailySummary, PlannedWorkout
from src.routers.dashboard import router as dashboard_router
from src.routers.races import router as races_router
from src.routers.plan import router as plan_router
from src.routers.activities import router as activities_router
from src.routers.athlete import router as athlete_router
from src.routers.readiness import router as readiness_router
from src.routers.briefings import router as briefings_router
from src.routers.chat import router as chat_router
from src.routers.recommendations import router as recommendations_router

app = FastAPI(title="Training Assistant API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(dashboard_router)
app.include_router(races_router)
app.include_router(plan_router)
app.include_router(activities_router)
app.include_router(athlete_router)
app.include_router(readiness_router)
app.include_router(briefings_router)
app.include_router(chat_router)
app.include_router(recommendations_router)


@app.on_event("startup")
async def warm_startup_queries() -> None:
    """Prime DB pool and query plans so first page load isn't cold/slow."""
    started = perf_counter()
    warmup_error: str | None = None
    try:
        async with async_session() as db:
            await db.execute(
                select(GarminDailySummary.id)
                .order_by(GarminDailySummary.calendar_date.desc())
                .limit(1)
            )
            await db.execute(
                select(GarminActivity.id)
                .order_by(GarminActivity.start_time.desc())
                .limit(1)
            )
            await db.execute(
                select(PlannedWorkout.id)
                .where(PlannedWorkout.date >= date.today() - timedelta(days=1))
                .order_by(PlannedWorkout.date.asc())
                .limit(3)
            )
    except Exception as exc:  # pragma: no cover - defensive warmup fallback
        warmup_error = f"{type(exc).__name__}: {exc}"

    app.state.startup_warmup = {
        "ok": warmup_error is None,
        "error": warmup_error,
        "duration_ms": round((perf_counter() - started) * 1000, 1),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    db_ok = await check_db_ready()
    warmup = getattr(app.state, "startup_warmup", None)
    warmup_ok = bool(warmup is None or warmup.get("ok"))

    payload = {
        "status": "ok" if db_ok and warmup_ok else "degraded",
        "db_ok": db_ok,
        "warmup_ok": warmup_ok,
        "warmup": warmup,
    }

    if not db_ok or not warmup_ok:
        raise HTTPException(status_code=503, detail=payload)
    return payload
