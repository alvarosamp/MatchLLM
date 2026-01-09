from typing import Dict, Any


def _parse_key_requirements() -> tuple[list[str], str]:
    """Lê requisitos-chave do ambiente.

    - IMPORTANT_REQUIREMENTS: lista separada por vírgula/; ou espaços (ex.: "tensao_v, capacidade_ah")
    - KEY_REQUIREMENTS_POLICY: "all" (default) ou "any"
    """
    import os

    raw = str(os.getenv("IMPORTANT_REQUIREMENTS", "") or "").strip()
    policy = str(os.getenv("KEY_REQUIREMENTS_POLICY", "all") or "all").strip().lower()
    if policy not in ("all", "any"):
        policy = "all"

    if not raw:
        return [], policy

    # aceita separadores comuns
    raw = raw.replace(";", ",")
    parts = []
    for token in raw.split(","):
        tok = token.strip()
        if not tok:
            continue
        parts.append(tok)
    if not parts:
        # fallback para whitespace
        parts = [p.strip() for p in raw.split() if p.strip()]
    # normaliza duplicatas
    seen = set()
    keys: list[str] = []
    for k in parts:
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return keys, policy


def _parse_sequence_filter() -> list[str]:
    """Lê uma lista ORDENADA de requisitos para aplicar como filtro por sequência.

    Env:
      - SEQUENCE_FILTER: ex. "corrente_a, capacidade_ah, tensao_v"

    Sem essa env var, retorna lista vazia (desabilitado).
    """
    import os

    raw = str(os.getenv("SEQUENCE_FILTER", "") or "").strip()
    if not raw:
        return []
    raw = raw.replace(";", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        parts = [p.strip() for p in raw.split() if p.strip()]
    # mantém ordem, remove duplicatas
    seen = set()
    ordered: list[str] = []
    for k in parts:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered


def compute_score(matching: Dict[str, str], edital_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score baseado apenas nos requisitos do edital.
    - obrigatórios: contam para o denominador
    - opcionais: contam separadamente

    Retorna:
    {
      "score_percent": float,
      "obrigatorios_total": int,
      "obrigatorios_atende": int,
      "obrigatorios_nao_atende": int,
      "obrigatorios_duvida": int,
      "opcionais_total": int,
      "opcionais_atende": int,
      "opcionais_nao_atende": int,
      "opcionais_duvida": int,
      "status_geral": "APROVADO" | "REPROVADO" | "DUVIDOSO"
    }
    """
    reqs = edital_json.get("requisitos", {}) or {}

    obrig_total = obrig_atende = obrig_nao = obrig_duvida = 0
    opt_total = opt_atende = opt_nao = opt_duvida = 0

    for k, regra in reqs.items():
        obrigatorio = bool(regra.get("obrigatorio", True))
        status = matching.get(k, "DUVIDA")

        if obrigatorio:
            obrig_total += 1
            if status == "ATENDE":
                obrig_atende += 1
            elif status == "NAO_ATENDE":
                obrig_nao += 1
            else:
                obrig_duvida += 1
        else:
            opt_total += 1
            if status == "ATENDE":
                opt_atende += 1
            elif status == "NAO_ATENDE":
                opt_nao += 1
            else:
                opt_duvida += 1

    score = 0.0
    if obrig_total > 0:
        score = (obrig_atende / obrig_total) * 100.0

    # status geral (base, conservador)
    if obrig_total == 0:
        status_geral_base = "DUVIDOSO"
    elif obrig_nao > 0:
        status_geral_base = "REPROVADO"
    elif obrig_duvida > 0:
        status_geral_base = "DUVIDOSO"
    else:
        status_geral_base = "APROVADO"

    # Override opcional por requisitos-chave (ex.: tensao_v)
    key_reqs, policy = _parse_key_requirements()
    key_total = key_atende = key_nao = key_duvida = 0
    key_present: list[str] = []
    for k in key_reqs:
        if k in reqs:
            key_present.append(k)
            key_total += 1
            st = matching.get(k, "DUVIDA")
            if st == "ATENDE":
                key_atende += 1
            elif st == "NAO_ATENDE":
                key_nao += 1
            else:
                key_duvida += 1

    status_geral = status_geral_base
    key_override_applied = False
    if key_total > 0:
        # Regra sempre conservadora para requisitos-chave:
        # - Se algum chave NAO_ATENDE => REPROVADO
        # - Se algum chave DUVIDA => DUVIDOSO
        # - Se política "all": todos chaves ATENDE => APROVADO
        # - Se política "any": pelo menos 1 chave ATENDE (e nenhuma chave falhou/duvidosa) => APROVADO
        if key_nao > 0:
            status_geral = "REPROVADO"
            key_override_applied = True
        elif key_duvida > 0:
            status_geral = "DUVIDOSO"
            key_override_applied = True
        else:
            if policy == "any":
                if key_atende >= 1:
                    status_geral = "APROVADO"
                    key_override_applied = True
            else:  # all
                if key_atende == key_total:
                    status_geral = "APROVADO"
                    key_override_applied = True

    # Filtro por sequência (gating) opcional — tem precedência maior que key_requirements.
    seq = _parse_sequence_filter()
    seq_present: list[str] = []
    seq_steps: list[dict] = []
    seq_final = None
    seq_override_applied = False
    if seq:
        # avalia apenas os requisitos que existirem no edital
        any_present = False
        any_duvida = False
        failed = False

        for k in seq:
            if k not in reqs:
                seq_steps.append({"requisito": k, "present": False, "status": None})
                continue
            any_present = True
            seq_present.append(k)
            st = matching.get(k, "DUVIDA")
            seq_steps.append({"requisito": k, "present": True, "status": st})
            if st == "NAO_ATENDE":
                failed = True
                break
            if st == "DUVIDA":
                any_duvida = True
                # continua avaliando próximos (para diagnóstico), mas não quebra
                continue

        if any_present:
            if failed:
                seq_final = "REPROVADO"
            elif any_duvida:
                seq_final = "DUVIDOSO"
            else:
                seq_final = "APROVADO"

            status_geral = seq_final
            seq_override_applied = True

    return {
        "score_percent": round(score, 2),
        "obrigatorios_total": obrig_total,
        "obrigatorios_atende": obrig_atende,
        "obrigatorios_nao_atende": obrig_nao,
        "obrigatorios_duvida": obrig_duvida,
        "opcionais_total": opt_total,
        "opcionais_atende": opt_atende,
        "opcionais_nao_atende": opt_nao,
        "opcionais_duvida": opt_duvida,
        "status_geral": status_geral,
        "key_requirements": {
            "configured": key_reqs,
            "present_in_edital": key_present,
            "policy": policy,
            "total": key_total,
            "atende": key_atende,
            "nao_atende": key_nao,
            "duvida": key_duvida,
            "override_applied": key_override_applied,
            "base_status": status_geral_base,
        },
        "sequence_filter": {
            "configured": seq,
            "present_in_edital": seq_present,
            "steps": seq_steps,
            "final_status": seq_final,
            "override_applied": seq_override_applied,
        },
    }
