
"""SQLAlchemy models registry.

This module is imported for its side effects (model registration on Base.metadata).
Keep imports lightweight and avoid referencing non-existent modules.
"""

# Importa os models para registrarem no Base.metadata
from db.models.produtos import Produto  # noqa: F401

# Tabelas auxiliares (podem não existir em branches antigos)
from db.models.editais import Edital  # noqa: F401
from db.models.matches import Match  # noqa: F401
from db.models.cache import DocumentCache, MatchCache  # noqa: F401

# Auth
from db.models.users import User  # noqa: F401

