from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.base import Base
from pathlib import Path

# Simple SQLite file in the repo (development only)
DB_PATH = Path("data") / "matchllm.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    # create tables
    Base.metadata.create_all(bind=engine)
