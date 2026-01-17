from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.sql import func
from db.base import Base


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String, nullable=True)
    atributos_json = Column(JSON, nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
