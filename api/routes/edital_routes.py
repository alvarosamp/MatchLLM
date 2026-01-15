from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
import traceback
import json
from typing import List, Optional
from pathlib import Path
from api.models.edital import Produto
from api.services.edital_service import (
    processar_edital,
    rodar_match,
    extrair_requisitos,
    rodar_match_com_requisitos,
)

from api.auth.deps import get_current_user

router = APIRouter(
    prefix="/editais",
    tags=["Editais"],
    dependencies=[Depends(get_current_user)],
)

from sqlalchemy.orm import Session

from db.session import SessionLocal, init_db
from db.repositories.produto_repo import get_or_create
from db.repositories.match_repo import create_match


from pydantic import BaseModel
from core.utils.emailer import is_valid_email, send_email


class MatchMultipleRequest(BaseModel):
    produto: Produto
    edital_ids: list[int]
    consulta: str
    model: Optional[str] = None
    use_requisitos: bool = False
    email: Optional[str] = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _summarize_technical(items: list[dict]) -> str:
    """
    Gera um resumo técnico simples a partir do resultado estruturado do match.
    - Destina-se a produzir um parágrafo conciso por edital explicando quais requisitos
      o produto atende ou não, e apontando lacunas técnicas.
    """
    if not items:
        return "Nenhum requisito identificado no edital."
    atendidos = [it for it in items if str(it.get("status", "")).upper() in {"ATENDE", "SIM"}]
    nao_atendidos = [it for it in items if str(it.get("status", "")).upper() not in {"ATENDE", "SIM"}]
    parts = []
    parts.append(f"Requisitos avaliados: {len(items)}; atende: {len(atendidos)}; não atende: {len(nao_atendidos)}.")
    if atendidos:
        # pega nomes e exemplos de justificativa
        nomes = ", ".join(sorted({it.get("requisito") for it in atendidos if it.get("requisito")}))
        if nomes:
            parts.append(f"Principais requisitos atendidos: {nomes}.")
    if nao_atendidos:
        exemplos = []
        for it in nao_atendidos[:5]:
            req = it.get("requisito") or "(sem nome)"
            motivo = it.get("justificativa") or it.get("comentario") or "sem justificativa"
            exemplos.append(f"{req}: {motivo}")
        parts.append("Exemplos de não conformidade: " + "; ".join(exemplos) + ".")
    return " ".join(parts)


def _normalize_match_item(item: dict) -> dict:
    """Garante campos mínimos e formatos previsíveis para cada item retornado pelo LLM."""
    if not isinstance(item, dict):
        return {
            "requisito": "N/A",
            "valor_produto": "N/A",
            "matched_attribute": "N/A",
            "status": "DUVIDA",
            "confidence": 0.5,
            "evidence": [],
            "missing_fields": [],
            "suggested_fix": "",
            "comparacao_tecnica": {"esperado": "N/A", "observado": "N/A", "diferenca": "N/A", "motivo": "N/A"},
            "resumo_tecnico": "",
            "justificativa": "",
            "detalhes_tecnicos": {"esperado": "N/A", "observado": "N/A", "comparacao": "INDEFINIDO", "unidade": "N/A"},
        }

    it = dict(item)
    # requisito / valor / status / justificativa
    it.setdefault("requisito", "N/A")
    it.setdefault("valor_produto", "N/A")
    it.setdefault("status", "DUVIDA")
    it.setdefault("justificativa", "")

    # matched attribute
    it["matched_attribute"] = it.get("matched_attribute") or it.get("matched_attr") or "N/A"

    # confidence
    try:
        conf = float(it.get("confidence", 0.5))
    except Exception:
        conf = 0.5
    it["confidence"] = max(0.0, min(1.0, conf))

    # evidence -> list
    ev = it.get("evidence", [])
    if isinstance(ev, str):
        ev = [ev]
    if not isinstance(ev, list):
        try:
            ev = list(ev)
        except Exception:
            ev = []
    it["evidence"] = ev[:2]

    # missing fields
    mf = it.get("missing_fields", [])
    if isinstance(mf, str):
        mf = [mf]
    it["missing_fields"] = mf if isinstance(mf, list) else []

    it.setdefault("suggested_fix", "")

    # comparacao_tecnica
    ct = it.get("comparacao_tecnica") or {}
    if not isinstance(ct, dict):
        ct = {"esperado": str(ct), "observado": "N/A", "diferenca": "N/A", "motivo": "N/A"}
    ct.setdefault("esperado", "N/A")
    ct.setdefault("observado", "N/A")
    ct.setdefault("diferenca", "N/A")
    ct.setdefault("motivo", "N/A")
    it["comparacao_tecnica"] = ct

    # resumo_tecnico
    it.setdefault("resumo_tecnico", "")

    # detalhes_tecnicos
    dt = it.get("detalhes_tecnicos") or {}
    if not isinstance(dt, dict):
        dt = {}
    dt.setdefault("esperado", dt.get("esperado", "N/A"))
    dt.setdefault("observado", dt.get("observado", "N/A"))
    dt.setdefault("comparacao", dt.get("comparacao", "INDEFINIDO"))
    dt.setdefault("unidade", dt.get("unidade", "N/A"))
    it["detalhes_tecnicos"] = dt

    return it

@router.post("/upload")
async def upload_edital(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = (file.filename or "")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF.")

    try:
        init_db()
        result = processar_edital(file.file, filename=filename, db=db)
        return {
            "message": "Edital processado com sucesso.",
            "edital_id": result.get("edital_id"),
            "total_chunks": result.get("total_chunks"),
        }
    except HTTPException:
        raise
    except Exception as e:
        # Retorna detalhes do erro para facilitar diagnóstico
        raise HTTPException(status_code=500, detail=f"Falha ao processar edital: {e}")

@router.post("/match/{edital_id}")
async def match_edital(
    edital_id: int,
    produto: Produto,
    consulta: str,
    model: str | None = None,
    use_requisitos: bool = False,
    email: str | None = None,
    db: Session = Depends(get_db),
):
    """
    produto: JSON com informações técnicas
    consulta: string usada para buscar trechos relevantes (ex: "switch 24 portas poe")
    """
    try:
        init_db()

        # Persiste (ou atualiza) o produto para termos produto_id no match
        prod_rec = None
        try:
            prod_rec = get_or_create(db, nome=produto.nome, atributos_json=produto.atributos)
        except Exception:
            prod_rec = None

        if use_requisitos:
            # Tenta usar requisitos previamente extraídos; se não houver, tenta extrair primeiro
            try:
                itens = rodar_match_com_requisitos(produto, edital_id, model=model)
            except FileNotFoundError:
                _ = extrair_requisitos(edital_id, model=model)
                itens = rodar_match_com_requisitos(produto, edital_id, model=model)

            # Persiste match com resultado estruturado
            try:
                create_match(
                    db,
                    edital_id=edital_id,
                    produto_id=int(prod_rec.id) if prod_rec else None,
                    consulta=consulta,
                    resultado_llm={"resultado": itens, "modo": "requisitos"},
                )
            except Exception:
                pass
            response = {"edital_id": edital_id, "resultado": itens}
            email_sent = False
            email_error = None
            if email:
                if not is_valid_email(email):
                    email_error = "Email inválido"
                else:
                    try:
                        send_email(
                            to_email=email,
                            subject=f"MatchLLM - Resultado do match (edital_id={edital_id})",
                            body_text=(
                                f"Resultado do match para edital_id={edital_id}.\n"
                                f"Consulta: {consulta}\n\n"
                                f"O resultado estruturado está anexado como JSON."
                            ),
                            attachments=[(
                                f"match_edital_{edital_id}.json",
                                json.dumps(response, ensure_ascii=False, indent=2).encode("utf-8"),
                                "application/json",
                            )],
                        )
                        email_sent = True
                    except Exception as e:
                        email_error = str(e)
            response["email_sent"] = email_sent
            if email_error:
                response["email_error"] = email_error
            return response
        else:
            result = rodar_match(produto, edital_id, consulta, model=model)

        # Tenta normalizar o resultado como JSON estruturado e aplicar pós-processamento.
        try:
            result_json = None
            if isinstance(result, (dict, list)):
                result_json = result
            elif isinstance(result, str):
                try:
                    result_json = json.loads(result)
                except Exception:
                    # tenta extrair array/objeto de dentro da string
                    start = result.find('[')
                    end = result.rfind(']')
                    if start != -1 and end != -1 and end > start:
                        snippet = result[start:end+1]
                        try:
                            result_json = json.loads(snippet)
                        except Exception:
                            result_json = None

            # Normaliza: garante que `resultado` seja sempre uma lista (array JSON)
            if isinstance(result_json, dict):
                result_json = [result_json]

            # Aplicar pós-processamento por item para garantir campos mínimos
            if isinstance(result_json, list):
                result_json = [_normalize_match_item(it) for it in result_json]

            # Persiste match (raw + normalizado)
            try:
                create_match(
                    db,
                    edital_id=edital_id,
                    produto_id=int(prod_rec.id) if prod_rec else None,
                    consulta=consulta,
                    resultado_llm={"raw": result, "resultado": result_json},
                )
            except Exception:
                pass

            response = {"edital_id": edital_id, "resultado_llm": result, "resultado": result_json}
            email_sent = False
            email_error = None
            if email:
                if not is_valid_email(email):
                    email_error = "Email inválido"
                else:
                    try:
                        send_email(
                            to_email=email,
                            subject=f"MatchLLM - Resultado do match (edital_id={edital_id})",
                            body_text=(
                                f"Resultado do match para edital_id={edital_id}.\n"
                                f"Consulta: {consulta}\n\n"
                                f"O resultado (raw + estruturado) está anexado como JSON."
                            ),
                            attachments=[(
                                f"match_edital_{edital_id}.json",
                                json.dumps(response, ensure_ascii=False, indent=2).encode("utf-8"),
                                "application/json",
                            )],
                        )
                        email_sent = True
                    except Exception as e:
                        email_error = str(e)
            response["email_sent"] = email_sent
            if email_error:
                response["email_error"] = email_error
            return response
        except Exception as ex:
            tb = traceback.format_exc()
            # Retorna o resultado bruto e o erro para facilitar depuração, evitando 500 interno
            return {"edital_id": edital_id, "resultado_llm": result, "resultado": None, "error": str(ex), "traceback": tb}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Índice do edital não encontrado. Reprocesse o edital.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no match: {e}")

@router.get("/ids")
async def listar_editais_indexados() -> List[int]:
    """Lista os edital_id disponíveis no vectorstore para facilitar testes."""
    ids: List[int] = []
    vector_dir = Path("data/processed/vectorstore")
    if vector_dir.exists():
        for fp in vector_dir.glob("edital_*_index.pkl"):
            try:
                id_str = fp.name.replace("edital_", "").replace("_index.pkl", "")
                ids.append(int(id_str))
            except Exception:
                continue
    return sorted(ids)

@router.post("/requisitos/{edital_id}")
async def gerar_requisitos(edital_id: int, model: str | None = None, max_chunks: int = 20):
    """Extrai itens/requisitos do edital já indexado e salva em JSON."""
    try:
        # Passa max_chunks para controlar o tamanho do contexto enviado ao LLM
        from core.pipeline import extract_requisitos_edital
        info = extract_requisitos_edital(edital_id, model=model, max_chunks=max_chunks)
        return info
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Índice do edital não encontrado. Reprocesse o edital.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao extrair requisitos: {e}")



@router.post("/match_multiple")
async def match_multiple(request: "MatchMultipleRequest", db: Session = Depends(get_db)):
    """
    Roda match para múltiplos `edital_id`s e retorna uma seção por edital com explicação técnica.

    Body params:
    - produto: objeto do produto
    - edital_ids: lista de edital_id
    - consulta: texto usado para RAG/retrieval
    - model: override de modelo
    - use_requisitos: se True, usa requisitos já extraídos (ou extrai se ausente)
    """
    results = []
    try:
        init_db()

        prod_rec = None
        try:
            prod_rec = get_or_create(db, nome=request.produto.nome, atributos_json=request.produto.atributos)
        except Exception:
            prod_rec = None

        for eid in request.edital_ids:
            try:
                if request.use_requisitos:
                    try:
                        itens = rodar_match_com_requisitos(request.produto, eid, model=request.model)
                    except FileNotFoundError:
                        _ = extrair_requisitos(eid, model=request.model)
                        itens = rodar_match_com_requisitos(request.produto, eid, model=request.model)
                    result_parsed = itens
                    raw = None
                else:
                    raw = rodar_match(request.produto, eid, request.consulta, model=request.model)
                    # tenta parsear
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) else raw
                    except Exception:
                        parsed = None
                    result_parsed = parsed

                # Build a technical summary from parsed result if available
                # Normaliza: se o parsed for dict, transforma em lista para consistência
                if isinstance(result_parsed, dict):
                    result_parsed = [result_parsed]
                # Aplicar normalização por item
                if isinstance(result_parsed, list):
                    result_parsed = [_normalize_match_item(it) for it in result_parsed]

                # Persistir match no banco
                try:
                    if request.use_requisitos:
                        create_match(
                            db,
                            edital_id=eid,
                            produto_id=int(prod_rec.id) if prod_rec else None,
                            consulta=request.consulta,
                            resultado_llm={"resultado": result_parsed, "modo": "requisitos"},
                        )
                    else:
                        create_match(
                            db,
                            edital_id=eid,
                            produto_id=int(prod_rec.id) if prod_rec else None,
                            consulta=request.consulta,
                            resultado_llm={"raw": raw, "resultado": result_parsed},
                        )
                except Exception:
                    pass
                summary = _summarize_technical(result_parsed if isinstance(result_parsed, list) else (result_parsed or []))

                results.append({
                    "edital_id": eid,
                    "resultado": result_parsed,
                    "resultado_llm": raw,
                    "resumo_tecnico": summary,
                })
            except FileNotFoundError:
                results.append({"edital_id": eid, "error": "Índice não encontrado"})
        response = {"consulta": request.consulta, "produto": request.produto, "results": results}
        email_sent = False
        email_error = None
        if request.email:
            if not is_valid_email(request.email):
                email_error = "Email inválido"
            else:
                try:
                    send_email(
                        to_email=request.email,
                        subject="MatchLLM - Resultado do match (múltiplos editais)",
                        body_text=(
                            f"Resultado do match para {len(request.edital_ids)} editais.\n"
                            f"Consulta: {request.consulta}\n\n"
                            f"Os resultados estão anexados como JSON."
                        ),
                        attachments=[(
                            "match_multiple.json",
                            json.dumps(response, ensure_ascii=False, indent=2).encode("utf-8"),
                            "application/json",
                        )],
                    )
                    email_sent = True
                except Exception as e:
                    email_error = str(e)

        response["email_sent"] = email_sent
        if email_error:
            response["email_error"] = email_error

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no match múltiplo: {e}")