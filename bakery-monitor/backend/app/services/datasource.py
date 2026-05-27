"""数据源抽象层 —— 支持多种平台的数据采集插件。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class ProductSnapshot:
    """单次采集到的商品快照。"""

    product_name: str
    original_price: Decimal | None = None
    discount_price: Decimal | None = None
    discount_rate: str | None = None
    stock_status: str | None = None
    stock_quantity: int | None = None
    captured_at: datetime | None = None


class DataSource(ABC):
    """数据源基类 —— 各平台实现需继承此类。"""

    @abstractmethod
    async def search_stores(self, city: str, keyword: str) -> list[dict[str, object]]:
        """按城市和关键字搜索门店。

        Returns:
            [{"name": "Drunk Baker", "address": "...", "platform_store_id": "xxx"}, ...]
        """
        ...

    @abstractmethod
    async def fetch_products(
        self,
        store_id: str,
        keywords: str | None = None,
        keywords_mode: str = "discount",
    ) -> list[ProductSnapshot]:
        """抓取指定门店的商品列表。

        Args:
            store_id: 平台侧门店 ID。
            keywords: 过滤关键字（逗号分隔），为 None 时取折扣商品。
            keywords_mode: discount / keyword / all。

        Returns:
            商品快照列表。
        """
        ...


class MockDataSource(DataSource):
    """模拟数据源 —— 用于开发和演示。"""

    _MOCK_PRODUCTS = [
        ("法式可颂", 18.00, 9.90, "5.5折", "有货", 12),
        ("巧克力丹麦", 22.00, 11.00, "5折", "有货", 8),
        ("肉桂卷", 16.00, 8.00, "5折", "即将售罄", 2),
        ("碱水面包", 12.00, 12.00, "无折扣", "有货", 20),
        ("抹茶红豆吐司", 28.00, 14.00, "5折", "售罄", 0),
        ("全麦贝果", 10.00, 5.00, "5折", "有货", 15),
        ("蓝莓麦芬", 15.00, 7.50, "5折", "有货", 6),
        ("提拉米苏", 35.00, 17.50, "5折", "有货", 4),
    ]

    _MOCK_STORES = [
        {
            "name": "Drunk Baker",
            "address": "上海市静安区南京西路",
            "platform_store_id": "drunk-baker-sh",
        },
        {
            "name": "B&C Bakery",
            "address": "上海市徐汇区衡山路",
            "platform_store_id": "bc-bakery-sh",
        },
        {
            "name": "Pain Chaud",
            "address": "上海市黄浦区永嘉路",
            "platform_store_id": "pain-chaud-sh",
        },
    ]

    async def search_stores(self, city: str, keyword: str) -> list[dict[str, object]]:
        keyword_lower = keyword.lower()
        return [
            s
            for s in self._MOCK_STORES
            if keyword_lower in s["name"].lower() or keyword_lower in s["address"].lower()
        ]

    async def fetch_products(
        self,
        store_id: str,
        keywords: str | None = None,
        keywords_mode: str = "discount",
    ) -> list[ProductSnapshot]:
        import random

        now = datetime.utcnow()
        results: list[ProductSnapshot] = []

        for name, orig, disc, rate, stock, qty in self._MOCK_PRODUCTS:
            # 根据模式过滤
            if keywords_mode == "discount" and rate == "无折扣":
                continue
            if keywords_mode == "keyword" and keywords:
                kw_list = [k.strip() for k in keywords.split(",")]
                if not any(k in name for k in kw_list):
                    continue

            # 模拟价格和库存波动
            jitter = Decimal(str(round(random.uniform(-2, 2), 1)))
            qty_jitter = random.randint(-2, 2)

            results.append(
                ProductSnapshot(
                    product_name=name,
                    original_price=Decimal(str(orig)),
                    discount_price=Decimal(str(disc)) if disc else None,
                    discount_rate=rate,
                    stock_status="售罄" if max(0, qty + qty_jitter) == 0 else stock,
                    stock_quantity=max(0, qty + qty_jitter),
                    captured_at=now,
                )
            )

        return results
