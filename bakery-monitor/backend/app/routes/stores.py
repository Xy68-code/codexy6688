"""API 路由 —— 门店查询。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.models import StoreOut

router = APIRouter(prefix="/api/stores", tags=["门店"])


@router.get("", response_model=list[StoreOut])
async def search_stores(
    request: Request,
    city_id: int = Query(..., description="城市 ID"),
    keyword: str = Query(default="", description="门店名称或地址关键字"),
) -> list[StoreOut]:
    """按城市和关键字搜索门店。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        query = """
            SELECT id, city_id, name, address, platform, status
            FROM stores
            WHERE city_id = $1 AND status = 'active'
        """
        params: list[object] = [city_id]
        idx = 2

        if keyword:
            query += f" AND (name ILIKE ${idx} OR address ILIKE ${idx})"
            params.append(f"%{keyword}%")
            idx += 1

        query += " ORDER BY name LIMIT 50"
        rows = await conn.fetch(query, *params)

    return [
        StoreOut(
            id=r["id"],
            city_id=r["city_id"],
            name=r["name"],
            address=r["address"],
            platform=r["platform"],
            status=r["status"],
        )
        for r in rows
    ]
