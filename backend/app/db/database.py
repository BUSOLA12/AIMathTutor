from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def prepare_asyncpg_url(raw_url: str) -> tuple[str, dict]:
    """
    asyncpg doesn't accept psycopg2-style URL params (sslmode, channel_binding).
    Strip them and return (clean_url, connect_args) where connect_args carries ssl=True
    when sslmode was require/verify-full/verify-ca.
    """
    parsed = urlparse(raw_url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    sslmode = params.pop("sslmode", [""])[0]
    params.pop("channel_binding", None)

    needs_ssl = sslmode in ("require", "verify-full", "verify-ca")
    new_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url = urlunparse(parsed._replace(query=new_query))

    return clean_url, ({"ssl": True} if needs_ssl else {})


_db_url, _connect_args = prepare_asyncpg_url(settings.database_url)
engine = create_async_engine(_db_url, echo=settings.debug, connect_args=_connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
