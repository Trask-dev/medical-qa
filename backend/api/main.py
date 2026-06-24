import logging
logging.basicConfig(level=logging.INFO, format='%(name)s | %(levelname)s | %(message)s')

from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import Settings
from api.routers import sessions, messages, safety_events

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="医疗智能问答系统",
    description="基于 Master-Agent 多智能体协作架构的医疗健康咨询 API",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/v1", tags=["Sessions"])
app.include_router(messages.router, prefix="/api/v1", tags=["Messages"])
app.include_router(safety_events.router, prefix="/api/v1", tags=["Safety"])


@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "database": "up",
            "milvus": "not_configured",
            "llm": "up",
        },
        "uptime_seconds": 0,
    }
