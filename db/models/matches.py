from __future__ import annotations

from sqlalchemy import Column, Integer, Text, JSON, DateTime
from sqlalchemy.sql import func

from db.base import Base


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    edital_id = Column(Integer, nullable=True)
    produto_id = Column(Integer, nullable=True)
    consulta = Column(Text, nullable=True)
    resultado_llm = Column(JSON, nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
