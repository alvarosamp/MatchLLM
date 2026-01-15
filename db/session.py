import os
from pathlib import Path
import time
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.base import Base
# Garante registro de models no metadata
import db.models  # noqa: F401


logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    # db/session.py -> db/ -> repo root
    return Path(__file__).resolve().parents[1]


def _default_sqlite_url() -> str:
    db_path = _repo_root() / "data" / "matchllm.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Migração simples (dev): se o SQLite já existe com schema antigo, faz backup.
    # No Windows, pode falhar renomear/apagar se outro processo estiver com o arquivo aberto;
    # nesse caso, usamos um novo arquivo (matchllm_v2.sqlite) para destravar.
    try:
        if db_path.exists():
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            try:
                def _table_has_integer_pk(table: str) -> bool:
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    if cur.fetchone() is None:
                        return True
                    cur.execute(f"PRAGMA table_info({table})")
                    rows = cur.fetchall() or []
                    for row in rows:
                        # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
                        if row and len(row) >= 6 and row[1] == "id":
                            col_type = (row[2] or "").strip().upper()
                            is_pk = int(row[5] or 0) == 1
                            # SQLite só autogera rowid quando é exatamente INTEGER PRIMARY KEY
                            return is_pk and col_type == "INTEGER"
                    return False

                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='produtos'")
                has_prod = cur.fetchone() is not None
                if has_prod:
                    cur.execute("PRAGMA table_info(produtos)")
                    cols = {row[1] for row in cur.fetchall() if row and len(row) > 1}
                    # Schema antigo (antes da unificação com db/schemas.sql)
                    if {"fabricante", "modelo", "specs"}.issubset(cols):
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        backup = db_path.with_name(f"matchllm.sqlite.backup_{ts}")
                        conn.close()
                        conn = None
                        try:
                            db_path.rename(backup)
                        except Exception:
                            # Fallback: se não dá pra renomear (arquivo em uso), não trava.
                            db_path = db_path.with_name("matchllm_v2.sqlite")

                # Schema incompatível com SQLite: PKs não-autoincrement (BigInteger -> BIGINT)
                # Isso causa: NOT NULL constraint failed: <tabela>.id
                needs_reset = False
                for t in ("document_cache", "match_cache", "editais", "produtos", "matches"):
                    if not _table_has_integer_pk(t):
                        needs_reset = True
                        break

                if needs_reset:
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    backup = db_path.with_name(f"matchllm.sqlite.backup_schema_{ts}")
                    conn.close()
                    conn = None
                    try:
                        db_path.rename(backup)
                    except Exception:
                        # Fallback (Windows): se o arquivo estiver em uso, usa um DB novo.
                        db_path = db_path.with_name("matchllm_v2.sqlite")
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
    except Exception:
        # Nunca falhar import/boot por causa disso
        pass

    url = f"sqlite:///{db_path}"
    try:
        logger.info("Using SQLite database at %s", db_path)
    except Exception:
        pass
    return url


# Prioriza DATABASE_URL (Docker/Postgres). Se não existir, cai para SQLite local.
DATABASE_URL = os.getenv("DATABASE_URL") or _default_sqlite_url()

try:
    logger.info("DATABASE_URL=%s", DATABASE_URL)
except Exception:
    pass

# connect_args só é necessário para SQLite.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    # create tables
    Base.metadata.create_all(bind=engine)
