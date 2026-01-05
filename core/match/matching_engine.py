from typing import Dict, Any


class MatchingEngine:
    STATUS_ATENDE = "ATENDE"
    STATUS_NAO_ATENDE = "NAO_ATENDE"
    STATUS_DUVIDA = "DUVIDA"

    def compare(
        self,
        produto: Dict[str, Any],
        edital: Dict[str, Any]
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

            valor_produto = prod_attr.get("valor")
            unidade_produto = prod_attr.get("unidade")

            valor_min = regra.get("valor_min")
            valor_max = regra.get("valor_max")
            unidade_req = regra.get("unidade")

            # Valor ausente
            if valor_produto is None:
                resultados[requisito] = self.STATUS_DUVIDA
                continue

            # Unidade incompatível
            if unidade_req and unidade_produto and unidade_req != unidade_produto:
                resultados[requisito] = self.STATUS_DUVIDA
                continue

            # Mínimo
            if valor_min is not None and valor_produto < valor_min:
                resultados[requisito] = self.STATUS_NAO_ATENDE
                continue

            # Máximo
            if valor_max is not None and valor_produto > valor_max:
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
