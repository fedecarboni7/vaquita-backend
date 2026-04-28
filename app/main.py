from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers.accounts import router as accounts_router
from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.chat import router as chat_router
from app.routers.expenses import router as expenses_router
from app.routers.settings import router as settings_router
from app.routers.transcribe import router as transcribe_router
from app.routers.stats import router as stats_router
from app.routers.subcategories import router as subcategories_router
from app.routers.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Expenses Tracker API",
    description="AI-powered expenses tracker backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts_router)
app.include_router(auth_router)
app.include_router(categories_router)
app.include_router(subcategories_router)
app.include_router(chat_router)
app.include_router(transcribe_router)
app.include_router(expenses_router)
app.include_router(settings_router)
app.include_router(stats_router)
app.include_router(users_router)


@app.get("/health")
async def health_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}
