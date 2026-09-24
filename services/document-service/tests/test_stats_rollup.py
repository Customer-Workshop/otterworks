"""A replica that restarts inside a rollup window does not double that window."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import stats_rollup
from app.models.document import DocumentStatsRollup

WINDOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _rows(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(DocumentStatsRollup))).scalar_one()


@pytest.mark.asyncio
async def test_same_host_rerun_reuses_its_row(db_session: AsyncSession) -> None:
    first = await stats_rollup.compute_rollup(db_session, WINDOW)
    again = await stats_rollup.compute_rollup(db_session, WINDOW)
    assert again.id == first.id
    assert await _rows(db_session) == 1


@pytest.mark.asyncio
async def test_other_host_still_writes_its_own_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await stats_rollup.compute_rollup(db_session, WINDOW)
    monkeypatch.setattr(stats_rollup.socket, "gethostname", lambda: "replica-b")
    await stats_rollup.compute_rollup(db_session, WINDOW)
    assert await _rows(db_session) == 2
    assert await stats_rollup.duplicate_windows(db_session, WINDOW) == 1
