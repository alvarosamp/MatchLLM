"""
Script de teste da API
- Faz upload do primeiro PDF encontrado em `data/editais`.
- Realiza match com o primeiro JSON de `data/produtos` (ou usa um fallback) e uma consulta exemplo.

Melhorias:
- Caminhos relativos ao repositório (sem hardcode de paths absolutos).
- Tratamento de erros e mensagens mais claras.
- Saída formatada em JSON para melhor leitura.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests


def find_first_pdf(edital_dir: Path) -> Optional[Path]:
    """Retorna o primeiro arquivo PDF no diretório informado, se existir."""
    for p in sorted(edital_dir.glob("*.pdf")):
        if p.is_file():
            return p
    return None


def find_first_product_json(produtos_dir: Path) -> Optional[dict]:
    """Carrega e retorna o primeiro JSON de produto no diretório informado, se existir."""
    for pj in sorted(produtos_dir.glob("*.json")):
        if pj.is_file():
            try:
                return json.loads(pj.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"Aviso: falha ao decodificar JSON em {pj}: {e}")
                continue
    return None


def main() -> None:
    # Args
    parser = argparse.ArgumentParser(description="Teste da API de Editais/Match")
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://localhost:8000"),
                        help="Base URL da API (padrão via env API_BASE_URL ou http://localhost:8000)")
    parser.add_argument("--pdf", type=str, default=None, help="Caminho para um PDF específico em data/editais")
    parser.add_argument("--produto", type=str, default=None, help="Caminho para JSON de produto em data/produtos")
    parser.add_argument("--consulta", type=str, default="switch 24 portas poe", help="Consulta para o match")
    parser.add_argument("--timeout-upload", type=int, default=60, help="Timeout (s) para upload")
    parser.add_argument("--timeout-match", type=int, default=120, help="Timeout (s) para match")
    parser.add_argument("--ping", action="store_true", help="Tenta pingar a API antes de iniciar (GET /health)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Saída detalhada (inclui curl)")
    # Novos argumentos de teste
    parser.add_argument("--list", action="store_true", help="Lista PDFs e JSONs disponíveis e sai")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Pula upload e usa o edital_id mais recente em data/processed/vectorstore")
    parser.add_argument("--auth-header", type=str, default=None,
                        help="Cabeçalho de autorização (ex: 'Authorization: Bearer XXX')")
    parser.add_argument("--retries", type=int, default=0, help="Número de tentativas extras com backoff")
    parser.add_argument("--backoff", type=float, default=1.5, help="Fator de backoff entre tentativas")
    args = parser.parse_args()

    api_base_url = args.base_url.rstrip("/")

    # Raiz do repositório (um nível acima de /teste)
    repo_root = Path(__file__).resolve().parents[1]
    editais_dir = repo_root / "data" / "editais"
    produtos_dir = repo_root / "data" / "produtos"

    if not editais_dir.exists():
        raise SystemExit(f"Diretório não encontrado: {editais_dir}")

    if not produtos_dir.exists():
        print(f"Aviso: diretório de produtos não encontrado: {produtos_dir}")

    # Lista e sai
    if args.list:
        print("Arquivos disponíveis:")
        print("- PDFs:")
        for p in sorted(editais_dir.glob("*.pdf")):
            print(f"  * {p.name}")
        print("- Produtos JSON:")
        if produtos_dir.exists():
            for pj in sorted(produtos_dir.glob("*.json")):
                print(f"  * {pj.name}")
        else:
            print("  (diretório não encontrado)")
        return

    # Health check opcional
    if args.ping:
        try:
            hc = requests.get(f"{api_base_url}/health", timeout=10)
            if args.verbose:
                print(f"[ping] GET {api_base_url}/health -> {hc.status_code}")
            hc.raise_for_status()
        except Exception as e:
            print(f"Aviso: falha no ping da API: {e}")

    # Seleciona o primeiro PDF ou o escolhido via --pdf
    if args.pdf:
        edital_pdf = Path(args.pdf)
        if not edital_pdf.is_absolute():
            edital_pdf = editais_dir / edital_pdf
        if not edital_pdf.exists():
            raise SystemExit(f"PDF especificado não existe: {edital_pdf}")
    else:
        edital_pdf = find_first_pdf(editais_dir)
        if edital_pdf is None:
            raise SystemExit("Nenhum PDF encontrado em data/editais")

    print(f"Usando PDF: {edital_pdf.name}")

    # Cabeçalhos opcionais (auth)
    headers = {}
    if args.auth_header:
        try:
            k, v = args.auth_header.split(":", 1)
            headers[k.strip()] = v.strip()
        except ValueError:
            raise SystemExit("Formato inválido para --auth-header. Use 'Chave: Valor'.")

    # Upload do edital (com opção de pular e com retry)
    edital_id: Optional[int] = None
    total_chunks: Optional[int] = None

    def find_latest_index_id() -> Optional[int]:
        vector_dir = repo_root / "data" / "processed" / "vectorstore"
        if not vector_dir.exists():
            return None
        ids = []
        for fp in vector_dir.glob("edital_*_index.pkl"):
            try:
                ids.append(int(fp.name.replace("edital_", "").replace("_index.pkl", "")))
            except Exception:
                continue
        return sorted(ids)[-1] if ids else None

    if args.skip_upload:
        latest_id = find_latest_index_id()
        if latest_id is None:
            raise SystemExit("Nenhum índice existente encontrado para --skip-upload.")
        edital_id = latest_id
        print(f"Pulado upload. Usando edital_id existente: {edital_id}")
    else:
        files = {"file": (edital_pdf.name, edital_pdf.read_bytes(), "application/pdf")}
        if args.verbose:
            print("[debug] curl upload:")
            print(f"curl -X POST '{api_base_url}/editais/upload' -F 'file=@{edital_pdf}'")

        attempt = 0
        while True:
            try:
                r = requests.post(f"{api_base_url}/editais/upload",
                                  files=files, headers=headers, timeout=args.timeout_upload)
                r.raise_for_status()
                try:
                    resp = r.json()
                except ValueError:
                    raise SystemExit(f"Resposta não é JSON válida: {r.text if r is not None else ''}")

                edital_id = resp.get("edital_id")
                total_chunks = resp.get("total_chunks")
                if not edital_id:
                    raise SystemExit(f"Resposta inesperada: {json.dumps(resp, ensure_ascii=False)}")

                print(f"Upload OK: edital_id={edital_id}, chunks={total_chunks}")
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException) as e:
                if isinstance(e, requests.exceptions.HTTPError):
                    # Fallback: tenta usar índice existente
                    latest_id = find_latest_index_id()
                    if latest_id is not None:
                        edital_id = latest_id
                        print(f"Falha no upload ({e}). Usando edital_id existente (fallback): {edital_id}")
                        break
                attempt += 1
                if attempt > args.retries:
                    if isinstance(e, requests.exceptions.ConnectionError):
                        raise SystemExit(
                            "Não foi possível conectar à API. Verifique se o servidor está rodando em "
                            f"{api_base_url} e se a porta está acessível."
                        )
                    elif isinstance(e, requests.exceptions.Timeout):
                        raise SystemExit("Timeout ao tentar fazer upload. Tente novamente ou aumente o timeout.")
                    else:
                        raise SystemExit(f"Falha no upload do edital: {e}")
                sleep_s = (args.backoff ** attempt)
                print(f"Aviso: upload falhou ({e}). Tentativa {attempt}/{args.retries}. Aguardando {sleep_s:.1f}s...")
                time.sleep(sleep_s)

    # Seleciona produto (primeiro JSON, ou via --produto, ou fallback)
    if args.produto:
        produto_path = Path(args.produto)
        if not produto_path.is_absolute():
            produto_path = produtos_dir / produto_path
        if not produto_path.exists():
            raise SystemExit(f"Produto JSON especificado não existe: {produto_path}")
        try:
            produto_json = json.loads(produto_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Falha ao decodificar JSON do produto {produto_path}: {e}")
    else:
        produto_json = find_first_product_json(produtos_dir)
        if produto_json is None:
            produto_json = {"nome": "Switch X", "atributos": {"portas": 24, "poe": True}}
            print("Aviso: nenhum JSON de produto encontrado; usando fallback")

    if 'edital_id' not in locals():
        raise SystemExit("Nenhum edital_id disponível para realizar o match.")

    consulta = args.consulta
    if args.verbose:
        print("[debug] curl match:")
        consulta_q = consulta.replace("'", "'\"'\"'")
        print(
            "curl -X POST "
            f"'{api_base_url}/editais/match/{edital_id}?consulta={consulta_q}' "
            "-H 'Content-Type: application/json' "
            + (f"-H '{args.auth_header}' " if args.auth_header else "")
            + f"-d '{json.dumps(produto_json, ensure_ascii=False)}'"
        )

    # Match com retry
    attempt = 0
    while True:
        try:
            r2 = requests.post(
                f"{api_base_url}/editais/match/{edital_id}",
                params={"consulta": consulta},
                json=produto_json,
                headers=headers,
                timeout=args.timeout_match,
            )
            r2.raise_for_status()
            match_resp = r2.json()
            print("Match OK:")
            print(json.dumps(match_resp, ensure_ascii=False, indent=2))
            break
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException) as e:
            attempt += 1
            if attempt > args.retries:
                if isinstance(e, requests.exceptions.ConnectionError):
                    raise SystemExit(
                        "Não foi possível conectar à API durante o match. Verifique o servidor e o endpoint."
                    )
                elif isinstance(e, requests.exceptions.Timeout):
                    raise SystemExit("Timeout ao tentar realizar o match. Tente novamente ou aumente o timeout.")
                else:
                    raise SystemExit(f"Falha no match: {e}")
            sleep_s = (args.backoff ** attempt)
            print(f"Aviso: match falhou ({e}). Tentativa {attempt}/{args.retries}. Aguardando {sleep_s:.1f}s...")
            time.sleep(sleep_s)


if __name__ == "__main__":
    main()
