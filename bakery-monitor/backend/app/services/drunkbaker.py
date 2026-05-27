"""Drunk Baker 真实数据源 —— 对接 51hchc.com 平台 API。

数据来源：
- nice-api.51hchc.com/menu/service  → 全量商品菜单（名称、价格、分类）
- nice-api.51hchc.com/menu/branch-product-amount/{branchId} → 真实库存数量（主数据源）
- nice-api.51hchc.com/menu/product-status/{branchId} → 商品生命周期状态（SOLD_OUT/DISABLED）
- pay.51hchc.com/wxa/order/coupons/v2/ → 折扣券（折扣力度、有效期，需sessionKey）

关键发现：menu/service 返回所有商品 status=ONSALE（仅代表列入菜单），
真正库存由 branch-product-amount 接口提供（amount 字段）。
当 amount=0 时商品在菜单中显示但不可购买（即售罄）。
"""

from __future__ import annotations

import asyncio
import logging
import zoneinfo
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx

from app.services.datasource import DataSource, ProductSnapshot

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 北京时间
CST = zoneinfo.ZoneInfo("Asia/Shanghai")

# ── API 基础配置 ──

MENU_API = "https://nice-api.51hchc.com/menu/service"
COUPON_API = "https://pay.51hchc.com/wxa/order/coupons/v2/{branch_id}/{timestamp}"

# Drunk Baker 的 hqId
DRUNK_BAKER_HQ_ID = 14434

# 请求头（模拟微信小程序环境）
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 26_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Mobile/15E148 MicroMessenger/8.0.73"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class DrunkBakerDataSource(DataSource):
    """Drunk Baker (51hchc 平台) 数据采集器。

    无需登录即可访问菜单和优惠券 API。
    通过菜单 API 获取完整商品列表，通过优惠券 API 获取折扣信息，
    合并两者得出：商品名称、原价、折扣价、折扣率、库存状态。
    """

    def __init__(
        self,
        hq_id: int = DRUNK_BAKER_HQ_ID,
        timeout: float = 30.0,
    ) -> None:
        self.hq_id = hq_id
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── 实现 DataSource 接口 ──

    async def search_stores(self, city: str, keyword: str) -> list[dict[str, object]]:
        """搜索门店 —— 51hchc 平台暂未暴露公开的门店搜索 API。

        返回内置的已知门店列表，通过城市和关键字过滤。
        """
        stores = await self._get_all_branches()
        keyword_lower = keyword.lower()
        return [
            {
                "name": s["name"],
                "address": s["address"],
                "platform_store_id": str(s["branch_id"]),
            }
            for s in stores
            if keyword_lower in s["name"].lower() or keyword_lower in s.get("address", "").lower()
        ]

    async def fetch_products(
        self,
        store_id: str,
        keywords: str | None = None,
        keywords_mode: str = "discount",
    ) -> list[ProductSnapshot]:
        """抓取指定门店的商品列表。

        流程：
        1. 调菜单 API 获取全量商品（名称、价格、状态）
        2. 可选：调优惠券 API 获取折扣信息（需有效 sessionKey）
        3. 返回所有在售商品，折扣模式时尝试附加折扣价
        """
        branch_id = int(store_id)
        now = datetime.now(CST)

        # 并发：菜单 + 真实库存 + 优惠券 + 产品状态
        menu_task = self._fetch_menu(branch_id)
        amount_task = self._fetch_branch_product_amount(branch_id)
        coupon_task = self._fetch_coupons(branch_id)
        status_task = self._fetch_product_status(branch_id)
        menu_data, amount_map, coupon_data, status_map = await asyncio.gather(
            menu_task, amount_task, coupon_task, status_task
        )

        # 构建折扣映射
        discount_map: dict[int, dict[str, object]] = {}
        if coupon_data:
            for coupon in (
                coupon_data.get("ableCoupons", [])
                + coupon_data.get("unableCoupons", [])
            ):
                for pid in coupon.get("productIdList", []):
                    if pid not in discount_map:
                        discount_map[pid] = {
                            "name": coupon.get("name", ""),
                            "type": coupon.get("type", ""),
                            "val": coupon.get("val", 1.0),
                        }

        # 解析菜单
        results: list[ProductSnapshot] = []
        categories: list[dict[str, object]] = menu_data.get("data", []) if menu_data else []

        # 关键字过滤
        kw_list: list[str] = []
        if keywords and keywords_mode == "keyword":
            kw_list = [k.strip() for k in keywords.split(",")]

        for cat in categories:
            for product in cat.get("products", []):
                pid = product.get("id", 0)
                product_name = str(product.get("name", ""))
                original_price = float(product.get("price", 0))
                status = str(product.get("status", "ONSALE"))
                discountable = bool(product.get("discountable", False))

                # 跳过非实体商品（提示页、公告等）
                if original_price == 0 and status == "ONSALE":
                    continue

                # 按模式过滤
                if keywords_mode == "keyword" and kw_list:
                    if not any(k in product_name for k in kw_list):
                        continue
                elif keywords_mode == "discount":
                    # 折扣模式：优先看优惠券 API 折扣，否则看 discountable 标记
                    if not discount_map and not discountable:
                        continue
                    if discount_map and pid not in discount_map:
                        continue

                # 折扣信息
                disc_info = discount_map.get(pid)
                if disc_info:
                    disc_type = str(disc_info["type"])
                    disc_val = float(str(disc_info["val"]))
                    if disc_type == "PERCENT":
                        discount_rate = f"{(disc_val * 10):.1f}折"
                        discount_price = Decimal(str(original_price)) * Decimal(str(disc_val))
                    else:
                        discount_rate = f"减{disc_val}元"
                        discount_price = Decimal(str(original_price)) - Decimal(str(disc_val))
                else:
                    discount_rate = "原价"
                    discount_price = Decimal(str(original_price))

                # 库存状态：branch-product-amount 为主数据源
                amount_info = amount_map.get(pid)
                life_status = status_map.get(pid, "ONSALE")

                if life_status == "DISABLED" or life_status == "OFF_SHELF":
                    stock_status = "已下架"
                    stock_qty = 0
                elif life_status == "SOLD_OUT":
                    stock_status = "售罄"
                    stock_qty = 0
                elif amount_info is None:
                    stock_status = "有货"
                    stock_qty = -1
                elif amount_info["amount"] <= 0:
                    stock_status = "售罄"
                    stock_qty = amount_info["amount"]
                else:
                    stock_status = "有货"
                    stock_qty = amount_info["amount"]

                results.append(
                    ProductSnapshot(
                        product_name=product_name,
                        original_price=Decimal(str(original_price)),
                        discount_price=discount_price,
                        discount_rate=discount_rate,
                        stock_status=stock_status,
                        stock_quantity=stock_qty,
                        captured_at=now,
                    )
                )

        sold_count = sum(1 for r in results if r.stock_status == "售罄")
        avail_count = sum(1 for r in results if r.stock_status == "有货")
        total_all = len(results)
        logger.info(
            "采集完成 branch=%s: 全量%d件, 有货%d件, 售罄%d件, 有券=%s",
            branch_id,
            total_all,
            avail_count,
            sold_count,
            bool(discount_map),
        )
        return results

    # ── 底层 API 调用 ──

    async def _fetch_branch_product_amount(self, branch_id: int) -> dict[int, dict[str, int]]:
        """获取门店商品真实库存数量（主数据源）。

        返回 {productId: {amount, total_amount, safety_amount}}
        当 amount <= 0 时商品虽在菜单中但不可购买。
        """
        client = await self._ensure_client()
        url = f"https://nice-api.51hchc.com/menu/branch-product-amount/{branch_id}"

        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                logger.warning("branch-product-amount API 异常: %s", data)
                return {}
            return {
                item["productId"]: {
                    "amount": item.get("amount", 0),
                    "total_amount": item.get("total_amount", 0),
                    "safety_amount": item.get("safety_amount", 0),
                }
                for item in data.get("data", [])
            }
        except Exception as e:
            logger.error("branch-product-amount API 请求失败 branch=%s: %s", branch_id, e)
            return {}

    async def _fetch_product_status(self, branch_id: int) -> dict[int, str]:
        """获取门店各商品真实状态（SOLD_OUT / DISABLED / ONSALE）。"""
        client = await self._ensure_client()
        url = f"https://nice-api.51hchc.com/menu/product-status/{branch_id}"

        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                logger.warning("product-status API 异常: %s", data)
                return {}
            # 返回 {productId: status}
            return {item["productId"]: item["status"] for item in data.get("data", [])}
        except Exception as e:
            logger.error("product-status API 请求失败 branch=%s: %s", branch_id, e)
            return {}

    async def _fetch_menu(self, branch_id: int) -> dict[str, object]:
        """获取门店菜单（全量商品）。"""
        client = await self._ensure_client()
        url = f"{MENU_API}?hqId={self.hq_id}&branchId={branch_id}&platform=APP_SELF_SERVICE"

        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0" and data.get("status") != "0":
                logger.warning("菜单 API 返回异常: %s", data)
                return {}
            return data
        except Exception as e:
            logger.error("菜单 API 请求失败 branch=%s: %s", branch_id, e)
            return {}

    async def _fetch_coupons(self, branch_id: int) -> dict[str, object] | None:
        """获取门店优惠券列表。"""
        client = await self._ensure_client()
        ts = datetime.now(CST).strftime("%Y%m%d%H%M%S%f")[:17] + "000"
        url = COUPON_API.format(branch_id=branch_id, timestamp=ts)
        params = {
            "hqId": self.hq_id,
            "branchId": branch_id,
            "platform": "WXA_SCAN",
        }

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                logger.warning("优惠券 API 返回异常: %s", data)
                return None
            return data
        except Exception as e:
            logger.error("优惠券 API 请求失败 branch=%s: %s", branch_id, e)
            return None

    # ── 门店发现 ──

    async def _get_all_branches(self) -> list[dict[str, str | int]]:
        """获取已知的 Drunk Baker 门店列表。

        TODO: 51hchc 未暴露公开的门店列表 API。
        当前使用手动维护的列表，可在此扩展。
        """
        return [
            {
                "branch_id": 30789,
                "name": "Drunk Baker",
                "address": "上海大宁音乐广场店",
            },
        ]

    async def discover_branches(self) -> list[dict[str, str | int]]:
        """发现新门店 —— 尝试从菜单 API 反查。

        通过已知的分店模式探测门店是否存在。
        """
        discovered: list[dict[str, str | int]] = []
        known = await self._get_all_branches()

        # 先验证已知门店
        for store in known:
            menu = await self._fetch_menu(int(store["branch_id"]))
            if menu and menu.get("data"):
                discovered.append(store)
                logger.info("门店有效: %s (branchId=%s)", store["name"], store["branch_id"])

        return discovered
