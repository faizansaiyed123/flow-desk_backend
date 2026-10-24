"""Transactional email sending.

Function-based, single responsibility: format + dispatch. When no SMTP
server is configured (the default in dev/test), emails are logged instead
of sent so the whole app — including invite/reset flows — works fully
without any external credentials. Set SMTP_HOST + EMAIL_ENABLED in
production to actually deliver mail.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger("flowdesk.email")
settings = get_settings()


def send_email(*, to: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    if not settings.EMAIL_ENABLED or not settings.SMTP_HOST:
        logger.info("EMAIL (dev mode, not sent) -> to=%s subject=%r\n%s", to, subject, text_body or html_body)
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to
    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, [to], msg.as_string())
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def send_invitation_email(*, to: str, tenant_name: str, inviter_name: str, accept_url: str) -> None:
    subject = f"{inviter_name} invited you to join {tenant_name} on FlowDesk"
    text = (
        f"{inviter_name} has invited you to collaborate on {tenant_name} in FlowDesk.\n\n"
        f"Accept the invitation: {accept_url}\n\nThis link expires in 7 days."
    )
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>You're invited to {tenant_name}</h2>
      <p>{inviter_name} has invited you to collaborate in FlowDesk.</p>
      <p><a href="{accept_url}" style="background:#6366f1;color:#fff;padding:10px 20px;
      border-radius:6px;text-decoration:none;">Accept invitation</a></p>
      <p style="color:#888;font-size:13px;">This link expires in 7 days.</p>
    </div>
    """
    send_email(to=to, subject=subject, html_body=html, text_body=text)


def send_password_reset_email(*, to: str, reset_url: str) -> None:
    subject = "Reset your FlowDesk password"
    text = f"Reset your password: {reset_url}\n\nIf you didn't request this, you can ignore this email."
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>Reset your password</h2>
      <p><a href="{reset_url}" style="background:#6366f1;color:#fff;padding:10px 20px;
      border-radius:6px;text-decoration:none;">Reset password</a></p>
      <p style="color:#888;font-size:13px;">If you didn't request this, you can safely ignore this email.
      This link expires in 1 hour.</p>
    </div>
    """
    send_email(to=to, subject=subject, html_body=html, text_body=text)
