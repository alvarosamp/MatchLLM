from db.models.produtos import Produto


def get_or_create(
    db,
    *,
    nome: str | None = None,
    atributos_json: dict | None = None,
    # compat: chamadas antigas
    fabricante: str | None = None,
    modelo: str | None = None,
    specs: dict | None = None,
):
    """Cria (ou retorna) um produto.

    Schema (db/schemas.sql): produtos(nome, atributos_json, criado_em)

    Compatibilidade:
    - Se vierem `fabricante`/`modelo`/`specs`, mapeia para:
      nome = f"{fabricante} {modelo}" e atributos_json = specs
    """

    if (nome is None or not str(nome).strip()) and (fabricante or modelo):
        nome = f"{fabricante or ''} {modelo or ''}".strip() or None
    if atributos_json is None and specs is not None:
        atributos_json = specs

    produto = None
    if nome:
        produto = db.query(Produto).filter_by(nome=nome).first()
    if produto:
        # Atualiza atributos se vierem novos
        if isinstance(atributos_json, dict) and atributos_json and atributos_json != (produto.atributos_json or {}):
            produto.atributos_json = atributos_json
            db.add(produto)
            db.commit()
            db.refresh(produto)
        return produto

    produto = Produto(
        nome=nome,
        atributos_json=atributos_json or {},
    )
    db.add(produto)
    db.commit()
    db.refresh(produto)
    return produto
