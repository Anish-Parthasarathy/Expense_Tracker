"""
alembic/env.py
--------------
Alembic environment configuration.

Key decisions:
 1. We load DATABASE_URL from the .env file (via python-dotenv) so that
    credentials are never stored in alembic.ini.
 2. We set target_metadata to our SQLAlchemy Base.metadata so that Alembic
    can *autogenerate* migration scripts by comparing the DB schema to the
    ORM models (run: alembic revision --autogenerate -m "message").
"""

import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# Load environment variables from the project root .env
load_dotenv()

# this is the Alembic Config object, which provides access to the values
# within the alembic.ini file.
config = context.config

# Interpret the config file for Python logging. This line sets up loggers
# basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the placeholder sqlalchemy.url with the real one from .env
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

# Import Base *after* setting the URL to avoid circular imports
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402  – side-effect: registers models with Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
