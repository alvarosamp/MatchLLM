def compare(produto: dict, requisito: dict) -> dict:
    resultado = {}

    for k, req_val in requisito.items():
        prod_val = produto.get(k)

        if prod_val is None or req_val is None:
            resultado[k] = "indeterminado"
        elif isinstance(prod_val, (int, float)) and isinstance(req_val, (int, float)) and prod_val >= req_val:
            resultado[k] = "atende"
        else:
            resultado[k] = "não atende"

    return resultado


# Backwards-compatible alias expected by older modules
def compare_specs(produto: dict, requisito: dict) -> dict:
    """Compatibiliza import name 'compare_specs' usado em other modules."""
    return compare(produto, requisito)
