#!/usr/bin/env python3
# ==============================================================================
# migrate.py -- Database schema migration script for Omega V5.
# ==============================================================================

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.exc import SQLAlchemyError

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from omega_v5.config import DATABASE_URL

SCHEMA_FILE = ROOT / "omega_v5" / "db" / "schema.sql"

async def apply_schema() -> None:
    """Applies the SQL schema from schema.sql to the database."""
    if not DATABASE_URL:
        print("[ERROR] DATABASE_URL is not configured in .env or config.py.")
        sys.exit(1)

    if not SCHEMA_FILE.exists():
        print(f"[ERROR] Schema file not found at: {SCHEMA_FILE}")
        sys.exit(1)

    print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}...")
    engine = create_async_engine(DATABASE_URL, echo=False)

    try:
        async with engine.begin() as conn:
            sql_commands = SCHEMA_FILE.read_text(encoding="utf-8")
            await conn.execute(sql_commands)
        print("[SUCCESS] Database schema applied successfully.")
    except SQLAlchemyError as e:
        print(f"[ERROR] Failed to apply database schema: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    print("Applying Omega V5 PostgreSQL schema...")
    asyncio.run(apply_schema())