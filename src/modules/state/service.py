from typing import Optional, Any
import psycopg
from src.shared.contracts import Summary
from src.shared.db import get_connection
from src.modules.state import queries


def get_summary(conn: Optional[psycopg.Connection] = None, source_id: Optional[str] = None) -> Summary:
    with get_connection(conn) as c:
        return queries.query_summary(c, source_id=source_id)


def get_pending(conn: Optional[psycopg.Connection] = None, source_id: Optional[str] = None) -> list[dict[str, Any]]:
    with get_connection(conn) as c:
        return queries.query_pending(c, source_id=source_id)


def get_exceptions(conn: Optional[psycopg.Connection] = None, source_id: Optional[str] = None) -> list[dict[str, Any]]:
    with get_connection(conn) as c:
        return queries.query_exceptions(c, source_id=source_id)


def get_sources(conn: Optional[psycopg.Connection] = None) -> list[str]:
    with get_connection(conn) as c:
        return queries.query_sources(c)
