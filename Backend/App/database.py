from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from dotenv import load_dotenv
import os
from pgvector.psycopg import register_vector
from .base import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured before starting the backend")

engine = create_engine(DATABASE_URL, echo=False, hide_parameters=True)


@event.listens_for(engine, "connect")
def _register_pgvector(dbapi_connection, _connection_record):
    if engine.dialect.name == "postgresql":
        register_vector(dbapi_connection)

SessionLocal = sessionmaker(bind=engine , autoflush=False , autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
