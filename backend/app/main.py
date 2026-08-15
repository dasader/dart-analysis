from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import asyncio

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.migrate import run as run_migrations
from app.scheduler import start_scheduler, shutdown_scheduler
from app.seed_prompts import seed_default_prompts
from app.services.analysis_queue import requeue_orphans, worker as queue_worker
from app.services.dart_client import aclose_http
from app.routers import companies, reports, analyses, scheduler, admin, batches, backup
from app.routers import app_settings as app_settings_router
from app.routers import technologies as technologies_router
from app.routers import prompts as prompts_router
from app.routers import tags as tags_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: DB 테이블 생성 + 기본 프롬프트 시딩 + 데이터 디렉터리 확보 + 스케줄러 + 큐 워커
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)   # create_all은 기존 테이블에 컬럼을 추가하지 못한다
    db = SessionLocal()
    try:
        seed_default_prompts(db)
    finally:
        db.close()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    # 재시작으로 in-memory 큐가 유실된 pending 분석을 다시 투입 (진행 중 batch는 폴링이 이어받음)
    requeue_orphans()
    start_scheduler()
    worker_task = asyncio.create_task(queue_worker())
    yield
    # 종료: 스케줄러 정지 + 큐 워커 취소 (취소 완료까지 대기)
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    shutdown_scheduler()
    await aclose_http()


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
app.include_router(tags_router.router)
app.include_router(admin.router)
app.include_router(batches.router)
app.include_router(app_settings_router.router)
app.include_router(technologies_router.router)
app.include_router(backup.router)
