import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable, Optional, Tuple


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    from_email: str
    use_tls: bool
    use_ssl: bool

    @staticmethod
    def from_env() -> "SmtpConfig":
        host = (os.getenv("SMTP_HOST") or "").strip()
        port_raw = (os.getenv("SMTP_PORT") or "").strip()
        from_email = (os.getenv("SMTP_FROM") or "").strip()

        if not host or not port_raw or not from_email:
            raise RuntimeError(
                "SMTP não configurado. Defina SMTP_HOST, SMTP_PORT e SMTP_FROM (e opcionalmente SMTP_USER/SMTP_PASS)."
            )

        try:
            port = int(port_raw)
        except ValueError as e:
            raise RuntimeError("SMTP_PORT inválido; esperado inteiro.") from e

        username = (os.getenv("SMTP_USER") or "").strip() or None
        password = (os.getenv("SMTP_PASS") or "").strip() or None
        use_tls = str(os.getenv("SMTP_TLS", "1")).strip().lower() not in {"0", "false", "no"}
        use_ssl = str(os.getenv("SMTP_SSL", "0")).strip().lower() in {"1", "true", "yes"}

        # Se SMTP_SSL estiver habilitado, não faz sentido também tentar STARTTLS.
        if use_ssl:
            use_tls = False

        return SmtpConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            from_email=from_email,
            use_tls=use_tls,
            use_ssl=use_ssl,
        )


def is_valid_email(email: str) -> bool:
    email = (email or "").strip()
    return bool(email) and bool(_EMAIL_RE.match(email))


Attachment = Tuple[str, bytes, str]  # (filename, content_bytes, mime)


def send_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    attachments: Optional[Iterable[Attachment]] = None,
    smtp: Optional[SmtpConfig] = None,
) -> None:
    to_email = (to_email or "").strip()
    if not is_valid_email(to_email):
        raise ValueError("Email inválido")

    smtp = smtp or SmtpConfig.from_env()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.from_email
    msg["To"] = to_email
    msg.set_content(body_text or "")

    for attachment in attachments or []:
        filename, content_bytes, mime = attachment
        maintype, subtype = (mime.split("/", 1) + ["octet-stream"])[:2]
        msg.add_attachment(content_bytes, maintype=maintype, subtype=subtype, filename=filename)

    if smtp.use_ssl:
        server_cm = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=20)
    else:
        server_cm = smtplib.SMTP(smtp.host, smtp.port, timeout=20)

    with server_cm as server:
        if smtp.use_tls:
            server.starttls()
        if smtp.username and smtp.password:
            server.login(smtp.username, smtp.password)
        server.send_message(msg)
