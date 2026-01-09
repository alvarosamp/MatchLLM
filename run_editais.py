from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.Pipeline.pipeline import MatchPipeline


REPO_ROOT = Path(__file__).resolve().parent
EDITAIS_DIR = REPO_ROOT / "data" / "editais"
PRODUTOS_DIR = REPO_ROOT / "data" / "produtos"


def _hr(char: str = "-", width: int = 88) -> str:
    return char * width


def _short_path(p: str | Path) -> str:
    try:
        pp = Path(p)
        return str(pp.relative_to(REPO_ROOT))
    except Exception:
        return str(p)


def _pick_product_pdf() -> Path:
    # Prefer the same default used previously
    preferred = PRODUTOS_DIR / "Produto36334IdArquivo15589.pdf"
    if preferred.exists():
        return preferred
    pdfs = sorted([p for p in PRODUTOS_DIR.glob("*.pdf") if p.is_file()])
    if not pdfs:
        raise FileNotFoundError(f"Nenhum PDF de produto encontrado em {PRODUTOS_DIR}")
    return pdfs[0]


def _summarize_result(result: Dict[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    matching: Dict[str, str] = result.get("matching") or {}
    atende = sorted([k for k, v in matching.items() if v == "ATENDE"])
    nao = sorted([k for k, v in matching.items() if v == "NAO_ATENDE"])
    duv = sorted([k for k, v in matching.items() if v == "DUVIDA"])
    return atende, nao, duv


def _format_kv(key: str, value: Any, pad: int = 26) -> str:
    k = (key + ":").ljust(pad)
    return f"{k}{value}"


def _print_report(edital_pdf: Path, produto_pdf: Path, result: Dict[str, Any], out_json: Path) -> None:
    score = result.get("score") or {}
    debug = result.get("debug") or {}
    key_req = (score.get("key_requirements") or {}) if isinstance(score, dict) else {}
    seq = (score.get("sequence_filter") or {}) if isinstance(score, dict) else {}

    atende, nao, duv = _summarize_result(result)

    title = f"RESULTADO — {edital_pdf.name}"
    print("\n" + _hr("=") )
    print(title)
    print(_hr("="))

    print(_format_kv("Edital", _short_path(edital_pdf)))
    print(_format_kv("Produto", _short_path(produto_pdf)))
    print(_format_kv("Saída JSON", _short_path(out_json)))

    print(_hr())
    print(_format_kv("Status geral", score.get("status_geral")))
    print(_format_kv("Score (%)", score.get("score_percent")))
    print(
        _format_kv(
            "Obrigatórios", f"{score.get('obrigatorios_atende')}/{score.get('obrigatorios_total')} atende"
        )
    )

    # Filtro por sequência (se configurado)
    if isinstance(seq, dict) and seq.get("configured"):
        print(_hr())
        print("Filtro por sequência")
        print(_format_kv("Configurado", seq.get("configured")))
        print(_format_kv("Presentes", seq.get("present_in_edital")))
        print(_format_kv("Final", seq.get("final_status")))
        print(_format_kv("Override aplicado", seq.get("override_applied")))
        steps = seq.get("steps") if isinstance(seq.get("steps"), list) else []
        # mostra no máximo 10 passos para não poluir
        if steps:
            preview = []
            for s in steps[:10]:
                try:
                    rk = s.get("requisito")
                    st = s.get("status")
                    pr = s.get("present")
                    preview.append(f"{rk}={'(ausente)'}" if not pr else f"{rk}={st}")
                except Exception:
                    continue
            if preview:
                print(_format_kv("Passos", ", ".join(preview)))

    # Requisitos-chave (se configurados)
    if isinstance(key_req, dict) and (key_req.get("configured") or key_req.get("present_in_edital")):
        print(_hr())
        print("Requisitos-chave")
        print(_format_kv("Configurados", key_req.get("configured")))
        print(_format_kv("Presentes", key_req.get("present_in_edital")))
        print(_format_kv("Policy", key_req.get("policy")))
        print(
            _format_kv(
                "Contagem",
                f"{key_req.get('atende')}/{key_req.get('total')} atende, {key_req.get('nao_atende')} não atende, {key_req.get('duvida')} dúvida",
            )
        )
        print(_format_kv("Override aplicado", key_req.get("override_applied")))
        print(_format_kv("Status base", key_req.get("base_status")))

    print(_hr())
    print(_format_kv("Chunks edital (total)", debug.get("edital_chunks_total")))
    print(_format_kv("Chunks usados (RAG)", debug.get("edital_chunks_usados")))
    print(_format_kv("Estratégia extração", debug.get("edital_extract_strategy")))
    if "fullscan_llm_calls" in debug:
        print(_format_kv("Fullscan LLM calls", debug.get("fullscan_llm_calls")))

    print(_hr())
    print(_format_kv("ATENDE", len(atende)))
    print(_format_kv("NÃO ATENDE", len(nao)))
    print(_format_kv("DÚVIDA", len(duv)))

    # Top itens para leitura rápida
    def _preview(items: List[str], max_n: int = 8) -> str:
        if not items:
            return "(nenhum)"
        head = items[:max_n]
        rest = len(items) - len(head)
        return ", ".join(head) + (f" (+{rest})" if rest > 0 else "")

    print(_hr())
    print(_format_kv("Exemplos ATENDE", _preview(atende)))
    print(_format_kv("Exemplos NÃO ATENDE", _preview(nao)))
    print(_format_kv("Exemplos DÚVIDA", _preview(duv)))

    # Justificativa global
    just = result.get("justificativas") or {}
    global_j = just.get("_global") if isinstance(just, dict) else None
    if global_j:
        print(_hr())
        print("Justificativa (global)")
        print(str(global_j).strip())

    print(_hr("=") )


def main() -> int:
    editais = sorted([p for p in EDITAIS_DIR.glob("*.pdf") if p.is_file()])
    if not editais:
        raise FileNotFoundError(f"Nenhum PDF encontrado em {EDITAIS_DIR}")

    produto_pdf = _pick_product_pdf()

    # Saídas por edital
    out_dir = REPO_ROOT / "resultados_e2e_local"
    out_dir.mkdir(parents=True, exist_ok=True)

    pipeline = MatchPipeline(
        top_k_edital_chunks=int(os.getenv("TOP_K_EDITAL_CHUNKS", "10")),
        enable_justification=True,
        llm_model=None,
    )

    print(_hr("="))
    print("BATCH RUN — MatchLLM")
    print(_format_kv("Editais", len(editais)))
    print(_format_kv("Produto", _short_path(produto_pdf)))
    print(_format_kv("Pasta saída", _short_path(out_dir)))
    print(_format_kv("LLM_DISABLE", os.getenv("LLM_DISABLE", "0")))
    print(_format_kv("IMPORTANT_REQUIREMENTS", os.getenv("IMPORTANT_REQUIREMENTS", "")))
    print(_format_kv("KEY_REQUIREMENTS_POLICY", os.getenv("KEY_REQUIREMENTS_POLICY", "all")))
    print(_hr("="))

    for edital_pdf in editais:
        out_json = out_dir / f"resultado__{edital_pdf.stem}.json"
        result = pipeline.run(str(edital_pdf), str(produto_pdf))
        pipeline.save_result(result, str(out_json))
        _print_report(edital_pdf, produto_pdf, result, out_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
