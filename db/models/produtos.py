from sqlalchemy import Column, Integer, String, JSON, UniqueConstraint
from database.base import Base


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True)
    fabricante = Column(String, nullable=False)
    modelo = Column(String, nullable=False)
    specs = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("fabricante", "modelo", name="uq_produto"),
    )
