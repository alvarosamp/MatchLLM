from database.models.produto import Produto


def get_or_create(db, fabricante: str, modelo: str, specs: dict):
    produto = (
        db.query(Produto)
        .filter_by(fabricante=fabricante, modelo=modelo)
        .first()
    )

    if produto:
        return produto

    produto = Produto(
        fabricante=fabricante,
        modelo=modelo,
        specs=specs,
    )
    db.add(produto)
    db.commit()
    db.refresh(produto)
    return produto
