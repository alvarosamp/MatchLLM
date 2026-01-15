
# Importa os models para registrarem no Base.metadata
from db.models.produtos import Produto  # noqa: F401
from db.models.editais import Edital  # noqa: F401
from db.models.matches import Match  # noqa: F401
from db.models.cache import DocumentCache, MatchCache  # noqa: F401

