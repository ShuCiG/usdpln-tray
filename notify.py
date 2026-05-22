"""Notification delivery — Windows toast and email.

Both senders swallow their own errors: an alert that fails to deliver must
never crash the polling loop.
"""

import smtplib
from email.message import EmailMessage


def send_toast(title: str, message: str) -> bool:
    """Show a Windows toast notification. Returns True on success."""
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster("USD/PLN")
        toast = Toast()
        toast.text_fields = [title, message]
        toaster.show_toast(toast)
        return True
    except Exception as e:
        print(f"[notify] toast failed: {e}")
        return False


def send_email(email_cfg: dict, subject: str, body: str) -> bool:
    """Send an email via SMTP over SSL. Returns True on success.

    Skips cleanly (returns False) when no password is configured.
    """
    if not email_cfg.get("password"):
        print("[notify] email skipped: no password configured")
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = email_cfg["from_addr"]
        msg["To"] = email_cfg["to_addr"]
        msg.set_content(body)

        with smtplib.SMTP_SSL(
            email_cfg["smtp_host"], email_cfg["smtp_port"], timeout=15
        ) as smtp:
            smtp.login(email_cfg["username"], email_cfg["password"])
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"[notify] email failed: {e}")
        return False
