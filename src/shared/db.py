import os
import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional
from dotenv import load_dotenv
import psycopg
from psycopg_pool import ConnectionPool
from src.shared.domain_events import transaction_events

logger = logging.getLogger("db")
load_dotenv()

_pool: Optional[ConnectionPool] = None


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is not set.")
    return url


def init_pool(db_url: Optional[str] = None, min_size: int = 2, max_size: int = 20) -> ConnectionPool:
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.close()

    target_url = db_url or get_db_url()
    logger.info("Initializing database connection pool...")
    _pool = ConnectionPool(
        conninfo=target_url,
        min_size=min_size,
        max_size=max_size,
        open=True,
        kwargs={"autocommit": False}
    )
    return _pool


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = init_pool()
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None and not _pool.closed:
        logger.info("Closing database connection pool...")
        _pool.close()
        _pool = None


@contextmanager
def get_connection(conn: Optional[psycopg.Connection] = None) -> Generator[psycopg.Connection, None, None]:
    if conn is not None:
        yield conn
    else:
        pool = get_pool()
        with pool.connection() as c:
            yield c


@contextmanager
def transaction(conn: Optional[psycopg.Connection] = None) -> Generator[psycopg.Connection, None, None]:
    """
    Transaction helper with domain event commit-hook support.
    If conn is provided, manages a transaction/savepoint on that connection.
    If conn is None, borrows a connection from the pool and runs a top-level transaction.
    """
    if conn is not None:
        with conn.transaction():
            yield conn
    else:
        pool = get_pool()
        with pool.connection() as c:
            with transaction_events():
                with c.transaction():
                    yield c
