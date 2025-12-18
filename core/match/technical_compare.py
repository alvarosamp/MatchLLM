def compare(produto: dict, requisito: dict) -> dict:
    resultado = {}

    for k, req_val in requisito.items():
        prod_val = produto.get(k)

        if prod_val is None or req_val is None:
            resultado[k] = "indeterminado"
        elif prod_val >= req_val:
            resultado[k] = "atende"
        else:
            resultado[k] = "não atende"

    return resultado
