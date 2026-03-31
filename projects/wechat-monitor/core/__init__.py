"""
微信小程序商品监控系统 - 核心模块

包含：
- api_client: 微信 API 客户端（支持 requests 和 Playwright）
- monitor: 监控核心逻辑
"""

from .api_client import WeChatAPIClient, PlaywrightClient, create_client
from .monitor import ProductMonitor, PriceRecord, AlertException

__all__ = [
    'WeChatAPIClient',
    'PlaywrightClient',
    'create_client',
    'ProductMonitor',
    'PriceRecord',
    'AlertException',
]
