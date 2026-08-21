from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb

from app.config import settings
from app.repository import OracleCommissionRepository


def connect() -> oracledb.Connection:
    return oracledb.connect(user=settings.user, password=settings.password, dsn=settings.dsn)


@contextmanager
def unit_of_work() -> Iterator[OracleCommissionRepository]:
    """R9 / R21 / R35: commit on success, roll back and re-raise on any error."""
    connection = connect()
    try:
        yield OracleCommissionRepository(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
