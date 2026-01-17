import os
import re
import smtplib
from email.message import EmailMessage
from typing import Iterable, Tuple


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip()))


def send_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    attachments: Iterable[Tuple[str, bytes, str]] | None = None,
):
    """Envia email via SMTP quando configurado.

    Variáveis de ambiente suportadas:
    - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
    - SMTP_TLS ("1" para STARTTLS)
    - SMTP_FROM (default: SMTP_USER)

    Se não estiver configurado, lança erro para o caller tratar (rotas já tratam).
    """

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = (os.getenv("SMTP_USER") or "").strip() or None
    password_raw = os.getenv("SMTP_PASSWORD") or ""
    # Gmail App Password costuma vir com espaços (xxxx xxxx xxxx xxxx). Removemos espaços.
    password = password_raw.replace(" ", "").strip() or None
    use_tls = os.getenv("SMTP_TLS", "1") not in {"0", "false", "False"}
    use_ssl = os.getenv("SMTP_SSL", "0") not in {"0", "false", "False"}
    from_email = (os.getenv("SMTP_FROM") or user or "").strip() or None

    if not host or not from_email:
        raise RuntimeError("SMTP não configurado (defina SMTP_HOST/SMTP_USER/SMTP_PASSWORD)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body_text or "")

    if attachments:
        for filename, content, mime in attachments:
            maintype, subtype = (mime.split("/", 1) + ["octet-stream"])[:2]
            msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    if use_ssl:
        smtp_ctx = smtplib.SMTP_SSL(host, port)
    else:
        smtp_ctx = smtplib.SMTP(host, port)

    with smtp_ctx as smtp:
        if (not use_ssl) and use_tls:
            smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
