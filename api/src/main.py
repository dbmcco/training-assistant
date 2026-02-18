from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.routers.dashboard import router as dashboard_router
from src.routers.races import router as races_router
from src.routers.plan import router as plan_router
from src.routers.activities import router as activities_router
from src.routers.athlete import router as athlete_router
from src.routers.readiness import router as readiness_router

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


@app.get("/health")
async def health():
    return {"status": "ok"}
