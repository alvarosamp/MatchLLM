import argparse
import json
import sys
from pathlib import Path

# Permite rodar este script tanto da raiz do projeto quanto de dentro de `scripts/`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.utils.emailer import send_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a test email using MatchLLM SMTP env vars.")
    parser.add_argument("--to", required=True, help="Recipient email")
    parser.add_argument("--subject", default="MatchLLM - Teste de email", help="Email subject")
    parser.add_argument("--body", default="Email de teste do MatchLLM.", help="Plain text body")
    args = parser.parse_args()

    payload = {
        "message": "Email de teste do MatchLLM",
        "note": "Se você recebeu isso, SMTP_* está configurado corretamente.",
    }

    send_email(
        to_email=args.to,
        subject=args.subject,
        body_text=args.body,
        attachments=[(
            "matchllm_test.json",
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
        )],
    )

    print(f"OK: email enviado para {args.to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
