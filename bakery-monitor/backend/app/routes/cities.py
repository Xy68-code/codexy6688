"""API 路由 —— 城市查询。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models import CityOut

router = APIRouter(prefix="/api/cities", tags=["城市"])


@router.get("", response_model=list[CityOut])
async def list_cities(request: Request) -> list[CityOut]:
    """获取所有城市列表。"""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, code FROM cities ORDER BY id")
    return [CityOut(id=r["id"], name=r["name"], code=r["code"]) for r in rows]
