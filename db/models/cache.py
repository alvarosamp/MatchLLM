from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from db.base import Base


class DocumentCache(Base):
    __tablename__ = "document_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_type = Column(String(32), nullable=False)
    sha256 = Column(String(64), nullable=False)
    hint_key = Column(Text, nullable=True)
    original_name = Column(Text, nullable=True)
    extracted_json = Column(JSON, nullable=False)
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("doc_type", "sha256", "hint_key", name="uq_document_cache_type_hash_hint"),
    )


class MatchCache(Base):
    __tablename__ = "match_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    edital_sha256 = Column(String(64), nullable=False)
    produto_sha256 = Column(String(64), nullable=False)
    settings_sig = Column(Text, nullable=False)
    result_json = Column(JSON, nullable=False)
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "edital_sha256",
            "produto_sha256",
            "settings_sig",
            name="uq_match_cache_pair_settings",
        ),
    )
