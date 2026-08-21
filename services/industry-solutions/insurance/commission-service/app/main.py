"""HTTP surface for the extracted Commission Pay rules.

The Oracle package body ``COMMISSION_PKG`` now marshals its arguments to these
endpoints and re-raises whatever comes back, so this API is the only place the
rules run. Numbers cross the wire as strings so that no value is ever routed
through a binary float; error responses carry the original ``ORA-20xxx`` code and
message for the package body to re-raise verbatim.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

import oracledb
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import domain
from app.config import settings
from app.db import connect, unit_of_work
from app.domain import CommissionError, SplitInput

app = FastAPI(title=settings.app_name)

DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def _parse_date(value: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise CommissionError(-20000, f"Not a valid date: {value}")


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise CommissionError(-20000, f"Not a valid number: {value}") from error


class RateUpsert(BaseModel):
    product_code: str
    agent_id: int | None = None
    rate_pct: str | None = None
    effective_from: str
    actor: str


class RateEnd(BaseModel):
    product_code: str
    agent_id: int | None = None
    effective_to: str
    actor: str


class SplitAllocation(BaseModel):
    agent_id: int
    split_pct: str | None = None


class SplitsRequest(BaseModel):
    splits: list[SplitAllocation] = Field(default_factory=list)
    actor: str


class CommissionRun(BaseModel):
    period_month: str
    actor: str


@app.exception_handler(CommissionError)
def _commission_error_handler(_request: Request, error: CommissionError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"ora_code": error.code, "message": error.message})


@app.exception_handler(oracledb.DatabaseError)
def _database_error_handler(_request: Request, error: oracledb.DatabaseError) -> JSONResponse:
    (info,) = error.args
    return JSONResponse(
        status_code=409,
        content={"ora_code": -20000, "message": str(info.message).strip()},
    )


@app.get("/health")
def health() -> dict[str, str]:
    with connect() as connection:
        connection.cursor().execute("SELECT 1 FROM dual")
    return {"status": "healthy", "service": settings.app_name}


@app.post("/rates/upsert")
def upsert_rate(body: RateUpsert) -> dict[str, int]:
    with unit_of_work() as repo:
        rate_id = domain.upsert_commission_rate(
            repo,
            body.product_code,
            body.agent_id,
            _decimal(body.rate_pct),
            _parse_date(body.effective_from),
            body.actor,
        )
    return {"rate_id": rate_id}


@app.post("/rates/end")
def end_rate(body: RateEnd) -> dict[str, str]:
    with unit_of_work() as repo:
        domain.end_commission_rate(
            repo,
            body.product_code,
            body.agent_id,
            _parse_date(body.effective_to),
            body.actor,
        )
    return {"status": "ended"}


@app.get("/rates/resolve")
def resolve_rate(
    product_code: str = Query(...),
    as_of: str = Query(...),
    agent_id: int | None = Query(default=None),
) -> dict[str, int]:
    with unit_of_work() as repo:
        rate_id = domain.resolve_rate(repo, product_code, agent_id, _parse_date(as_of))
    return {"rate_id": rate_id}


@app.post("/policies/{policy_id}/splits")
def set_splits(policy_id: int, body: SplitsRequest) -> dict[str, int]:
    splits = [
        SplitInput(agent_id=split.agent_id, split_pct=_decimal(split.split_pct))
        for split in body.splits
    ]
    with unit_of_work() as repo:
        count = domain.set_commission_splits(repo, policy_id, splits, body.actor)
    return {"splits": count}


@app.post("/policies/{policy_id}/commission")
def calculate_commission(policy_id: int, body: CommissionRun) -> dict[str, int]:
    with unit_of_work() as repo:
        rows = domain.calculate_policy_commission(repo, policy_id, body.period_month, body.actor)
    return {"rows": rows}
