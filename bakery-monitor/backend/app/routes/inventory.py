"""API 路由 —— 库存数据查询。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.models import ChangeOut, SnapshotOut

router = APIRouter(prefix="/api/inventory", tags=["库存数据"])


@router.get("/snapshots/{task_id}", response_model=list[SnapshotOut])
async def get_snapshots(
    request: Request,
    task_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SnapshotOut]:
    """获取指定任务的最新库存快照。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM inventory_snapshots
            WHERE task_id = $1
            ORDER BY captured_at DESC
            LIMIT $2
            """,
            task_id,
            limit,
        )

    return [
        SnapshotOut(
            id=str(r["id"]),
            task_id=str(r["task_id"]),
            product_name=r["product_name"],
            original_price=r["original_price"],
            discount_price=r["discount_price"],
            discount_rate=r["discount_rate"],
            stock_status=r["stock_status"],
            stock_quantity=r["stock_quantity"],
            has_changed=r["has_changed"],
            captured_at=r["captured_at"],
        )
        for r in rows
    ]


@router.get("/changes/{task_id}", response_model=list[ChangeOut])
async def get_changes(
    request: Request,
    task_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ChangeOut]:
    """获取指定任务的库存变化记录。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM inventory_changes
            WHERE task_id = $1
            ORDER BY detected_at DESC
            LIMIT $2
            """,
            task_id,
            limit,
        )

    return [
        ChangeOut(
            id=str(r["id"]),
            task_id=str(r["task_id"]),
            product_name=r["product_name"],
            change_type=r["change_type"],
            old_value=r["old_value"],
            new_value=r["new_value"],
            detail=r["detail"],
            detected_at=r["detected_at"],
        )
        for r in rows
    ]


@router.get("/latest/{task_id}", response_model=list[SnapshotOut])
async def get_latest_inventory(
    request: Request,
    task_id: UUID,
) -> list[SnapshotOut]:
    """获取指定任务最新一次的库存数据（去重按商品名）。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (product_name) *
            FROM inventory_snapshots
            WHERE task_id = $1
            ORDER BY product_name, captured_at DESC
            """,
            task_id,
        )

    return [
        SnapshotOut(
            id=str(r["id"]),
            task_id=str(r["task_id"]),
            product_name=r["product_name"],
            original_price=r["original_price"],
            discount_price=r["discount_price"],
            discount_rate=r["discount_rate"],
            stock_status=r["stock_status"],
            stock_quantity=r["stock_quantity"],
            has_changed=r["has_changed"],
            captured_at=r["captured_at"],
        )
        for r in rows
    ]
