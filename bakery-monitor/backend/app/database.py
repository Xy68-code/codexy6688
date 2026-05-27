"""数据库连接池管理。"""

from __future__ import annotations

import asyncpg
from fastapi import FastAPI

from app.config import settings

_pool: asyncpg.Pool | None = None


async def init_db(app: FastAPI) -> None:
    """初始化数据库连接池，挂载到 app.state。"""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    app.state.db_pool = _pool


async def close_db(app: FastAPI) -> None:
    """关闭数据库连接池。"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """获取数据库连接池（同步获取引用，用于依赖注入）。"""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool
