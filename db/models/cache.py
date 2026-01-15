from __future__ import annotations

from sqlalchemy import Column, Integer, String, JSON, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from db.base import Base


class DocumentCache(Base):
    __tablename__ = "document_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_type = Column(String, nullable=False)  # 'produto' | 'edital'
    sha256 = Column(String(64), nullable=False)
    hint_key = Column(String, nullable=True)  # usado para edital multi-item (depende do produto_hint)
    original_name = Column(String, nullable=True)

    extracted_json = Column(JSON, nullable=False)
    meta_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("doc_type", "sha256", "hint_key", name="uq_document_cache_type_hash_hint"),
    )


class MatchCache(Base):
    __tablename__ = "match_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    edital_sha256 = Column(String(64), nullable=False)
    produto_sha256 = Column(String(64), nullable=False)
    settings_sig = Column(String, nullable=False)  # assinatura estável da config usada

    result_json = Column(JSON, nullable=False)
    meta_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("edital_sha256", "produto_sha256", "settings_sig", name="uq_match_cache_pair_settings"),
    )
