import os
import re
from getpass import getpass
from pathlib import Path


def _upsert_env_var(env_text: str, key: str, value: str) -> str:
    # Preserve ordering where possible: if key exists, replace that line; else append.
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=).*?$", re.MULTILINE)
    replacement = rf"\1{value}"
    if pattern.search(env_text):
        return pattern.sub(replacement, env_text)

    if env_text and not env_text.endswith("\n"):
        env_text += "\n"
    return env_text + f"{key}={value}\n"


def _normalize_app_password(pw: str) -> str:
    # Gmail App Password is often shown with spaces; remove whitespace.
    return "".join(pw.split())


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env_path = repo_root / ".env"

    if not env_path.exists():
        raise SystemExit(f".env not found at: {env_path}")

    smtp_user = input("SMTP_USER (e.g. your@gmail.com): ").strip()
    if not smtp_user:
        raise SystemExit("SMTP_USER is required")

    smtp_from = input("SMTP_FROM (blank = same as SMTP_USER): ").strip() or smtp_user

    print("Paste your Gmail App Password (input hidden):")
    smtp_password = _normalize_app_password(getpass("SMTP_PASSWORD: "))
    if not smtp_password:
        raise SystemExit("SMTP_PASSWORD is required")

    mode = (input("Use SSL 465? (y/N): ").strip().lower() or "n")
    use_ssl = mode in {"y", "yes"}

    smtp_host = input("SMTP_HOST (blank = smtp.gmail.com): ").strip() or "smtp.gmail.com"

    if use_ssl:
        smtp_port = "465"
        smtp_ssl = "1"
        smtp_tls = "0"
    else:
        smtp_port = "587"
        smtp_ssl = "0"
        smtp_tls = "1"

    env_text = env_path.read_text(encoding="utf-8")

    env_text = _upsert_env_var(env_text, "SMTP_HOST", smtp_host)
    env_text = _upsert_env_var(env_text, "SMTP_PORT", smtp_port)
    env_text = _upsert_env_var(env_text, "SMTP_SSL", smtp_ssl)
    env_text = _upsert_env_var(env_text, "SMTP_TLS", smtp_tls)
    env_text = _upsert_env_var(env_text, "SMTP_USER", smtp_user)
    env_text = _upsert_env_var(env_text, "SMTP_FROM", smtp_from)
    env_text = _upsert_env_var(env_text, "SMTP_PASSWORD", smtp_password)

    env_path.write_text(env_text, encoding="utf-8")

    print("OK: wrote SMTP settings to .env (password not printed).")
    print("Next: python scripts/test_smtp_send.py")


if __name__ == "__main__":
    main()
