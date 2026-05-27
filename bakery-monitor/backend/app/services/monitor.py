"""监控引擎 —— 执行库存采集、变更检测、通知发送。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import asyncpg

from app.services.datasource import DataSource, ProductSnapshot
from app.services.notifier import build_inventory_change_email, send_email

logger = logging.getLogger(__name__)

# 北京时间
CST = timezone(timedelta(hours=8))


async def run_task(pool: asyncpg.Pool, task_id: str, datasource: DataSource) -> None:
    """执行一次监控采集。

    Args:
        pool: 数据库连接池。
        task_id: 监控任务 UUID。
        datasource: 数据采集插件。
    """
    now = datetime.now(CST)

    async with pool.acquire() as conn:
        # 1. 加载任务信息
        task = await conn.fetchrow(
            """
            SELECT t.*, s.name AS store_name, s.platform_store_id
            FROM monitoring_tasks t
            JOIN stores s ON s.id = t.store_id
            WHERE t.id = $1 AND t.status = 'active'
            """,
            task_id,
        )
        if not task:
            logger.warning("任务 %s 不存在或已暂停", task_id)
            return

        task_dict = dict(task)

        # 2. 采集最新库存数据
        try:
            products = await datasource.fetch_products(
                store_id=task_dict["platform_store_id"],
                keywords=task_dict["keywords"],
                keywords_mode=task_dict["keywords_mode"],
            )
        except Exception as e:
            logger.error("采集失败 task=%s: %s", task_id, e)
            await conn.execute(
                "UPDATE monitoring_tasks SET last_run_at = $1 WHERE id = $2", now, task_id
            )
            return

        if not products:
            logger.info("任务 %s 本次无数据", task_id)
            await conn.execute(
                "UPDATE monitoring_tasks SET last_run_at = $1, next_run_at = $2 WHERE id = $3",
                now,
                now + timedelta(minutes=task_dict["check_interval_min"]),
                task_id,
            )
            return

        # 3. 获取上一次快照用于对比
        prev_products = await conn.fetch(
            """
            SELECT DISTINCT ON (product_name) product_name, discount_price, stock_status, stock_quantity
            FROM inventory_snapshots
            WHERE task_id = $1
            ORDER BY product_name, captured_at DESC
            """,
            task_id,
        )
        prev_map: dict[str, dict[str, object]] = {r["product_name"]: dict(r) for r in prev_products}

        # 4. 批量插入快照 + 检测变化
        changes: list[dict[str, str]] = []
        for p in products:
            await conn.execute(
                """
                INSERT INTO inventory_snapshots (task_id, product_name, original_price,
                    discount_price, discount_rate, stock_status, stock_quantity, has_changed)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                task_id,
                p.product_name,
                p.original_price,
                p.discount_price,
                p.discount_rate,
                p.stock_status,
                p.stock_quantity,
                False,  # 先标记无变化，检测到变化再更新
            )

            prev = prev_map.get(p.product_name)
            change_detail = _detect_change(prev, p)
            if change_detail:
                # 更新快照标记
                await conn.execute(
                    "UPDATE inventory_snapshots SET has_changed = true WHERE task_id = $1 AND product_name = $2 AND captured_at = $3",
                    task_id,
                    p.product_name,
                    now,
                )
                # 插入变化记录
                await conn.execute(
                    """
                    INSERT INTO inventory_changes (task_id, product_name, change_type, old_value, new_value, detail, detected_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    task_id,
                    p.product_name,
                    change_detail["change_type"],
                    change_detail["old_value"],
                    change_detail["new_value"],
                    change_detail["detail"],
                    now,
                )
                changes.append(
                    {
                        "product_name": p.product_name,
                        "change_type": change_detail["change_type"],
                        "detail": change_detail["detail"] or "",
                    }
                )

        # 5. 更新任务状态
        next_run = now + timedelta(minutes=task_dict["check_interval_min"])
        await conn.execute(
            "UPDATE monitoring_tasks SET last_run_at = $1, next_run_at = $2, updated_at = $3 WHERE id = $4",
            now,
            next_run,
            now,
            task_id,
        )

        # 6. 发送通知（如有变化）
        if changes and task_dict["notify_email"]:
            store_name = task_dict["store_name"]
            body = build_inventory_change_email(store_name, changes, now.strftime("%Y-%m-%d %H:%M"))
            sent = await send_email(
                to=task_dict["notify_email"],
                subject=f"🍞 {store_name} 库存变化 - {len(changes)}项变动",
                body_html=body,
            )
            # 记录通知
            for change in changes:
                await conn.execute(
                    """
                    INSERT INTO notifications (task_id, channel, recipient, content, status, sent_at)
                    VALUES ($1, 'email', $2, $3, $4, $5)
                    """,
                    task_id,
                    task_dict["notify_email"],
                    f"{change['product_name']}: {change['change_type']} - {change['detail']}",
                    "sent" if sent else "failed",
                    now if sent else None,
                )

        logger.info("任务 %s 完成: %d 商品, %d 变化", task_id, len(products), len(changes))


def _detect_change(
    prev: dict[str, object] | None, curr: ProductSnapshot
) -> dict[str, str] | None:
    """对比新旧快照，检测变化。"""

    if prev is None:
        return {
            "change_type": "new",
            "old_value": None,
            "new_value": curr.product_name,
            "detail": f"新品上架: {curr.product_name}",
        }

    # 检查状态变化（有货 → 售罄）
    prev_status = str(prev.get("stock_status", ""))
    curr_status = str(curr.stock_status or "")

    if prev_status != "售罄" and curr_status == "售罄":
        return {
            "change_type": "sold_out",
            "old_value": prev_status,
            "new_value": curr_status,
            "detail": f"{curr.product_name} 已售罄",
        }
    if prev_status == "售罄" and curr_status != "售罄":
        return {
            "change_type": "restocked",
            "old_value": prev_status,
            "new_value": curr_status,
            "detail": f"{curr.product_name} 已补货 (当前: {curr_status})",
        }

    # 检查价格变化
    prev_price = prev.get("discount_price")
    curr_price = curr.discount_price
    if prev_price is not None and curr_price is not None and prev_price != curr_price:
        if float(str(curr_price)) < float(str(prev_price)):
            return {
                "change_type": "price_down",
                "old_value": str(prev_price),
                "new_value": str(curr_price),
                "detail": f"{curr.product_name}: ¥{prev_price} → ¥{curr_price}",
            }
        else:
            return {
                "change_type": "price_up",
                "old_value": str(prev_price),
                "new_value": str(curr_price),
                "detail": f"{curr.product_name}: ¥{prev_price} → ¥{curr_price}",
            }

    # 检查库存变化
    prev_qty = prev.get("stock_quantity")
    curr_qty = curr.stock_quantity
    if prev_qty is not None and curr_qty is not None and prev_qty != curr_qty:
        return {
            "change_type": "stock_change",
            "old_value": str(prev_qty),
            "new_value": str(curr_qty),
            "detail": f"{curr.product_name}: 库存 {prev_qty} → {curr_qty}",
        }

    return None
