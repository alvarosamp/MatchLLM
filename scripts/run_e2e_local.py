"""Executa o pipeline E2E localmente (sem Docker).

- Carrega variáveis de ambiente do .env
- Força LLM_URL para localhost (Ollama local)
- Força um modelo pequeno por padrão para evitar OOM
- Ajusta EMBED_BATCH_SIZE para reduzir uso de memória no FastEmbed/ONNX

Uso:
  C:/Users/vish8/OneDrive/Documentos/MatchLLM/.venv/Scripts/python.exe scripts/run_e2e_local.py

Opcional:
  EMBED_BATCH_SIZE=4 LLM_MODEL=llama3.2:1b LLM_URL=http://localhost:11434 python scripts/run_e2e_local.py
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import json
from typing import Any, Dict, Iterable, List, Tuple

from dotenv import load_dotenv


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _format_rule(rule: Dict[str, Any]) -> str:
    if not isinstance(rule, dict):
        return "-"
    vmin = rule.get("valor_min")
    vmax = rule.get("valor_max")
    unidade = rule.get("unidade")
    parts: List[str] = []
    if vmin is None and vmax is None and not unidade:
        return "-"
    if vmin is not None and vmax is not None and vmin == vmax:
        parts.append(f"= {vmin}")
    else:
        if vmin is not None:
            parts.append(f">= {vmin}")
        if vmax is not None:
            parts.append(f"<= {vmax}")
    if unidade:
        parts.append(str(unidade))
    return " ".join(parts) if parts else "-"


def _format_prod_value(attr: Dict[str, Any] | None) -> str:
    if not isinstance(attr, dict):
        return "(sem atributo no produto)"
    v = attr.get("valor")
    u = attr.get("unidade")
    if v is None and not u:
        return "(valor ausente)"
    if u:
        return f"{v} {u}" if v is not None else f"(valor ausente) {u}"
    return str(v)


def _iter_editais(repo: Path) -> List[Path]:
    # Permite rodar apenas um edital específico via env.
    single = os.getenv("EDITAL_PATH")
    if single:
        p = Path(single)
        if not p.is_absolute():
            p = (repo / p).resolve()
        return [p]

    editais_dir = repo / "data" / "editais"
    pdfs = sorted(editais_dir.glob("*.pdf"))
    return pdfs


def _split_requirements(edital_json: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    reqs = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
    if not isinstance(reqs, dict):
        return [], []
    obrig: List[str] = []
    opt: List[str] = []
    for k, regra in reqs.items():
        if not isinstance(k, str):
            continue
        is_obrig = True
        if isinstance(regra, dict):
            is_obrig = bool(regra.get("obrigatorio", True))
        (obrig if is_obrig else opt).append(k)
    return sorted(obrig), sorted(opt)


def _print_result_organized(result: Dict[str, Any]) -> None:
    edital_pdf = Path(str(result.get("edital_pdf") or ""))
    produto_pdf = Path(str(result.get("produto_pdf") or ""))

    _score_raw = result.get("score")
    score = _score_raw if isinstance(_score_raw, dict) else {}

    _edital_raw = result.get("edital_json")
    edital_json = _edital_raw if isinstance(_edital_raw, dict) else {}

    _produto_raw = result.get("produto_json")
    produto_json = _produto_raw if isinstance(_produto_raw, dict) else {}

    _matching_raw = result.get("matching")
    matching = _matching_raw if isinstance(_matching_raw, dict) else {}

    _just_raw = result.get("justificativas")
    just = _just_raw if isinstance(_just_raw, dict) else {}

    reqs_raw = edital_json.get("requisitos")
    reqs = reqs_raw if isinstance(reqs_raw, dict) else {}

    attrs_raw = produto_json.get("atributos")
    attrs = attrs_raw if isinstance(attrs_raw, dict) else {}

    obrig_keys, opt_keys = _split_requirements(edital_json if isinstance(edital_json, dict) else {})

    print("=" * 90)
    print("Edital :", edital_pdf.name)
    print("Produto:", produto_pdf.name)
    print("Status geral:", (score or {}).get("status_geral"))
    print("Score (%):", (score or {}).get("score_percent"))
    print(
        "Obrigatórios:",
        f"{(score or {}).get('obrigatorios_atende')}/{(score or {}).get('obrigatorios_total')} (não={(score or {}).get('obrigatorios_nao_atende')}, dúvida={(score or {}).get('obrigatorios_duvida')})",
    )
    print(
        "Opcionais:",
        f"{(score or {}).get('opcionais_atende')}/{(score or {}).get('opcionais_total')} (não={(score or {}).get('opcionais_nao_atende')}, dúvida={(score or {}).get('opcionais_duvida')})",
    )
    print(f"Requisitos extraídos: {len(reqs)} (obrigatórios={len(obrig_keys)}, opcionais={len(opt_keys)})")

    dbg = result.get("debug") if isinstance(result.get("debug"), dict) else {}
    if dbg:
        print("Debug:", dbg)
    if not reqs:
        print("Aviso: nenhum requisito técnico foi extraído deste edital.")

    def _print_group(title: str, keys: Iterable[str]) -> None:
        keys = list(keys)
        if not keys:
            return
        print("\n" + title)
        for k in keys:
            regra = reqs.get(k, {}) if isinstance(reqs, dict) else {}
            status = matching.get(k, "DUVIDA")
            prod_attr = attrs.get(k) if isinstance(attrs, dict) else None
            line = f"- {k}: {status} | regra: {_format_rule(regra)} | produto: {_format_prod_value(prod_attr)}"
            print(line)
            j = just.get(k)
            if isinstance(j, str) and j.strip():
                print(f"  justificativa: {j}")

    _print_group("Obrigatórios", obrig_keys)
    _print_group("Opcionais", opt_keys)

    # Imprime justificativas que não estão ligadas a um requisito específico.
    extras = {k: v for k, v in just.items() if k not in reqs} if isinstance(just, dict) else {}
    if extras:
        print("\nJustificativas extras")
        for k, v in extras.items():
            if isinstance(v, str) and v.strip():
                print(f"- {k}: {v}")


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    # Garante imports do pacote local `core` quando executado via `python scripts/...`.
    sys.path.insert(0, str(repo))

    from core.Pipeline.pipeline import MatchPipeline
    load_dotenv(repo / ".env")

    # Defaults seguros para execução local.
    # Por padrão, sobrescreve LLM_URL/LLM_MODEL para evitar:
    # - LLM_URL apontando para 'ollama' (hostname do docker-compose)
    # - OOM em modelos grandes
    # Para respeitar o .env, defina RUN_E2E_USE_ENV_LLM=1.
    # Se o usuário já definiu LLM_URL/LLM_MODEL no ambiente, respeita automaticamente.
    has_llm_env = bool(os.getenv("LLM_URL")) or bool(os.getenv("LLM_MODEL"))
    use_env_llm = has_llm_env or (str(os.getenv("RUN_E2E_USE_ENV_LLM", "0")).lower() in ("1", "true", "yes"))
    if not use_env_llm:
        os.environ["LLM_URL"] = "http://localhost:11434"
        os.environ["LLM_MODEL"] = "llama3.2:1b"
    os.environ.setdefault("EMBED_BATCH_SIZE", "4")

    # OCR é local (PaddleOCR / extração nativa). Não há mais fallback/força via Gemini.

    # Ajuda o Ollama a retornar JSON parseável nos extratores
    os.environ.setdefault("LLM_FORCE_JSON", "1")

    # Contexto um pouco maior para não truncar prompts (ajuste conforme sua máquina)
    os.environ.setdefault("LLM_NUM_CTX", "4096")

    # Estratégia de extração do edital:
    # - rag_then_full (default): tenta RAG e, se não extrair nada, varre o edital inteiro por chunks
    # - fullscan: sempre varre o edital inteiro (mais lento, mas cobre tudo)
    os.environ.setdefault("EDITAL_EXTRACT_STRATEGY", "rag_then_full")

    produto_path = Path(os.getenv("PRODUTO_PATH") or (repo / "data/produtos/Produto36334IdArquivo15589.pdf"))
    if not produto_path.is_absolute():
        produto_path = (repo / produto_path).resolve()

    editais = _iter_editais(repo)
    if not editais:
        raise FileNotFoundError("Nenhum PDF encontrado em data/editais (ou EDITAL_PATH inválido).")

    pipeline = MatchPipeline(
        top_k_edital_chunks=int(os.getenv("TOP_K_EDITAL_CHUNKS", "20")),
        enable_justification=True,
        llm_model=None,
    )

    out_dir = repo / "resultados_e2e_local"
    out_dir.mkdir(parents=True, exist_ok=True)

    print_json = _is_truthy(os.getenv("RUN_E2E_PRINT_JSON", "1"))

    for edital_path in editais:
        result = pipeline.run(str(edital_path), str(produto_path))
        out_path = out_dir / f"resultado__{edital_path.stem}.json"
        pipeline.save_result(result, str(out_path))

        # Arquivos auxiliares para inspeção rápida dos JSONs intermediários
        try:
            import json as _json

            (out_dir / f"produto_json__{edital_path.stem}.json").write_text(
                _json.dumps(result.get("produto_json", {}), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (out_dir / f"edital_json__{edital_path.stem}.json").write_text(
                _json.dumps(result.get("edital_json", {}), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        _print_result_organized(result)
        print("Arquivo gerado:", out_path)

        if print_json:
            try:
                print("\nJSON: produto_json")
                print(json.dumps(result.get("produto_json", {}), ensure_ascii=False, indent=2))
                print("\nJSON: edital_json")
                print(json.dumps(result.get("edital_json", {}), ensure_ascii=False, indent=2))
                print("\nJSON: resultado (matching/score/justificativas/debug)")
                compact = {
                    "score": result.get("score"),
                    "matching": result.get("matching"),
                    "justificativas": result.get("justificativas"),
                    "debug": result.get("debug"),
                }
                print(json.dumps(compact, ensure_ascii=False, indent=2))
            except Exception as e:
                print("(Falha ao imprimir JSONs no console)", e)


if __name__ == "__main__":
    main()
