from typing import Dict, Any


def _to_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # comum em PT-BR: "1,5"
        s = s.replace(" ", "")
        # remove separador de milhar quando tiver "." e ","
        if "," in s and "." in s:
            s = s.replace(".", "")
        s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None
    return None


def _norm_unit(u: str | None) -> str | None:
    if u is None:
        return None
    s = str(u).strip().lower()
    if not s:
        return None
    # normalizações comuns
    s = s.replace("/s", "ps")
    s = s.replace("mbps", "mbps")
    # remove plural e espaços
    s = s.replace(" ", "")
    # sinônimos
    alias = {
        "volts": "v",
        "volt": "v",
        "amp": "a",
        "amps": "a",
        "watt": "w",
        "watts": "w",
        "mes": "meses",
        "mês": "meses",
        "messes": "meses",
        "gb": "gb",
        "gbyte": "gb",
        "gbytes": "gb",
        "tb": "tb",
        "mb": "mb",
        "mah": "mah",
        "ah": "ah",
        "kg": "kg",
        "g": "g",
        "mm": "mm",
        "cm": "cm",
        "m": "m",
        "gbps": "gbps",
        "gbit": "gbps",
        "gbit/s": "gbps",
        "mbps": "mbps",
        "mbit": "mbps",
        "mbit/s": "mbps",
    }
    return alias.get(s, s)


def _convert_value(val: float, unit_from: str | None, unit_to: str | None) -> float | None:
    """Converte val de unit_from para unit_to quando suportado."""
    uf = _norm_unit(unit_from)
    ut = _norm_unit(unit_to)
    if uf is None or ut is None:
        return None
    if uf == ut:
        return float(val)

    # energia/potência: W <-> kW
    if (uf, ut) == ("kw", "w"):
        return float(val) * 1000.0
    if (uf, ut) == ("w", "kw"):
        return float(val) / 1000.0

    # tensão: V <-> kV
    if (uf, ut) == ("kv", "v"):
        return float(val) * 1000.0
    if (uf, ut) == ("v", "kv"):
        return float(val) / 1000.0

    # corrente: A <-> mA
    if (uf, ut) == ("ma", "a"):
        return float(val) / 1000.0
    if (uf, ut) == ("a", "ma"):
        return float(val) * 1000.0

    # capacidade: Ah <-> mAh
    if (uf, ut) == ("mah", "ah"):
        return float(val) / 1000.0
    if (uf, ut) == ("ah", "mah"):
        return float(val) * 1000.0

    # armazenamento/memória: MB/GB/TB
    storage = {"mb": 1.0, "gb": 1024.0, "tb": 1024.0 * 1024.0}
    if uf in storage and ut in storage:
        # converte para MB base
        mb = float(val) * storage[uf]
        return mb / storage[ut]

    # velocidade: Mbps <-> Gbps
    if (uf, ut) == ("gbps", "mbps"):
        return float(val) * 1000.0
    if (uf, ut) == ("mbps", "gbps"):
        return float(val) / 1000.0

    # peso: g <-> kg
    if (uf, ut) == ("g", "kg"):
        return float(val) / 1000.0
    if (uf, ut) == ("kg", "g"):
        return float(val) * 1000.0

    # comprimento: mm <-> cm <-> m
    length = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
    if uf in length and ut in length:
        mm = float(val) * length[uf]
        return mm / length[ut]

    return None


def _get_tolerance_for_key(key: str, overrides: dict | None = None) -> float:
    """Retorna tolerância percentual (0.0 a 1.0) para um requisito.

    - MATCH_TOLERANCE_PCT: ex. "5" (5%) ou "0.05" (5%)
    - MATCH_TOLERANCE_OVERRIDES: ex. "tensao_v=0.02,capacidade_ah=0.1"
    """
    import os

    if overrides and key in overrides:
        try:
            x = float(overrides[key])
            return x / 100.0 if x > 1.0 else max(0.0, x)
        except Exception:
            pass

    overrides = str(os.getenv("MATCH_TOLERANCE_OVERRIDES", "") or "").strip()
    if overrides:
        pairs = overrides.replace(";", ",").split(",")
        for p in pairs:
            if "=" not in p:
                continue
            k, v = p.split("=", 1)
            if k.strip() == key:
                try:
                    x = float(v.strip())
                    return x / 100.0 if x > 1.0 else max(0.0, x)
                except Exception:
                    break

    raw = str(os.getenv("MATCH_TOLERANCE_PCT", "0") or "0").strip()
    try:
        x = float(raw)
    except Exception:
        return 0.0
    if x > 1.0:
        x = x / 100.0
    return max(0.0, x)


class MatchingEngine:
    STATUS_ATENDE = "ATENDE"
    STATUS_NAO_ATENDE = "NAO_ATENDE"
    STATUS_DUVIDA = "DUVIDA"

    def compare(
        self,
        produto: Dict[str, Any],
        edital: Dict[str, Any],
        tolerance_overrides: dict | None = None,
    ) -> Dict[str, str]:

        resultados: Dict[str, str] = {}

        atributos_produto = produto.get("atributos", {})
        requisitos_edital = edital.get("requisitos", {})

        for requisito, regra in requisitos_edital.items():

            prod_attr = atributos_produto.get(requisito)

            # Produto não possui o atributo
            if not prod_attr:
                resultados[requisito] = (
                    self.STATUS_NAO_ATENDE
                    if regra.get("obrigatorio", True)
                    else self.STATUS_DUVIDA
                )
                continue

            valor_produto_raw = prod_attr.get("valor")
            unidade_produto = prod_attr.get("unidade")

            valor_min = regra.get("valor_min")
            valor_max = regra.get("valor_max")
            unidade_req = regra.get("unidade")

            # Valor ausente
            if valor_produto_raw is None:
                resultados[requisito] = self.STATUS_DUVIDA
                continue

            # Normaliza para float quando o requisito for numérico
            v_prod = _to_float(valor_produto_raw)
            vmin = _to_float(valor_min)
            vmax = _to_float(valor_max)

            # Se não conseguimos converter para número, não dá para comparar
            if v_prod is None:
                resultados[requisito] = self.STATUS_DUVIDA
                continue

            # Unidade incompatível (tenta conversão quando possível)
            if unidade_req and unidade_produto and _norm_unit(unidade_req) != _norm_unit(unidade_produto):
                converted = _convert_value(v_prod, unidade_produto, unidade_req)
                if converted is None:
                    resultados[requisito] = self.STATUS_DUVIDA
                    continue
                v_prod = converted

            tol = _get_tolerance_for_key(str(requisito), overrides=tolerance_overrides)

            # Mínimo (com tolerância)
            if vmin is not None:
                eff_min = vmin - (abs(vmin) * tol)
                if v_prod < eff_min:
                    resultados[requisito] = self.STATUS_NAO_ATENDE
                    continue

            # Máximo (com tolerância)
            if vmax is not None:
                eff_max = vmax + (abs(vmax) * tol)
                if v_prod > eff_max:
                    resultados[requisito] = self.STATUS_NAO_ATENDE
                    continue

            resultados[requisito] = self.STATUS_ATENDE

        return resultados


# ------------------------------------------------------------------
# Backwards-compatible API (mantém imports antigos funcionando)
# ------------------------------------------------------------------

_engine = MatchingEngine()

def compare(produto: dict, edital: dict) -> dict:
    return _engine.compare(produto, edital)

def compare_specs(produto: dict, edital: dict) -> dict:
    return _engine.compare(produto, edital)
