from typing import Dict, Any


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

    # status geral (conservador)
    if obrig_total == 0:
        status_geral = "DUVIDOSO"
    elif obrig_nao > 0:
        status_geral = "REPROVADO"
    elif obrig_duvida > 0:
        status_geral = "DUVIDOSO"
    else:
        status_geral = "APROVADO"

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
    }
