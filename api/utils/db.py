from sqlchemy import create_engine
from sqlachemy.orm import sessionmaker
from api.utils.settings import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind = engine)
