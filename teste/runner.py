"""
Runner automático:
- Varre PDFs em data/editais e faz upload (ou usa fallback se falhar).
- Varre PDFs de datasheets em data/produtos e monta um JSON simples por arquivo.
- Executa match para cada (edital_id escolhido) x (produto) com consulta padrão.

Uso:
  API_BASE_URL=http://127.0.0.1:8000 python teste/runner.py

Observações:
- Se o upload falhar, usa o último índice existente em data/processed/vectorstore.
- O JSON de produto é um template simples; ajuste conforme necessário.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional, List
import requests
import argparse
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITAIS_DIR = REPO_ROOT / "data" / "editais"
PRODUTOS_DIR = REPO_ROOT / "data" / "produtos"
VECTOR_DIR = REPO_ROOT / "data" / "processed" / "vectorstore"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def list_pdfs(folder: Path) -> List[Path]:
    return [p for p in sorted(folder.glob("*.pdf")) if p.is_file()]


def list_index_ids() -> List[int]:
    ids: List[int] = []
    if VECTOR_DIR.exists():
        for fp in VECTOR_DIR.glob("edital_*_index.pkl"):
            try:
                id_str = fp.name.replace("edital_", "").replace("_index.pkl", "")
                ids.append(int(id_str))
            except Exception:
                continue
    return sorted(ids)


def upload_edital(edital_pdf: Path) -> Optional[tuple[int, Optional[int]]]:
    files = {"file": (edital_pdf.name, edital_pdf.read_bytes(), "application/pdf")}
    try:
        r = requests.post(f"{API_BASE_URL}/editais/upload", files=files, timeout=120)
        r.raise_for_status()
        resp = r.json()
        return resp.get("edital_id"), resp.get("total_chunks")
    except requests.exceptions.HTTPError as e:
        print(f"[upload] HTTPError: {e}")
        # fallback: usa índice existente
        ids = list_index_ids()
        if ids:
            return ids[-1], None
        return None
    except requests.exceptions.RequestException as e:
        print(f"[upload] erro de requisição: {e}")
        return None
    except ValueError:
        print(f"[upload] resposta não é JSON válida")
        return None


def produto_from_datasheet(pdf: Path) -> dict:
    # Template simples; adapte conforme suas necessidades
    return {
        "nome": pdf.stem,
        "atributos": {
            "portas": 24,
            "poe": True,
            "gigabit": True,
            "gerenciavel": True,
        },
        "origem": pdf.name,
    }


def run() -> None:
    # Args CLI
    parser = argparse.ArgumentParser(description="Runner automático de upload + match")
    parser.add_argument("--consulta", type=str, default="switch 24 portas poe", help="Consulta para o match")
    parser.add_argument("--timeout-upload", type=int, default=120, help="Timeout (s) para upload")
    parser.add_argument("--timeout-match", type=int, default=120, help="Timeout (s) para match")
    parser.add_argument("--retries", type=int, default=2, help="Tentativas extras para match em caso de falha (500/timeout/conexão)")
    parser.add_argument("--backoff", type=float, default=2.0, help="Fator de backoff exponencial entre tentativas")
    parser.add_argument("--auth-header", type=str, default=None, help="Cabeçalho de autorização (ex: 'Authorization: Bearer XXX')")
    parser.add_argument("--verbose", "-v", action="store_true", help="Saída detalhada (inclui curl)")
    # Novo: escolher modelo e ping do LLM local (Ollama)
    parser.add_argument("--model", type=str, default=None, help="Modelo de LLM a ser usado no match (ex: 'llama3:latest')")
    parser.add_argument("--ping-llm", action="store_true", help="Verifica Ollama em http://localhost:11434 antes de rodar")
    args = parser.parse_args()

    headers = {}
    if args.auth_header:
        try:
            k, v = args.auth_header.split(":", 1)
            headers[k.strip()] = v.strip()
        except ValueError:
            raise SystemExit("Formato inválido para --auth-header. Use 'Chave: Valor'.")

    if not EDITAIS_DIR.exists():
        raise SystemExit(f"Diretório não encontrado: {EDITAIS_DIR}")
    if not PRODUTOS_DIR.exists():
        raise SystemExit(f"Diretório não encontrado: {PRODUTOS_DIR}")

    editais = list_pdfs(EDITAIS_DIR)
    if not editais:
        raise SystemExit("Nenhum PDF de edital encontrado em data/editais")

    produtos_pdfs = list_pdfs(PRODUTOS_DIR)
    if not produtos_pdfs:
        print("Aviso: nenhum PDF de produto encontrado; usando um produto exemplo")
        produtos_pdfs = []

    # Escolhe o primeiro edital para a demo
    edital_pdf = editais[0]
    print(f"[edital] Usando PDF: {edital_pdf.name}")
    up = upload_edital(edital_pdf)
    if not up:
        raise SystemExit("Falha no upload e nenhum índice existente encontrado.")
    edital_id, total_chunks = up
    print(f"[edital] edital_id={edital_id}, chunks={total_chunks}")

    # Monta lista de produtos (a partir de PDFs ou um único fallback)
    produtos: List[dict] = []
    for pdf in produtos_pdfs:
        produtos.append(produto_from_datasheet(pdf))
    if not produtos:
        produtos.append({
            "nome": "Produto do Datasheet",
            "atributos": {"portas": 24, "poe": True, "gigabit": True, "gerenciavel": True},
            "origem": "exemplo"
        })

    # Ping opcional do LLM (Ollama)
    if args.ping_llm:
        try:
            llm_resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            llm_resp.raise_for_status()
            tags = llm_resp.json()
            if args.verbose:
                print("[llm] Ollama OK. Modelos instalados:", ", ".join([m.get("name", "") for m in tags.get("models", [])]))
        except Exception as e:
            print(f"[llm] Aviso: Ollama indisponível em http://localhost:11434 ({e}).")
            print("Dica: instale/inicie Ollama e o modelo desejado. Exemplos:")
            print("  - Instalar:   ollama pull llama3:latest")
            print("  - Iniciar:    ollama serve")
            print("  - Ver modelos: ollama list")

    consulta = args.consulta
    for i, prod in enumerate(produtos, start=1):
        if args.verbose:
            consulta_q = consulta.replace("'", "'\"'\"'")
            print("[debug] curl match:")
            # monta o comando com partes para evitar erro de concatenação mista
            curl_parts = [
                "curl -X POST ",
                f"'{API_BASE_URL}/editais/match/{edital_id}?consulta={consulta_q}",
            ]
            if args.model:
                curl_parts[-1] += f"&model={args.model}"
            curl_parts[-1] += "' "
            curl_parts.append("-H 'Content-Type: application/json' ")
            if args.auth_header:
                curl_parts.append(f"-H '{args.auth_header}' ")
            curl_parts.append(f"-d '{json.dumps(prod, ensure_ascii=False)}'")
            print("".join(curl_parts))

        attempt = 0
        while True:
            try:
                params = {"consulta": consulta}
                if args.model:
                    params["model"] = args.model
                r2 = requests.post(
                    f"{API_BASE_URL}/editais/match/{edital_id}",
                    params=params,
                    json=prod,
                    headers=headers,
                    timeout=args.timeout_match,
                )
                r2.raise_for_status()
                resp = r2.json()
                print(f"\n[match {i}] OK:")
                print(json.dumps(resp, ensure_ascii=False, indent=2))
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException) as e:
                attempt += 1
                # Tentar obter corpo de resposta para depuração
                body_text = ""
                try:
                    body_text = r2.text  # r2 pode não existir em timeouts/conexão
                except Exception:
                    body_text = ""
                # Mensagem específica se backend LLM está indisponível
                if body_text:
                    if "llama" in body_text.lower() or "api/generate" in body_text.lower():
                        print(f"\n[match {i}] Backend LLM indisponível. Detalhe: {body_text}")
                        print("Dica: certifique-se que o modelo está instalado e disponível no Ollama.")
                        if args.model:
                            print(f"Sugestão: ollama pull {args.model}")
                        else:
                            print("Sugestão: use --model llama3:latest ou instale o modelo padrão configurado na API.")
                if attempt > args.retries:
                    if isinstance(e, requests.exceptions.ConnectionError):
                        print(f"\n[match {i}] Falha de conexão ao endpoint.")
                    elif isinstance(e, requests.exceptions.Timeout):
                        print(f"\n[match {i}] Timeout no match.")
                    else:
                        print(f"\n[match {i}] Falha: {e}")
                    print(f"Body: {body_text}")
                    print("Dica: verifique o serviço de LLM (ex: Ollama) e o modelo configurado.")
                    break
                sleep_s = (args.backoff ** attempt)
                print(f"\n[match {i}] Tentativa {attempt}/{args.retries} após falha ({e}). Aguardando {sleep_s:.1f}s...")
                time.sleep(sleep_s)


if __name__ == "__main__":
    run()