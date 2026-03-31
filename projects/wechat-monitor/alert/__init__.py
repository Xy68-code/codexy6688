"""
微信小程序商品监控系统 - 告警通知模块

支持的通知方式：
- Discord Webhook
- 企业微信 Webhook
- 邮件 SMTP
"""

from .notifier import Notifier, create_notifier

__all__ = [
    'Notifier',
    'create_notifier',
]
