"""API 路由 —— 监控任务 CRUD。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.models import TaskCreate, TaskListOut, TaskOut

router = APIRouter(prefix="/api/tasks", tags=["监控任务"])

CST = timezone(timedelta(hours=8))
DEFAULT_USER_ID = 1  # 简化：当前固定用户


@router.get("", response_model=TaskListOut)
async def list_tasks(request: Request) -> TaskListOut:
    """获取当前用户的所有监控任务。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        # 获取用户信息
        user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", DEFAULT_USER_ID)
        free_limit = user["max_stores"] if user else 1

        rows = await conn.fetch(
            """
            SELECT t.*, s.name AS store_name, c.name AS city_name
            FROM monitoring_tasks t
            JOIN stores s ON s.id = t.store_id
            JOIN cities c ON c.id = s.city_id
            WHERE t.user_id = $1 AND t.status != 'deleted'
            ORDER BY t.created_at DESC
            """,
            DEFAULT_USER_ID,
        )

        active_count = sum(1 for r in rows if r["status"] == "active")

    return TaskListOut(
        tasks=[
            TaskOut(
                id=str(r["id"]),
                user_id=r["user_id"],
                store_id=r["store_id"],
                store_name=r["store_name"],
                city_name=r["city_name"],
                keywords=r["keywords"],
                keywords_mode=r["keywords_mode"],
                notify_email=r["notify_email"],
                status=r["status"],
                last_run_at=r["last_run_at"],
                next_run_at=r["next_run_at"],
                check_interval_min=r["check_interval_min"],
                created_at=r["created_at"].replace(tzinfo=CST) if r["created_at"] else None,
            )
            for r in rows
        ],
        total=len(rows),
        free_limit=free_limit,
        used=active_count,
    )


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(request: Request, body: TaskCreate) -> TaskOut:
    """创建新的监控任务。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        # 检查免费额度
        user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", DEFAULT_USER_ID)
        free_limit = user["max_stores"] if user else 1

        active_count = await conn.fetchval(
            "SELECT COUNT(*) FROM monitoring_tasks WHERE user_id = $1 AND status = 'active'",
            DEFAULT_USER_ID,
        )

        if active_count >= free_limit:
            raise HTTPException(
                status_code=403,
                detail=f"免费版仅可监控 {free_limit} 家门店，请升级以监控更多门店",
            )

        # 验证门店存在
        store = await conn.fetchrow("SELECT * FROM stores WHERE id = $1", body.store_id)
        if not store:
            raise HTTPException(status_code=404, detail="门店不存在")

        now = datetime.now(CST)
        row = await conn.fetchrow(
            """
            INSERT INTO monitoring_tasks
                (user_id, store_id, keywords, notify_email, next_run_at, check_interval_min)
            VALUES ($1, $2, $3, $4, $5, 30)
            RETURNING *
            """,
            DEFAULT_USER_ID,
            body.store_id,
            body.keywords,
            body.notify_email,
            now,  # 创建后立即可执行
        )

        # 关联查询
        row2 = await conn.fetchrow(
            """
            SELECT t.*, s.name AS store_name, c.name AS city_name
            FROM monitoring_tasks t
            JOIN stores s ON s.id = t.store_id
            JOIN cities c ON c.id = s.city_id
            WHERE t.id = $1
            """,
            row["id"],
        )

    return TaskOut(
        id=str(row2["id"]),
        user_id=row2["user_id"],
        store_id=row2["store_id"],
        store_name=row2["store_name"],
        city_name=row2["city_name"],
        keywords=row2["keywords"],
        keywords_mode=row2["keywords_mode"],
        notify_email=row2["notify_email"],
        status=row2["status"],
        last_run_at=row2["last_run_at"],
        next_run_at=row2["next_run_at"],
        check_interval_min=row2["check_interval_min"],
        created_at=row2["created_at"].replace(tzinfo=CST) if row2["created_at"] else None,
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(request: Request, task_id: UUID) -> TaskOut:
    """获取单个任务详情。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT t.*, s.name AS store_name, c.name AS city_name
            FROM monitoring_tasks t
            JOIN stores s ON s.id = t.store_id
            JOIN cities c ON c.id = s.city_id
            WHERE t.id = $1 AND t.user_id = $2
            """,
            task_id,
            DEFAULT_USER_ID,
        )
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")

    return TaskOut(
        id=str(row["id"]),
        user_id=row["user_id"],
        store_id=row["store_id"],
        store_name=row["store_name"],
        city_name=row["city_name"],
        keywords=row["keywords"],
        keywords_mode=row["keywords_mode"],
        notify_email=row["notify_email"],
        status=row["status"],
        last_run_at=row["last_run_at"],
        next_run_at=row["next_run_at"],
        check_interval_min=row["check_interval_min"],
        created_at=row["created_at"].replace(tzinfo=CST) if row["created_at"] else None,
    )


@router.patch("/{task_id}/status")
async def update_task_status(
    request: Request,
    task_id: UUID,
    status: str = "active",
) -> dict[str, str]:
    """更新任务状态：active / paused / deleted。"""
    if status not in ("active", "paused", "deleted"):
        raise HTTPException(status_code=400, detail="无效的状态值")

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE monitoring_tasks SET status = $1, updated_at = now() WHERE id = $2 AND user_id = $3",
            status,
            task_id,
            DEFAULT_USER_ID,
        )
        # 检查是否更新成功
        updated = await conn.fetchval(
            "SELECT id FROM monitoring_tasks WHERE id = $1", task_id
        )
        if not updated:
            raise HTTPException(status_code=404, detail="任务不存在")

    return {"status": status}
