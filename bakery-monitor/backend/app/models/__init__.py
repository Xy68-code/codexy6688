"""Pydantic 响应模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ── 城市 ──

class CityOut(BaseModel):
    id: int
    name: str
    code: str | None = None


# ── 门店 ──

class StoreOut(BaseModel):
    id: int
    city_id: int
    name: str
    address: str | None = None
    platform: str
    status: str


# ── 监控任务 ──

class TaskCreate(BaseModel):
    city_id: int
    store_id: int
    keywords: str | None = Field(default=None, description="商品关键字，逗号分隔")
    notify_email: str | None = None


class TaskOut(BaseModel):
    id: str
    user_id: int
    store_id: int
    store_name: str = ""
    city_name: str = ""
    keywords: str | None = None
    keywords_mode: str
    notify_email: str | None = None
    status: str
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    check_interval_min: int
    created_at: datetime


class TaskListOut(BaseModel):
    tasks: list[TaskOut]
    total: int
    free_limit: int
    used: int


# ── 库存快照 ──

class SnapshotOut(BaseModel):
    id: str
    task_id: str
    product_name: str
    original_price: Decimal | None = None
    discount_price: Decimal | None = None
    discount_rate: str | None = None
    stock_status: str | None = None
    stock_quantity: int | None = None
    has_changed: bool
    captured_at: datetime


# ── 库存变化 ──

class ChangeOut(BaseModel):
    id: str
    task_id: str
    product_name: str
    change_type: str
    old_value: str | None = None
    new_value: str | None = None
    detail: str | None = None
    detected_at: datetime


# ── 通用 ──

class APIResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: object | None = None


class PaginatedResponse(BaseModel):
    items: list[object]
    total: int
    page: int = 1
    page_size: int = 20
