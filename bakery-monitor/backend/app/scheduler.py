"""定时调度器 —— 使用 APScheduler 管理监控任务轮询。"""

from __future__ import annotations

import logging

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.datasource import DataSource
from app.services.monitor import run_task

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler(pool: asyncpg.Pool, datasource: DataSource) -> None:
    """启动调度器，每分钟扫描到期任务并执行。"""

    async def tick() -> None:
        """扫描所有到期待执行的活跃任务。"""
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id FROM monitoring_tasks
                    WHERE status = 'active'
                      AND (next_run_at IS NULL OR next_run_at <= now())
                    LIMIT 20
                    """
                )
            for row in rows:
                task_id = row["id"]
                logger.info("调度执行: %s", task_id)
                try:
                    await run_task(pool, task_id, datasource)
                except Exception as e:
                    logger.error("调度异常 task=%s: %s", task_id, e)
        except Exception as e:
            logger.error("调度器扫描异常: %s", e)

    # 每分钟触发一次
    scheduler.add_job(tick, "interval", minutes=1, id="tick", replace_existing=True)
    scheduler.start()
    logger.info("调度器已启动 (每 1 分钟扫描)")


def stop_scheduler() -> None:
    """停止调度器。"""
    scheduler.shutdown(wait=False)
    logger.info("调度器已停止")
