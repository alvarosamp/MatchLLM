from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from db.base import Base


class Edital(Base):
    __tablename__ = "editais"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String, nullable=True)
    caminho_pdf = Column(Text, nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
