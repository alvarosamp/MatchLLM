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

# Ajusta caminho para permitir importar módulos 'core' quando executado via python teste/runner.py
import sys
from pathlib import Path as _Path
_REPO_ROOT_BOOT = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_BOOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOT))

import os
import json
from pathlib import Path
from typing import Optional, List
import requests
import argparse
import time
import json as jsonlib
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse
from core.logging_config import get_logger

logger = get_logger(__name__)


# Importa componentes para ler e interpretar datasheets
from core.ocr.extractor import PDFExtractor
from core.ocr.normalizador import normalize_text
from core.preprocess.product_extractor import ProductExtractor


REPO_ROOT = Path(__file__).resolve().parents[1]
# Carrega variáveis do .env (sem sobrescrever existentes)
load_dotenv(dotenv_path=str(REPO_ROOT / ".env"), override=False)
EDITAIS_DIR = REPO_ROOT / "data" / "editais"
PRODUTOS_DIR = REPO_ROOT / "data" / "produtos"
VECTOR_DIR = REPO_ROOT / "data" / "processed" / "vectorstore"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _sanitize_api_base(url: str) -> str:
    """Se o host for 'api' (nome de serviço Docker), troca por localhost.
    Mantém esquema e porta. Não altera se o host não for 'api'.
    """
    try:
        parsed = urlparse(url)
        if parsed.hostname in {"api", "api.local"}:
            netloc = f"localhost:{parsed.port or 8000}"
            return urlunparse((parsed.scheme or "http", netloc, parsed.path or "", parsed.params or "", parsed.query or "", parsed.fragment or ""))
    except Exception:
        pass
    return url


def list_pdfs(folder: Path) -> List[Path]:
    return [p for p in sorted(folder.glob("*.pdf")) if p.is_file()]


def list_jsons(folder: Path) -> List[Path]:
    return [p for p in sorted(folder.glob("*.json")) if p.is_file()]


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
        logger.exception("[upload] HTTPError")
        # fallback: usa índice existente
        ids = list_index_ids()
        if ids:
            return ids[-1], None
        return None
    except requests.exceptions.RequestException as e:
        logger.exception("[upload] erro de requisição")
        return None
    except ValueError:
        logger.exception("[upload] resposta não é JSON válida")
        return None


def produto_from_datasheet(pdf: Path) -> dict:
    """
    Lê o PDF do datasheet, normaliza, e extrai atributos via LLM (ProductExtractor).
    Se a extração falhar ou não retornar JSON válido, cai para um template simples.
    """
    extractor = PDFExtractor()
    try:
        raw_text = extractor.extract(str(pdf))
    except Exception as e:
        logger.exception("[produto] Falha ao ler datasheet %s", pdf.name)
        raw_text = ""
    norm_text = normalize_text(raw_text or "")

    def _parse_resp(resp):
        if isinstance(resp, str):
            try:
                return jsonlib.loads(resp)
            except Exception:
                return None
        if isinstance(resp, dict):
            return resp
        return None

    def _missing_ratio(attrs: dict) -> float:
        # Considera ausente: None, "", "N/A", dict vazio/todos nulos, lista vazia
        def is_missing(v) -> bool:
            if v is None:
                return True
            if isinstance(v, str) and v.strip().upper() in {"", "N/A", "NA", "NULL"}:
                return True
            if isinstance(v, list):
                return len(v) == 0
            if isinstance(v, dict):
                # ausente se todos os subcampos forem ausentes
                if not v:
                    return True
                return all(is_missing(sv) for sv in v.values())
            return False

        if not isinstance(attrs, dict) or not attrs:
            return 1.0
        total = 0
        missing = 0
        for v in attrs.values():
            total += 1
            if is_missing(v):
                missing += 1
        return missing / max(total, 1)

    # Tenta extrair atributos com LLM (primeira passada)
    try:
        pe = ProductExtractor()
        resp1 = pe.extract(norm_text)
        data1 = _parse_resp(resp1)
        if isinstance(data1, dict) and "atributos" in data1:
            miss1 = _missing_ratio(data1.get("atributos") or {})
            # Se muitos campos ausentes e Gemini disponível, tenta OCR Gemini
            use_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
            if miss1 >= 0.7 and use_gemini:
                try:
                    logger.info("[produto] Muitos campos ausentes (>=70%). Tentando OCR via Gemini...")
                    extractor_g = PDFExtractor()
                    raw_text2 = extractor_g.extract_text_gemini(str(pdf), log_label="doc")
                    norm_text2 = normalize_text(raw_text2 or "")
                    resp2 = pe.extract(norm_text2)
                    data2 = _parse_resp(resp2)
                    if isinstance(data2, dict) and "atributos" in data2:
                        miss2 = _missing_ratio(data2.get("atributos") or {})
                        if miss2 <= miss1:
                            data1 = data2
                            miss1 = miss2
                            if os.getenv("RUNNER_VERBOSE"):
                                logger.info("[produto] OCR Gemini melhorou preenchimento: %.0f%% ausentes", miss1*100)
                except Exception as e2:
                    logger.exception("[produto] OCR via Gemini falhou: %s", e2)

            return {
                "nome": data1.get("nome") or pdf.stem,
                "atributos": data1.get("atributos") or {},
                "origem": pdf.name,
            }
    except Exception as e:
        # Em erro do LLM, tenta OCR via Gemini e reexecuta a extração com LLM
        use_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        if use_gemini:
            try:
                logger.info("[produto] Extração via LLM falhou: %s. Tentando OCR via Gemini...", e)
                raw_text2 = PDFExtractor().extract_text_gemini(str(pdf), log_label="doc")
                norm_text2 = normalize_text(raw_text2 or "")
                pe = ProductExtractor()
                resp2 = pe.extract(norm_text2)
                data2 = _parse_resp(resp2)
                if isinstance(data2, dict) and "atributos" in data2:
                    return {
                        "nome": data2.get("nome") or pdf.stem,
                        "atributos": data2.get("atributos") or {},
                        "origem": pdf.name,
                    }
            except Exception as e2:
                logger.exception("[produto] OCR via Gemini também falhou: %s", e2)
        else:
            logger.exception("[produto] Extração de atributos via LLM falhou: %s", e)

    # Fallback simples
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


def produto_from_json(fp: Path) -> Optional[dict]:
    try:
        data = jsonlib.loads(fp.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if "origem" not in data:
                data["origem"] = fp.name
            return data
    except Exception as e:
        print(f"[produto] Falha ao ler JSON {fp.name}: {e}")
    return None


def run() -> None:
    # Args CLI
    parser = argparse.ArgumentParser(description="Runner automático de upload + match")
    parser.add_argument("--consulta", type=str, default="switch 24 portas poe", help="Consulta para o match")
    parser.add_argument("--timeout-upload", type=int, default=120, help="Timeout (s) para upload")
    # Aumenta o timeout padrão do match para cenários com OCR + RAG + LLM
    parser.add_argument("--timeout-match", type=int, default=300, help="Timeout (s) para match")
    parser.add_argument("--no-timeout", dest="no_timeout", action="store_true", help="Desativa timeouts de upload e match (pode travar em caso de erro)")
    parser.add_argument("--retries", type=int, default=2, help="Tentativas extras para match em caso de falha (500/timeout/conexão)")
    parser.add_argument("--backoff", type=float, default=2.0, help="Fator de backoff exponencial entre tentativas")
    parser.add_argument("--auth-header", type=str, default=None, help="Cabeçalho de autorização (ex: 'Authorization: Bearer XXX')")
    parser.add_argument("--verbose", "-v", action="store_true", help="Saída detalhada (inclui curl)")
    # Novo: escolher modelo e ping do LLM local (Ollama)
    parser.add_argument("--model", type=str, default=None, help="Modelo de LLM a ser usado no match (ex: 'llama3:latest')")
    parser.add_argument("--ping-llm", action="store_true", help="Verifica Ollama em http://localhost:11434 antes de rodar")
    parser.add_argument("--extract-requisitos", action="store_true", help="Extrai requisitos do edital antes do match e usa 'use_requisitos=true'")
    parser.add_argument("--max-chunks", type=int, default=20, help="Máximo de chunks do edital para extrair requisitos (default=20)")
    parser.add_argument("--materializar-json", action="store_true", help="Gera JSONs de produtos a partir de PDFs em data/produtos antes do match")
    # Controle de upload/índice existente
    parser.add_argument("--skip-upload", action="store_true", help="Não faz upload; usa índice existente em data/processed/vectorstore")
    parser.add_argument("--edital-id", type=int, default=None, help="Usa um edital_id já indexado (ex: 12345); requer que o índice exista")
    parser.add_argument("--edital-pdf", type=str, default=None, help="Caminho de um PDF específico de edital para upload; ignora varredura da pasta")
    parser.add_argument("--produto-json", type=str, default=None, help="Caminho para um JSON de produto em data/produtos (prioriza sobre datasheet PDF)")
    args = parser.parse_args()

    # Corrige base da API se estiver usando host do Docker (api:8000)
    global API_BASE_URL
    api_before = API_BASE_URL
    API_BASE_URL = _sanitize_api_base(API_BASE_URL).rstrip("/")
    if api_before != API_BASE_URL:
        print(f"[runner] Aviso: API_BASE_URL ajustado de '{api_before}' para '{API_BASE_URL}'.")

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
    if args.edital_pdf:
        ep = Path(args.edital_pdf)
        if not ep.exists():
            raise SystemExit(f"Arquivo de edital não encontrado: {ep}")
        editais = [ep]
    if not editais and not (args.skip_upload or args.edital_id):
        raise SystemExit("Nenhum PDF de edital encontrado em data/editais e nenhum índice existente especificado.")

    # Seleção de produtos: prioriza JSONs salvos de datasheets; senão tenta PDF+LLM; senão fallback
    produtos: List[dict] = []
    if args.produto_json:
        pjson = Path(args.produto_json)
        if not pjson.exists():
            raise SystemExit(f"Produto JSON especificado não existe: {pjson}")
        pj = produto_from_json(pjson)
        if pj:
            produtos.append(pj)
        else:
            print("[produto] JSON inválido; tentando datasheets da pasta...")
    else:
        produtos_json = list_jsons(PRODUTOS_DIR)
        for fp in produtos_json:
            pj = produto_from_json(fp)
            if pj:
                produtos.append(pj)
        if not produtos:
            produtos_pdfs = list_pdfs(PRODUTOS_DIR)
            if not produtos_pdfs:
                print("Aviso: nenhum JSON ou PDF de produto encontrado; usando um produto exemplo")
            else:
                for pdf in produtos_pdfs:
                    produtos.append(produto_from_datasheet(pdf))

    # Escolhe o primeiro edital para a demo
    # Seleção de edital: usar índice existente se solicitado
    if args.edital_id:
        # Verifica se o índice existe
        idx_path = VECTOR_DIR / f"edital_{args.edital_id}_index.pkl"
        if not idx_path.exists():
            raise SystemExit(f"Índice para edital_id {args.edital_id} não encontrado em {idx_path}.")
        edital_id = args.edital_id
        total_chunks = None
        print(f"[edital] Usando índice existente: edital_id={edital_id}")
    elif args.skip_upload:
        ids_existentes = list_index_ids()
        if not ids_existentes:
            raise SystemExit("Nenhum índice existente encontrado em data/processed/vectorstore. Remova --skip-upload ou informe --edital-pdf.")
        edital_id = ids_existentes[-1]
        total_chunks = None
        print(f"[edital] Usando último índice existente: edital_id={edital_id}")
    else:
        edital_pdf = editais[0]
        print(f"[edital] Usando PDF: {edital_pdf.name}")
        up = upload_edital(edital_pdf)
        if not up:
            raise SystemExit("Falha no upload e nenhum índice existente encontrado.")
        edital_id, total_chunks = up
        print(f"[edital] edital_id={edital_id}, chunks={total_chunks}")

    # Monta lista de produtos (a partir de PDFs ou um único fallback)
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

    # Se solicitado, materializa JSONs de datasheets
    if args.materializar_json:
        pdfs = list_pdfs(PRODUTOS_DIR)
        for pdf in pdfs:
            try:
                prod = produto_from_datasheet(pdf)
                out = PRODUTOS_DIR / f"{pdf.stem}.json"
                out.write_text(json.dumps(prod, ensure_ascii=False, indent=2), encoding="utf-8")
                if args.verbose:
                    print(f"[produto] JSON gerado: {out.name}")
            except Exception as e:
                print(f"[produto] Falha ao materializar {pdf.name}: {e}")

    # Se solicitado, extrai requisitos via API
    if args.extract_requisitos:
        try:
            params = {"model": args.model} if args.model else {}
            if args.max_chunks:
                params["max_chunks"] = str(args.max_chunks)
            resp = requests.post(f"{API_BASE_URL}/editais/requisitos/{edital_id}", params=params, timeout=None if args.no_timeout else args.timeout_match)
            resp.raise_for_status()
            info = resp.json()
            if args.verbose:
                print("[requisitos] extraídos:", json.dumps(info, ensure_ascii=False))
        except Exception as e:
            print(f"[requisitos] Falha ao extrair: {e}")

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
                if args.extract_requisitos:
                    params["use_requisitos"] = True
                # Timeout: permite desativar se --no-timeout
                req_timeout = None if args.no_timeout else args.timeout_match
                r2 = requests.post(
                    f"{API_BASE_URL}/editais/match/{edital_id}",
                    params=params,
                    json=prod,
                    headers=headers,
                    timeout=req_timeout,
                )
                r2.raise_for_status()
                resp = r2.json()
                print(f"\n[match {i}] OK:")
                # Preferir resultado estruturado se o backend forneceu
                if isinstance(resp, dict) and ("resultado" in resp or "resultado_llm" in resp):
                    parsed = resp.get("resultado")
                    raw = resp.get("resultado_llm")
                    if parsed is not None:
                        print("Resultado estruturado:")
                        print(json.dumps(parsed, ensure_ascii=False, indent=2))
                    else:
                        # Tentar parsear o bruto para melhorar a leitura
                        try:
                            raw_parsed = json.loads(raw) if isinstance(raw, str) else raw
                            print("Resultado (parseado do bruto):")
                            print(json.dumps(raw_parsed, ensure_ascii=False, indent=2))
                        except Exception:
                            print("Resultado bruto:")
                            print(raw)
                else:
                    # Resposta antiga: imprime como veio
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