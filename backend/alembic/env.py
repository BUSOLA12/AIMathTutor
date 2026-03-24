"""
Alembic environment for async SQLAlchemy (asyncpg driver).

Why async matters here:
  Our engine uses "postgresql+asyncpg://..." which is an async driver.
  Alembic's default env.py calls engine.connect() synchronously, which
  fails with asyncpg. The fix is to wrap the migration runner in asyncio.run().
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# ── Alembic config object ────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import Base + all ORM models ─────────────────────────────────────────────
# The import of tables.py is what registers Session, DiagnosticResponse, etc.
# with Base.metadata so that autogenerate can see them.
from app.db.database import Base, prepare_asyncpg_url  # noqa: E402
import app.models.tables                               # noqa: E402, F401

target_metadata = Base.metadata


# ── Offline mode ─────────────────────────────────────────────────────────────
# Used when you run:  alembic upgrade head --sql
# Emits raw SQL without connecting to the database. Useful for reviewing
# migrations before running them on production.

def run_migrations_offline() -> None:
    from app.core.config import settings

    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render server defaults so the SQL output is accurate
        render_as_batch=False,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────
# Used when you run:  alembic upgrade head
# Connects to the real database and applies migrations.

def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,          # detect column type changes in autogenerate
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    from app.core.config import settings

    clean_url, connect_args = prepare_asyncpg_url(settings.database_url)
    connectable = create_async_engine(clean_url, connect_args=connect_args)

    async with connectable.connect() as connection:
        # run_sync bridges the async connection into Alembic's sync API
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
