"""邮件通知服务。"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body_html: str) -> bool:
    """发送 HTML 邮件。

    Args:
        to: 收件人邮箱。
        subject: 邮件主题。
        body_html: HTML 正文。

    Returns:
        发送是否成功。
    """
    if not settings.smtp_host:
        logger.warning("SMTP 未配置，跳过邮件发送: %s", subject)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_port == 465,
            start_tls=settings.smtp_port == 587,
        )
        logger.info("邮件已发送至 %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error("邮件发送失败 (%s): %s", to, e)
        return False


def build_inventory_change_email(
    store_name: str,
    changes: list[dict[str, str]],
    captured_at: str,
) -> str:
    """生成库存变化通知邮件的 HTML 内容。"""

    rows = ""
    for c in changes:
        change_type_label = {
            "new": "🆕 新品上架",
            "removed": "❌ 已下架",
            "price_down": "📉 降价",
            "price_up": "📈 涨价",
            "restocked": "📦 已补货",
            "sold_out": "🚫 已售罄",
            "stock_change": "📊 库存变化",
        }.get(c["change_type"], c["change_type"])

        rows += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{c['product_name']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{change_type_label}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{c.get('detail', '')}</td>
        </tr>"""

    return f"""
    <html>
    <body style="font-family:'PingFang SC',Helvetica,Arial,sans-serif;background:#f5f7fa;padding:20px;">
        <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
            <div style="background:linear-gradient(135deg,#4A90D9,#357ABD);padding:24px;color:#fff;">
                <h2 style="margin:0;">🍞 {store_name} 库存变化通知</h2>
                <p style="margin:4px 0 0;font-size:13px;opacity:0.8;">监控时间: {captured_at}</p>
            </div>
            <div style="padding:16px 24px 24px;">
                <p>以下商品发生了<b>{len(changes)}</b>项变化：</p>
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="text-align:left;background:#f0f4ff;">
                            <th style="padding:8px 12px;">商品</th>
                            <th style="padding:8px 12px;">变化类型</th>
                            <th style="padding:8px 12px;">详情</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
                <p style="margin-top:16px;font-size:12px;color:#999;">
                    此邮件由 面包店库存监控 自动发送。如需调整通知频率，请在应用中修改设置。
                </p>
            </div>
        </div>
    </body>
    </html>"""
