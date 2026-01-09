import logging
import os


def get_logger(name: str | None = None) -> logging.Logger:
    """Logger simples e estável para scripts.

    Evita falhas de import em ambientes onde não há configuração avançada.
    Controla o nível via env LOG_LEVEL (default: INFO).
    """
    level_name = str(os.getenv("LOG_LEVEL", "INFO")).upper().strip()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name or __name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)

    logger.setLevel(level)
    return logger
