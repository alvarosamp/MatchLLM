import os
from pathlib import Path
import sys


def _ensure_repo_root_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    _ensure_repo_root_on_path()
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")

    from core.utils.emailer import send_email

    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    tls = os.getenv("SMTP_TLS")
    ssl = os.getenv("SMTP_SSL")
    user = os.getenv("SMTP_USER")
    pwd = (os.getenv("SMTP_PASSWORD") or "").strip()

    print(f"SMTP_HOST={host} SMTP_PORT={port} SMTP_TLS={tls} SMTP_SSL={ssl} SMTP_USER={user}")
    if (not pwd) or ("CHANGE_ME" in pwd):
        raise RuntimeError("SMTP_PASSWORD não configurado no .env (ou ainda está como placeholder).")

    csv_bytes = b"edital_id,requisito,status\n1,exemplo,ATENDE\n"

    send_email(
        to_email="alvaroscareli@gmail.com",
        subject="MatchLLM - Teste de envio (CSV)",
        body_text="Teste automatico do MatchLLM: segue CSV em anexo.",
        attachments=[("match_multiple.csv", csv_bytes, "text/csv")],
    )

    print("OK: email enviado")


if __name__ == "__main__":
    main()
