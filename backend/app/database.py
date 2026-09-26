from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

database_url = (
    URL.create("postgresql+psycopg", username=settings.db_username,
               password=settings.db_password, host=settings.db_host, database=settings.db_name)
    if settings.db_host else settings.database_url
)
connect_args = {"check_same_thread": False} if str(database_url).startswith("sqlite") else {}
engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
