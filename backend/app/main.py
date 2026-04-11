from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import asyncio

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.scheduler import start_scheduler, shutdown_scheduler
from app.seed_prompts import seed_default_prompts
from app.services.analysis_queue import worker as queue_worker
from app.routers import companies, reports, analyses, scheduler
from app.routers import prompts as prompts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: DB 테이블 생성 + 기본 프롬프트 시딩 + 데이터 디렉터리 확보 + 스케줄러 + 큐 워커
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_default_prompts(db)
    finally:
        db.close()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    start_scheduler()
    worker_task = asyncio.create_task(queue_worker())
    yield
    # 종료: 스케줄러 정지 + 큐 워커 취소
    worker_task.cancel()
    shutdown_scheduler()


app = FastAPI(
    title="기업 DART 사업보고서 분석",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(reports.router)
app.include_router(analyses.router)
app.include_router(scheduler.router)
app.include_router(prompts_router.router)
