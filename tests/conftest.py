import os
import pytest
from dotenv import load_dotenv
import psycopg
from src.shared.db import init_pool, close_pool, get_pool
from migrations.run_migrations import run_migrations

load_dotenv()

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:Shopnil13@localhost:5432/fse01_test")


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure test database schema is migrated before running tests."""
    run_migrations(TEST_DB_URL)
    pool = init_pool(TEST_DB_URL, min_size=2, max_size=10)
    yield
    close_pool()


@pytest.fixture(autouse=True)
def truncate_tables():
    """Truncate tables between tests to guarantee isolated test execution."""
    yield
    # Cleanup after test
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                TRUNCATE TABLE 
                    submission_attempts,
                    production_events,
                    production_sources,
                    mqtt_challenges
                CASCADE;
            """)
        conn.commit()


@pytest.fixture
def db_conn():
    """Provides a dedicated connection for testing raw queries."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn
