"""面包店库存监控后端 —— FastAPI 入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, init_db
from app.routes import cities, inventory, stores, tasks
from app.scheduler import start_scheduler, stop_scheduler
from app.services.datasource import MockDataSource
from app.services.drunkbaker import DrunkBakerDataSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 DB 和调度器，关闭时清理。"""
    logger.info("正在启动...")
    await init_db(app)

    # 使用 Mock 数据源（生产环境替换为真实采集器）
    # 使用真实 Drunk Baker 数据源（生产环境）
    # datasource = MockDataSource()  # 开发/演示用
    datasource = DrunkBakerDataSource()
    start_scheduler(app.state.db_pool, datasource)
    logger.info("启动完成")

    yield

    logger.info("正在关闭...")
    stop_scheduler()
    await close_db(app)
    logger.info("已关闭")


app = FastAPI(
    title="面包店库存监控 API",
    description="监控指定面包店门店的折扣商品库存变化，支持邮件通知",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(cities.router)
app.include_router(stores.router)
app.include_router(tasks.router)
app.include_router(inventory.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok", "version": "0.1.0"}
