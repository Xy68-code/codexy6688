"""
商品监控核心模块

负责：
- 加载商品配置
- 定时检查价格/库存
- 记录价格历史
- 触发告警通知
- 数据分析与统计

Author: WeChat Monitor Team
"""

import json
import os
import time
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Python 3.6 兼容性：使用简单类替代 dataclass

from .api_client import WeChatAPIClient, PlaywrightClient, create_client

logger = logging.getLogger(__name__)


class AlertException(Exception):
    """
    告警异常类

    当检测到需要通知的情况时抛出，携带商品信息和告警内容
    """

    def __init__(self, product_id: str, alert_type: str, message: str, info: Dict[str, Any]):
        self.product_id = product_id
        self.alert_type = alert_type  # price_drop, stock_low, stock_recovery 等
        self.message = message
        self.info = info
        super().__init__(message)


class PriceRecord:
    """价格记录类（Python 3.6 兼容）"""

    def __init__(self, product_id: str, price: float, stock: int, timestamp: datetime,
                 name: str = "", original_price: float = 0.0):
        self.product_id = product_id
        self.price = price
        self.stock = stock
        self.timestamp = timestamp
        self.name = name
        self.original_price = original_price

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'product_id': self.product_id,
            'price': self.price,
            'stock': self.stock,
            'name': self.name,
            'original_price': self.original_price,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


class ProductMonitor:
    """
    商品监控器

    核心功能：
    1. 定期抓取商品价格/库存
    2. 保存历史记录到数据库
    3. 检测价格变化并触发告警
    4. 支持多种告警条件
    """

    def __init__(self, config: Dict[str, Any], data_dir: str = "data"):
        """
        初始化监控器

        Args:
            config: 完整配置字典
            data_dir: 数据存储目录
        """
        self.config = config
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 数据库路径
        self.db_path = self.data_dir / "monitor.db"

        # 价格历史 JSON 文件（用于快速访问）
        self.history_file = self.data_dir / "price_history.json"

        # 告警记录文件
        self.alert_log_file = self.data_dir / "alerts.json"

        # 告警冷却时间记录
        self.last_alert_time: Dict[str, float] = {}

        # 上次检查的价格记录（用于对比）
        self.last_check_info: Dict[str, Dict[str, Any]] = {}

        # 初始化客户端
        monitor_config = config.get('monitor', {})
        use_playwright = monitor_config.get('use_playwright', False)
        self.client = create_client(config, use_playwright)

        # 加载告警冷却时间
        self._load_cooldown_state()

        # 初始化数据库
        self._init_db()

        logger.info(f"商品监控器初始化完成，数据目录：{self.data_dir}")

    def _init_db(self):
        """初始化 SQLite 数据库"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 价格历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    product_name TEXT,
                    price REAL NOT NULL,
                    stock INTEGER NOT NULL,
                    original_price REAL DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 告警记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alert_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    product_name TEXT,
                    alert_type TEXT NOT NULL,
                    message TEXT,
                    current_price REAL,
                    current_stock INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建索引优化查询
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_product_time
                ON price_history(product_id, timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_alert_time
                ON alert_log(product_id, timestamp)
            ''')

            conn.commit()
            conn.close()
            logger.debug("数据库初始化完成")

        except Exception as e:
            logger.error(f"数据库初始化失败：{e}")
            raise

    def _load_cooldown_state(self):
        """加载告警冷却状态"""
        try:
            if self.alert_log_file.exists():
                with open(self.alert_log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.last_alert_time = data.get('cooldown', {})
                    logger.debug(f"加载告警冷却状态：{len(self.last_alert_time)} 条记录")
        except Exception as e:
            logger.warning(f"加载冷却状态失败：{e}")
            self.last_alert_time = {}

    def _save_cooldown_state(self):
        """保存告警冷却状态"""
        try:
            data = {'cooldown': self.last_alert_time}
            with open(self.alert_log_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存冷却状态失败：{e}")

    def get_enabled_products(self) -> List[Dict[str, Any]]:
        """
        获取启用的商品列表

        Returns:
            启用的商品配置列表
        """
        products = self.config.get('products', [])
        enabled = [p for p in products if p.get('enabled', True)]
        logger.debug(f"启用商品数：{len(enabled)}/{len(products)}")
        return enabled

    def check_product(self, product: Dict[str, Any]) -> Optional[PriceRecord]:
        """
        检查单个商品价格

        Args:
            product: 商品配置字典

        Returns:
            价格记录，失败返回 None
        """
        product_id = product.get('id', '')
        product_name = product.get('name', product_id)
        goods_id = product.get('goods_id', '')

        logger.info(f"检查商品：{product_name} ({product_id})")

        try:
            # 获取商品信息
            info = self.client.get_product_info(product_id, goods_id)

            if not info:
                logger.warning(f"获取商品信息失败：{product_name}")
                return None

            # 更新商品名称
            if info.get('name'):
                product_name = info['name']

            # 创建价格记录
            record = PriceRecord(
                product_id=product_id,
                price=info.get('price', 0.0),
                stock=info.get('stock', 0),
                timestamp=datetime.now(),
                name=product_name,
                original_price=info.get('original_price', 0.0),
            )

            # 保存价格历史
            self._save_price_record(record)

            # 保存到 JSON 历史文件
            self._save_to_history_json(record)

            # 检查告警条件
            self._check_alert(product, info)

            # 记录上次检查信息
            self.last_check_info[product_id] = info

            logger.info(
                f"商品检查完成：{product_name}, "
                f"价格：¥{record.price:.2f}, 库存：{record.stock}"
            )

            return record

        except AlertException:
            # 告警已记录，继续检查其他商品
            raise
        except Exception as e:
            logger.error(f"检查商品失败：{product_name}, 错误：{e}")
            return None

    def _save_price_record(self, record: PriceRecord):
        """保存价格记录到数据库"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO price_history
                (product_id, product_name, price, stock, original_price)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                record.product_id,
                record.name,
                record.price,
                record.stock,
                record.original_price,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"保存价格记录失败：{e}")

    def _save_to_history_json(self, record: PriceRecord):
        """保存价格记录到 JSON 文件（便于快速读取）"""
        try:
            history_data = {}
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)

            product_id = record.product_id
            if product_id not in history_data:
                history_data[product_id] = []

            # 添加新记录
            history_data[product_id].append(record.to_dict())

            # 保留最近 100 条记录
            history_data[product_id] = history_data[product_id][-100:]

            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"保存 JSON 历史失败：{e}")

    def _check_alert(self, product: Dict[str, Any], info: Dict[str, Any]):
        """
        检查是否需要触发告警

        告警条件：
        1. 价格低于目标价格
        2. 价格下降超过阈值百分比
        3. 库存低于目标值
        4. 库存从 0 变为有货（补货告警）

        Args:
            product: 商品配置
            info: 当前商品信息
        """
        product_id = product.get('id', '')
        product_name = product.get('name', product_id)
        target_price = product.get('target_price', 0)
        target_stock = product.get('stock_threshold', product.get('target_stock', 0))

        current_price = info.get('price', 0)
        current_stock = info.get('stock', 0)

        # 获取冷却时间配置
        cooldown = self.config.get('alert', {}).get('cooldown', 600)
        last_alert = self.last_alert_time.get(product_id, 0)

        # 检查是否在冷却时间内
        in_cooldown = time.time() - last_alert < cooldown

        alert_triggered = False
        alert_type = ""
        alert_message = ""

        # === 条件 1: 价格低于目标价格 ===
        if target_price > 0 and current_price <= target_price:
            if not in_cooldown:
                alert_triggered = True
                alert_type = "price_below_target"
                alert_message = (
                    f"【{product_name}】价格降至 ¥{current_price:.2f}, "
                    f"低于目标价 ¥{target_price:.2f}"
                )

        # === 条件 2: 价格下降超过阈值 ===
        if not alert_triggered:
            drop_alert = self._check_price_drop(product_id, current_price)
            if drop_alert and not in_cooldown:
                alert_triggered = True
                alert_type = "price_drop"
                alert_message = (
                    f"【{product_name}】价格大幅下降，当前 ¥{current_price:.2f}"
                )

        # === 条件 3: 库存低于目标值 ===
        if target_stock > 0 and current_stock > 0 and current_stock <= target_stock:
            if not in_cooldown:
                alert_triggered = True
                alert_type = "stock_low"
                alert_message = (
                    f"【{product_name}】库存紧张，仅剩 {current_stock} 件"
                )

        # === 条件 4: 库存恢复告警（从 0 变为有货）===
        if not alert_triggered:
            last_info = self.last_check_info.get(product_id, {})
            last_stock = last_info.get('stock', -1)

            # 从无货变为有货
            if last_stock == 0 and current_stock > 0:
                alert_config = self.config.get('alert', {})
                if alert_config.get('notify_stock_recovery', True):
                    # 库存恢复不受冷却时间限制
                    alert_triggered = True
                    alert_type = "stock_recovery"
                    alert_message = (
                        f"【{product_name}】补货！库存恢复至 {current_stock} 件"
                    )

        # 触发告警
        if alert_triggered:
            # 更新冷却时间
            self.last_alert_time[product_id] = time.time()
            self._save_cooldown_state()

            # 保存告警记录
            self._save_alert_log(product_id, product_name, alert_type, alert_message,
                                current_price, current_stock)

            logger.warning(f"触发告警 [{alert_type}]: {alert_message}")

            # 抛出异常，由上层处理通知
            raise AlertException(product_id, alert_type, alert_message, info)

    def _check_price_drop(self, product_id: str, current_price: float) -> bool:
        """
        检查价格是否下降超过阈值

        Args:
            product_id: 商品 ID
            current_price: 当前价格

        Returns:
            是否超过阈值
        """
        try:
            # 获取上次记录的价格
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('''
                SELECT price FROM price_history
                WHERE product_id = ?
                ORDER BY timestamp DESC
                LIMIT 1 OFFSET 1
            ''', (product_id,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return False

            last_price = row[0]
            if last_price <= 0:
                return False

            # 获取阈值配置
            threshold = self.config.get('monitor', {}).get('price_threshold', 0.05)
            drop_ratio = (last_price - current_price) / last_price

            if drop_ratio >= threshold:
                logger.info(
                    f"价格下降检测：{product_id}, "
                    f"从 ¥{last_price:.2f} 降至 ¥{current_price:.2f} "
                    f"(降幅 {drop_ratio*100:.1f}%)"
                )
                return True

        except Exception as e:
            logger.error(f"价格下降检查失败：{e}")

        return False

    def _save_alert_log(self, product_id: str, product_name: str,
                        alert_type: str, message: str,
                        current_price: float, current_stock: int):
        """保存告警记录到数据库"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alert_log
                (product_id, product_name, alert_type, message, current_price, current_stock)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (product_id, product_name, alert_type, message, current_price, current_stock))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"保存告警记录失败：{e}")

    def run_once(self) -> Tuple[List[PriceRecord], List[AlertException]]:
        """
        运行一次完整的监控检查

        Returns:
            (正常检查记录列表，触发的告警列表)
        """
        results = []
        alerts = []

        products = self.get_enabled_products()
        logger.info(f"开始本轮检查，共 {len(products)} 个商品")

        for product in products:
            try:
                record = self.check_product(product)
                if record:
                    results.append(record)
            except AlertException as e:
                alerts.append(e)
                logger.info(f"捕获告警：{e.product_id} - {e.alert_type}")
            except Exception as e:
                logger.error(f"检查商品异常：{product.get('id')}, 错误：{e}")

        logger.info(f"本轮检查完成：{len(results)} 个成功，{len(alerts)} 个告警")
        return results, alerts

    def start(self, alert_callback=None):
        """
        启动持续监控循环

        Args:
            alert_callback: 告警回调函数，接收 (AlertException) 参数
        """
        logger.info("=" * 50)
        logger.info("商品监控系统启动")
        logger.info("=" * 50)

        interval = self.config.get('monitor', {}).get('interval', 120)

        while True:
            start_time = time.time()

            try:
                results, alerts = self.run_once()

                # 调用告警回调
                if alert_callback:
                    for alert in alerts:
                        alert_callback(alert)

            except Exception as e:
                logger.error(f"监控循环错误：{e}")

            # 计算下次执行时间
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)

            if sleep_time > 0:
                logger.debug(f"等待 {sleep_time:.1f} 秒后执行下一轮")
                time.sleep(sleep_time)

    def get_price_history(self, product_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取指定商品的历史价格

        Args:
            product_id: 商品 ID
            days: 获取最近 N 天的数据

        Returns:
            价格记录列表
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            start_date = datetime.now() - timedelta(days=days)

            cursor.execute('''
                SELECT product_id, product_name, price, stock, original_price, timestamp
                FROM price_history
                WHERE product_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            ''', (product_id, start_date.isoformat()))

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    'product_id': row[0],
                    'name': row[1] or '',
                    'price': row[2],
                    'stock': row[3],
                    'original_price': row[4] or 0,
                    'timestamp': row[5],
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"获取历史价格失败：{e}")
            return []

    def get_alert_history(self, product_id: str = None, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取告警历史

        Args:
            product_id: 可选的商品 ID 过滤
            days: 获取最近 N 天的数据

        Returns:
            告警记录列表
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            start_date = datetime.now() - timedelta(days=days)

            if product_id:
                cursor.execute('''
                    SELECT product_id, product_name, alert_type, message,
                           current_price, current_stock, timestamp
                    FROM alert_log
                    WHERE product_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                ''', (product_id, start_date.isoformat()))
            else:
                cursor.execute('''
                    SELECT product_id, product_name, alert_type, message,
                           current_price, current_stock, timestamp
                    FROM alert_log
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                ''', (start_date.isoformat(),))

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    'product_id': row[0],
                    'name': row[1] or '',
                    'alert_type': row[2],
                    'message': row[3] or '',
                    'current_price': row[4],
                    'current_stock': row[5],
                    'timestamp': row[6],
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"获取告警历史失败：{e}")
            return []

    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        获取监控统计信息

        Args:
            days: 统计最近 N 天

        Returns:
            统计信息字典
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            start_date = datetime.now() - timedelta(days=days)

            # 商品数量统计
            cursor.execute('''
                SELECT COUNT(DISTINCT product_id) FROM price_history WHERE timestamp >= ?
            ''', (start_date.isoformat(),))
            product_count = cursor.fetchone()[0]

            # 价格记录总数
            cursor.execute('''
                SELECT COUNT(*) FROM price_history WHERE timestamp >= ?
            ''', (start_date.isoformat(),))
            record_count = cursor.fetchone()[0]

            # 告警总数
            cursor.execute('''
                SELECT COUNT(*) FROM alert_log WHERE timestamp >= ?
            ''', (start_date.isoformat(),))
            alert_count = cursor.fetchone()[0]

            # 各类型告警数量
            cursor.execute('''
                SELECT alert_type, COUNT(*)
                FROM alert_log
                WHERE timestamp >= ?
                GROUP BY alert_type
            ''', (start_date.isoformat(),))
            alert_by_type = dict(cursor.fetchall())

            conn.close()

            return {
                'days': days,
                'product_count': product_count,
                'record_count': record_count,
                'alert_count': alert_count,
                'alert_by_type': alert_by_type,
            }

        except Exception as e:
            logger.error(f"获取统计信息失败：{e}")
            return {}
