import os
import glob
import logging
from pathlib import Path
from dotenv import load_dotenv
import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrations")

load_dotenv()


def run_migrations(db_url: str | None = None) -> None:
    if not db_url:
        db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set.")

    migrations_dir = Path(__file__).parent
    sql_files = sorted(glob.glob(str(migrations_dir / "*.sql")))

    logger.info(f"Connecting to database to run migrations...")
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                );
            """)

            cur.execute("SELECT version FROM schema_migrations;")
            applied_versions = {row[0] for row in cur.fetchall()}

            for filepath in sql_files:
                filename = Path(filepath).name
                if filename in applied_versions:
                    logger.info(f"Migration {filename} already applied. Skipping.")
                    continue

                logger.info(f"Applying migration: {filename}...")
                with open(filepath, "r", encoding="utf-8") as f:
                    sql_content = f.read()

                with conn.transaction():
                    cur.execute(sql_content)
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s);",
                        (filename,)
                    )
                logger.info(f"Migration {filename} applied successfully.")


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else None
    run_migrations(url)
