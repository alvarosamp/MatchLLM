from db.models.matches import Match


def create_match(
    db,
    *,
    edital_id: int | None,
    produto_id: int | None,
    consulta: str | None,
    resultado_llm: dict | list | str | None,
):
    rec = Match(
        edital_id=edital_id,
        produto_id=produto_id,
        consulta=consulta,
        resultado_llm=resultado_llm,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
