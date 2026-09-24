"""Apply Alembic migrations at service start."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from alembic.config import Config

logger = structlog.get_logger()

SERVICE_ROOT = Path(__file__).resolve().parents[2]

# Revision that matches a schema created by ``Base.metadata.create_all`` before
# the service ran migrations on boot.
LEGACY_BASELINE = "001"


def _alembic_config() -> Config:
    cfg = Config(str(SERVICE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return cfg


def _table_names(sync_conn) -> set[str]:  # noqa: ANN001
    return set(inspect(sync_conn).get_table_names())


async def upgrade_to_head(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(_table_names)
    cfg = _alembic_config()
    if "documents" in tables and "alembic_version" not in tables:
        logger.info("alembic_stamping_legacy_schema", revision=LEGACY_BASELINE)
        await asyncio.to_thread(command.stamp, cfg, LEGACY_BASELINE)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    logger.info("alembic_upgraded", revision="head")
