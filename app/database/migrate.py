"""
Lightweight auto-migration for existing tables.

`Base.metadata.create_all()` only CREATES tables that don't exist yet — it
never adds new columns to a table that already exists. Since this project has
no Alembic migrations, every time a new column is added to a SQLAlchemy model
(e.g. Job.logo_url, Job.overlay_text), the already-existing production table
falls out of sync and every INSERT/SELECT touching that column crashes with
psycopg2.errors.UndefinedColumn (or the sqlite3 equivalent).

This module runs once at startup, compares each model's expected columns
against what's actually in the database, and issues `ALTER TABLE ... ADD
COLUMN` for anything missing. It's intentionally conservative:
  - Only ADDs columns, never drops/alters/renames anything.
  - Wrapped in try/except per-column so one failure can't block startup.
  - Safe to run on every cold start — it's a no-op once columns exist.
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def sync_missing_columns(engine, base):
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in base.metadata.sorted_tables:
            if table.name not in existing_tables:
                # Brand-new table — create_all() already handled it.
                continue

            existing_columns = {
                col["name"] for col in inspector.get_columns(table.name)
            }

            for column in table.columns:
                if column.name in existing_columns:
                    continue

                try:
                    col_type = column.type.compile(dialect=engine.dialect)
                    nullable = "" if column.nullable else " NOT NULL"
                    default_clause = ""

                    # Adding a NOT NULL column to a table that already has
                    # rows requires a default, otherwise the ALTER fails.
                    if not column.nullable and column.default is not None and column.default.is_scalar:
                        default_clause = f" DEFAULT {column.default.arg!r}"
                    elif not column.nullable:
                        # No usable default — add as nullable instead so
                        # existing rows don't break the migration.
                        nullable = ""

                    ddl = (
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {col_type}{default_clause}{nullable}'
                    )
                    conn.execute(text(ddl))
                    logger.info(f"Auto-migration: added column {table.name}.{column.name}")
                except Exception as e:
                    logger.warning(
                        f"Auto-migration: could not add column {table.name}.{column.name}: {e}"
                    )
