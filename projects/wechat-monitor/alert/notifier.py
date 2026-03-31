"""
告警通知模块

支持的通知方式：
- Discord Webhook（富文本卡片）
- 企业微信 Webhook（Markdown）
- 邮件 SMTP（HTML 格式）

Author: WeChat Monitor Team
"""

import logging
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class Notifier:
    """
    通知管理器

    负责将告警信息通过不同渠道发送给用户
    支持多种通知方式，可同时启用多个渠道
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化通知器

        Args:
            config: alert 配置部分
        """
        self.config = config
        self.discord_config = config.get('discord', {})
        self.wechat_work_config = config.get('wechat_work', {})
        self.email_config = config.get('email', {})

        # 通知发送统计
        self.sent_count = 0
        self.failed_count = 0

        logger.info("通知器初始化完成")

    def send_alert(self, alert_type: str, message: str, info: Dict[str, Any],
                   product_config: Dict[str, Any] = None) -> Dict[str, bool]:
        """
        发送告警通知

        Args:
            alert_type: 告警类型 (price_drop, stock_low, stock_recovery 等)
            message: 告警消息文本
            info: 商品信息（price, stock, name 等）
            product_config: 商品配置（可选）

        Returns:
            各渠道发送结果字典 {'discord': True, 'wechat_work': False, ...}
        """
        # 构建通知内容
        content = self._build_message(alert_type, message, info, product_config)

        # 各渠道发送结果
        results = {}

        # Discord 通知
        if self.discord_config.get('enabled'):
            results['discord'] = self._send_discord(content, alert_type, info)
        else:
            results['discord'] = False

        # 企业微信通知
        if self.wechat_work_config.get('enabled'):
            results['wechat_work'] = self._send_wechat_work(content, alert_type, info)
        else:
            results['wechat_work'] = False

        # 邮件通知
        if self.email_config.get('enabled'):
            results['email'] = self._send_email(content, alert_type, info, product_config)
        else:
            results['email'] = False

        # 统计结果
        if any(results.values()):
            self.sent_count += 1
            logger.info(f"告警通知已发送，渠道：{[k for k, v in results.items() if v]}")
        else:
            self.failed_count += 1
            logger.warning("所有通知渠道发送失败")

        return results

    def _build_message(self, alert_type: str, message: str, info: Dict[str, Any],
                       product_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        构建通知内容

        Args:
            alert_type: 告警类型
            message: 告警消息
            info: 商品信息
            product_config: 商品配置

        Returns:
            包含通知各字段的字典
        """
        product_id = info.get('product_id', product_config.get('id', 'unknown') if product_config else 'unknown')
        product_name = info.get('name', product_config.get('name', product_id) if product_config else product_id)

        current_price = info.get('price', 0)
        current_stock = info.get('stock', 0)
        original_price = info.get('original_price', 0)

        # 计算折扣
        discount = ""
        if original_price > 0 and current_price > 0:
            discount_rate = current_price / original_price * 100
            discount = f"{discount_rate:.1f}折"

        # 告警类型对应的图标和标题
        alert_emojis = {
            'price_below_target': '💰',
            'price_drop': '📉',
            'stock_low': '⚠️',
            'stock_recovery': '✅',
            'default': '🔔',
        }

        alert_titles = {
            'price_below_target': '价格低于目标',
            'price_drop': '价格大幅下降',
            'stock_low': '库存紧张',
            'stock_recovery': '补货通知',
            'default': '价格告警',
        }

        emoji = alert_emojis.get(alert_type, alert_emojis['default'])
        title = alert_titles.get(alert_type, alert_titles['default'])

        return {
            'product_id': product_id,
            'product_name': product_name,
            'alert_type': alert_type,
            'title': title,
            'emoji': emoji,
            'message': message,
            'current_price': current_price,
            'current_stock': current_stock,
            'original_price': original_price,
            'discount': discount,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def _send_discord(self, content: Dict[str, Any], alert_type: str,
                      info: Dict[str, Any]) -> bool:
        """
        发送 Discord 通知（使用 Embed 富文本）

        Args:
            content: 通知内容
            alert_type: 告警类型
            info: 原始商品信息

        Returns:
            是否发送成功
        """
        webhook_url = self.discord_config.get('webhook_url')
        if not webhook_url:
            logger.error("Discord Webhook URL 未配置")
            return False

        try:
            # 根据告警类型设置颜色
            color_map = {
                'price_below_target': 0x00ff00,  # 绿色
                'price_drop': 0xff6600,  # 橙色
                'stock_low': 0xff0000,  # 红色
                'stock_recovery': 0x0099ff,  # 蓝色
            }
            color = color_map.get(alert_type, 0x999999)

            # 构建 Embed
            embed = {
                "title": f"{content['emoji']} {content['title']}",
                "color": color,
                "timestamp": datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "📦 商品名称",
                        "value": content['product_name'],
                        "inline": False,
                    },
                    {
                        "name": "💰 当前价格",
                        "value": f"¥{content['current_price']:.2f}" if content['current_price'] else "N/A",
                        "inline": True,
                    },
                    {
                        "name": "📊 库存",
                        "value": str(content['current_stock']) if content['current_stock'] >= 0 else "N/A",
                        "inline": True,
                    },
                    {
                        "name": "📝 详情",
                        "value": content['message'],
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": "微信小程序监控系统",
                    "icon_url": "https://i.imgur.com/AVV6vFj.png",
                },
            }

            # 添加原价字段（如果有折扣）
            if content['original_price'] > 0:
                embed["fields"].insert(2, {
                    "name": "🏷️ 原价",
                    "value": f"¥{content['original_price']:.2f}",
                    "inline": True,
                })

            # 构建 payload
            payload = {
                "username": "价格监控机器人",
                "avatar_url": "https://i.imgur.com/AVV6vFj.png",
                "embeds": [embed],
            }

            # 添加提及（如果配置了）
            mention_role_id = self.discord_config.get('mention_role_id')
            if mention_role_id:
                payload["content"] = f"<@&{mention_role_id}>"

            # 发送请求
            response = requests.post(webhook_url, json=payload, timeout=15)
            response.raise_for_status()

            logger.info(f"Discord 通知已发送：{content['product_name']}")
            return True

        except requests.exceptions.Timeout:
            logger.error("Discord 请求超时")
            return False
        except Exception as e:
            logger.error(f"Discord 发送失败：{e}")
            return False

    def _send_wechat_work(self, content: Dict[str, Any], alert_type: str,
                          info: Dict[str, Any]) -> bool:
        """
        发送企业微信通知（Markdown 格式）

        Args:
            content: 通知内容
            alert_type: 告警类型
            info: 原始商品信息

        Returns:
            是否发送成功
        """
        webhook_url = self.wechat_work_config.get('webhook_url')
        if not webhook_url:
            logger.error("企业微信 Webhook URL 未配置")
            return False

        try:
            # 构建 Markdown 消息
            markdown = f"""## {content['emoji']} {content['title']}

> **商品名称**: {content['product_name']}
> **商品 ID**: {content['product_id']}

---

| 项目 | 数值 |
|------|------|
| 💰 当前价格 | ¥{content['current_price']:.2f} |
| 🏷️ 原价 | ¥{content['original_price']:.2f} |
| 📊 库存 | {content['current_stock']} |
| ⏰ 时间 | {content['timestamp']} |

---

**详情**: {content['message']}

> _微信小程序监控系统_"""

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": markdown
                }
            }

            response = requests.post(webhook_url, json=payload, timeout=15)
            response.raise_for_status()

            result = response.json()
            if result.get('errcode') == 0:
                logger.info(f"企业微信通知已发送：{content['product_name']}")
                return True
            else:
                logger.error(f"企业微信返回错误：{result}")
                return False

        except requests.exceptions.Timeout:
            logger.error("企业微信请求超时")
            return False
        except Exception as e:
            logger.error(f"企业微信发送失败：{e}")
            return False

    def _send_email(self, content: Dict[str, Any], alert_type: str,
                    info: Dict[str, Any], product_config: Dict[str, Any] = None) -> bool:
        """
        发送邮件通知（HTML 格式）

        Args:
            content: 通知内容
            alert_type: 告警类型
            info: 原始商品信息
            product_config: 商品配置

        Returns:
            是否发送成功
        """
        smtp_server = self.email_config.get('smtp_server')
        smtp_port = self.email_config.get('smtp_port', 587)
        use_tls = self.email_config.get('use_tls', True)
        username = self.email_config.get('username')
        password = self.email_config.get('password')
        recipients = self.email_config.get('recipients', [])

        if not all([smtp_server, username, password, recipients]):
            logger.error("邮件配置不完整")
            return False

        try:
            # 构建 HTML 邮件
            html_content = self._build_email_html(content, alert_type)

            msg = MIMEMultipart('alternative')
            msg['From'] = username
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"{content['emoji']} {content['title']} - {content['product_name']}"

            # 纯文本版本（兼容性）
            plain_text = f"""
{content['emoji']} {content['title']}

商品名称：{content['product_name']}
商品 ID: {content['product_id']}

当前价格：¥{content['current_price']:.2f}
原价：¥{content['original_price']:.2f}
库存：{content['current_stock']}
时间：{content['timestamp']}

详情：{content['message']}

---
微信小程序监控系统
"""
            msg.attach(MIMEText(plain_text, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))

            # 连接 SMTP 服务器
            if use_tls:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)

            server.login(username, password)
            server.send_message(msg)
            server.quit()

            logger.info(f"邮件已发送至 {recipients}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("邮件认证失败，请检查用户名和密码")
            return False
        except smtplib.SMTPConnectError:
            logger.error(f"无法连接邮件服务器：{smtp_server}")
            return False
        except Exception as e:
            logger.error(f"邮件发送失败：{e}")
            return False

    def _build_email_html(self, content: Dict[str, Any], alert_type: str) -> str:
        """构建 HTML 邮件内容"""

        # 告警类型颜色
        color_map = {
            'price_below_target': '#28a745',
            'price_drop': '#fd7e14',
            'stock_low': '#dc3545',
            'stock_recovery': '#007bff',
        }
        color = color_map.get(alert_type, '#6c757d')

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        .info-table td {{ padding: 10px; border-bottom: 1px solid #dee2e6; }}
        .info-table tr:last-child td {{ border-bottom: none; }}
        .label {{ font-weight: bold; color: #495057; }}
        .footer {{ text-align: center; margin-top: 20px; color: #6c757d; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">{content['emoji']} {content['title']}</h2>
        </div>
        <div class="content">
            <p style="margin: 0 0 15px 0;"><strong>商品名称:</strong> {content['product_name']}</p>
            <p style="margin: 0 0 15px 0;"><strong>商品 ID:</strong> {content['product_id']}</p>

            <table class="info-table">
                <tr>
                    <td class="label">💰 当前价格</td>
                    <td>¥{content['current_price']:.2f}</td>
                </tr>
                <tr>
                    <td class="label">🏷️ 原价</td>
                    <td>¥{content['original_price']:.2f}</td>
                </tr>
                <tr>
                    <td class="label">📊 库存</td>
                    <td>{content['current_stock']}</td>
                </tr>
                <tr>
                    <td class="label">⏰ 时间</td>
                    <td>{content['timestamp']}</td>
                </tr>
            </table>

            <p style="background: white; padding: 15px; border-radius: 4px; border-left: 4px solid {color};">
                <strong>详情:</strong><br>{content['message']}
            </p>
        </div>
        <div class="footer">
            微信小程序监控系统
        </div>
    </div>
</body>
</html>
"""

    def test_connection(self) -> Dict[str, bool]:
        """
        测试各通知渠道连接

        Returns:
            各渠道测试结果
        """
        results = {}

        # 测试 Discord
        if self.discord_config.get('enabled'):
            webhook_url = self.discord_config.get('webhook_url')
            if webhook_url:
                try:
                    response = requests.get(webhook_url, timeout=10)
                    results['discord'] = response.status_code == 200
                except:
                    results['discord'] = False
            else:
                results['discord'] = False

        # 测试企业微信
        if self.wechat_work_config.get('enabled'):
            webhook_url = self.wechat_work_config.get('webhook_url')
            if webhook_url:
                try:
                    payload = {"msgtype": "text", "text": {"content": "测试消息"}}
                    response = requests.post(webhook_url, json=payload, timeout=10)
                    result = response.json()
                    results['wechat_work'] = result.get('errcode') == 0
                except:
                    results['wechat_work'] = False
            else:
                results['wechat_work'] = False

        # 测试邮件
        if self.email_config.get('enabled'):
            # 邮件连接测试较复杂，这里只做简单检查
            results['email'] = all([
                self.email_config.get('smtp_server'),
                self.email_config.get('username'),
                self.email_config.get('password'),
                self.email_config.get('recipients'),
            ])

        return results

    def get_stats(self) -> Dict[str, int]:
        """获取通知统计信息"""
        return {
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'total': self.sent_count + self.failed_count,
        }


def create_notifier(config: Dict[str, Any]) -> Notifier:
    """
    工厂函数：创建通知器实例

    Args:
        config: 完整配置字典

    Returns:
        Notifier 实例
    """
    alert_config = config.get('alert', {})
    return Notifier(alert_config)
