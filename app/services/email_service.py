"""VYRO — Email service. Dev: logs emails. Prod: SMTP via aiosmtplib/stdlib."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger("vyro.email")


def _render(kind: str, username: str, token: str) -> tuple[str, str]:
    link = f"https://app.vyro.app/{kind}?token={token}"
    if kind == "verify_email":
        subject = "تایید ایمیل VYRO"
        html = f"""
        <div style="font-family:sans-serif;direction:rtl;text-align:right">
          <h2>سلام {username} عزیز 👋</h2>
          <p>به <b>VYRO</b> خوش آمدی! برای فعال‌سازی حساب روی لینک زیر بزن:</p>
          <p><a href="{link}">تایید ایمیل</a></p>
          <p>کد: <code>{token}</code></p>
        </div>"""
    else:  # reset_password
        subject = "بازیابی رمز عبور VYRO"
        html = f"""
        <div style="font-family:sans-serif;direction:rtl;text-align:right">
          <h2>سلام {username}</h2>
          <p>برای تغییر رمز عبور روی لینک زیر بزن (۱ ساعت اعتبار دارد):</p>
          <p><a href="{link}">بازیابی رمز عبور</a></p>
          <p>اگر این درخواست را نزدی، این ایمیل را نادیده بگیر.</p>
        </div>"""
    return subject, html


async def send_email(to: str, kind: str, username: str, token: str) -> None:
    """Never raises — email failure must not break registration flows."""
    try:
        subject, html = _render(kind, username, token)
        if not settings.SMTP_HOST:
            logger.info("[DEV EMAIL] to=%s kind=%s token=%s", to, kind, token)
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        def _smtp_send():
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
                s.starttls()
                if settings.SMTP_USER:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
                s.sendmail(settings.SMTP_FROM, [to], msg.as_string())

        import asyncio

        await asyncio.to_thread(_smtp_send)
        logger.info("[EMAIL] sent to=%s kind=%s", to, kind)
    except Exception:
        logger.exception("[EMAIL] failed to=%s kind=%s", to, kind)
