from __future__ import annotations

import os
import sys
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


def _clean_text(s: str, max_len: int = 420) -> str:
    t = str(s or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    t = " ".join(t.split())
    if len(t) > max_len:
        t = t[: max_len - 3].rstrip() + "..."
    return t


def _first_sequence_failure(seq: dict) -> str | None:
    steps = seq.get("steps") if isinstance(seq, dict) else None
    if not isinstance(steps, list):
        return None
    for s in steps:
        if not isinstance(s, dict):
            continue
        if s.get("present") and s.get("status") == "NAO_ATENDE":
            return str(s.get("requisito"))
    return None


def _print_report(edital_pdf: Path, produto_pdf: Path, result: Dict[str, Any], out_json: Path) -> None:
    score = result.get("score") or {}
    key_req = (score.get("key_requirements") or {}) if isinstance(score, dict) else {}
    seq = (score.get("sequence_filter") or {}) if isinstance(score, dict) else {}

    atende, nao, duv = _summarize_result(result)

    # Cabeçalho compacto
    print("\n" + _hr("="))
    print(f"EDITAL: {edital_pdf.name}")
    print(_hr("="))
    print(_format_kv("Status", score.get("status_geral")))
    print(_format_kv("Score", f"{score.get('score_percent')}%"))
    print(_format_kv("Obrigatórios", f"{score.get('obrigatorios_atende')}/{score.get('obrigatorios_total')} atende"))

    # Gate por sequência (se configurado)
    if isinstance(seq, dict) and seq.get("configured"):
        first_fail = _first_sequence_failure(seq)
        gate_msg = f"final={seq.get('final_status')} override={seq.get('override_applied')}"
        if first_fail:
            gate_msg += f" | 1ª falha: {first_fail}"
        print(_format_kv("Filtro sequência", gate_msg))

    # Requisitos-chave (se configurado)
    if isinstance(key_req, dict) and key_req.get("present_in_edital"):
        print(
            _format_kv(
                "Reqs-chave",
                f"policy={key_req.get('policy')} {key_req.get('atende')}/{key_req.get('total')} atende (override={key_req.get('override_applied')})",
            )
        )

    print(_format_kv("ATENDE/NAO/DÚVIDA", f"{len(atende)}/{len(nao)}/{len(duv)}"))

    # Top itens para leitura rápida
    def _preview(items: List[str], max_n: int = 3) -> str:
        if not items:
            return "(nenhum)"
        head = items[:max_n]
        rest = len(items) - len(head)
        return ", ".join(head) + (f" (+{rest})" if rest > 0 else "")

    print(_format_kv("Exemplos (ATENDE)", _preview(atende)))
    print(_format_kv("Exemplos (NÃO)", _preview(nao)))
    print(_format_kv("Exemplos (DÚVIDA)", _preview(duv)))

    # Justificativa global
    just = result.get("justificativas") or {}
    global_j = just.get("_global") if isinstance(just, dict) else None
    if global_j:
        print(_format_kv("Motivo", _clean_text(global_j)))

    print(_format_kv("Arquivo", _short_path(out_json)))
    print(_hr("="))


def main() -> int:
    # Melhora encoding no Windows Terminal/PowerShell (evita "nÃ£o" etc.)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

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
    print("MATCHLLM — Execução em lote")
    print(_format_kv("Editais", len(editais)))
    print(_format_kv("Produto", _short_path(produto_pdf)))
    print(_format_kv("Saída", _short_path(out_dir)))
    print(_format_kv("Modo", "OFFLINE" if os.getenv("LLM_DISABLE", "0") in ("1", "true", "yes") else "COM LLM"))
    seq_cfg = os.getenv("SEQUENCE_FILTER", "").strip()
    if seq_cfg:
        print(_format_kv("SEQUENCE_FILTER", seq_cfg))
    key_cfg = os.getenv("IMPORTANT_REQUIREMENTS", "").strip()
    if key_cfg:
        print(_format_kv("IMPORTANT_REQUIREMENTS", key_cfg))
        print(_format_kv("KEY_REQUIREMENTS_POLICY", os.getenv("KEY_REQUIREMENTS_POLICY", "all")))
    tol = os.getenv("MATCH_TOLERANCE_PCT", "").strip()
    if tol:
        print(_format_kv("MATCH_TOLERANCE_PCT", tol))
    tol2 = os.getenv("MATCH_TOLERANCE_OVERRIDES", "").strip()
    if tol2:
        print(_format_kv("MATCH_TOLERANCE_OVERRIDES", tol2))
    print(_hr("="))

    for edital_pdf in editais:
        out_json = out_dir / f"resultado__{edital_pdf.stem}.json"
        result = pipeline.run(str(edital_pdf), str(produto_pdf))
        pipeline.save_result(result, str(out_json))
        _print_report(edital_pdf, produto_pdf, result, out_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
