"""
database.py
-----------
Sets up the SQLAlchemy engine, session factory, declarative Base, and
the get_db FastAPI dependency.

All connection details are loaded from the .env file via python-dotenv
so that no credentials are hard-coded here.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Load variables from the .env file that lives next to this project root
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add it to your .env file, e.g.:\n"
        "  DATABASE_URL=postgresql://user:pass@localhost:5432/expense_db"
    )

# create_engine is the starting point for any SQLAlchemy application.
# pool_pre_ping=True tells SQLAlchemy to test the connection before using
# it from the pool, which avoids stale-connection errors on long-idle services.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# sessionmaker returns a *factory* that we call to get a new Session each time.
# autocommit=False  – we control when to commit explicitly
# autoflush=False   – prevents SQLAlchemy from auto-flushing before queries
#                     (lets us batch multiple changes before a single flush)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    Single declarative base that all models will inherit from.
    SQLAlchemy 2.0 style: subclass DeclarativeBase instead of
    calling declarative_base().
    """
    pass


def get_db():
    """
    FastAPI dependency that yields a database session per request.

    The try/finally block guarantees the session is always closed even
    if an exception occurs inside the route handler, preventing
    connection-pool exhaustion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
