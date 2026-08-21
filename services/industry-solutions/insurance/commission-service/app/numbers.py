"""Oracle ``NUMBER`` semantics for the extracted rules.

Oracle ``NUMBER`` is an exact decimal type with 38 significant digits, and
``ROUND`` rounds half away from zero. Commission amounts must never touch binary
floating point, so every arithmetic step here runs through ``decimal`` in a
context that mirrors Oracle: 38 significant digits, half-up on the digit that
falls off the end.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Context, Decimal, localcontext

# R37: Oracle NUMBER — 38 significant decimal digits, half-away-from-zero.
NUMBER_CONTEXT = Context(prec=38, rounding=ROUND_HALF_UP)

CENTS = Decimal("0.01")


def number(value: object) -> Decimal:
    """Coerce a wire/database value to an exact decimal, never via float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("commission arithmetic must not go through binary float")
    return Decimal(str(value))


def divide(dividend: Decimal, divisor: Decimal) -> Decimal:
    with localcontext(NUMBER_CONTEXT):
        return dividend / divisor


def multiply(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(NUMBER_CONTEXT):
        return left * right


def round_cents(value: Decimal) -> Decimal:
    """``ROUND(value, 2)`` — half away from zero, as Oracle does."""
    with localcontext(NUMBER_CONTEXT):
        return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def to_char(value: Decimal | None) -> str:
    """Oracle's default ``TO_CHAR(number)``.

    R38: trailing zeros are dropped (``8.50`` renders as ``8.5``) and there is no
    leading zero below one (``0.5`` renders as ``.5``). Audit details and error
    messages in the package body interpolate numbers this way, so the extracted
    rules have to render them identically.
    """
    if value is None:
        return "NULL"
    normalized = value.normalize()
    if normalized == 0:
        normalized = Decimal(0)
    if normalized.as_tuple().exponent > 0:
        normalized = normalized.quantize(Decimal(1))
    text = format(normalized, "f")
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text
