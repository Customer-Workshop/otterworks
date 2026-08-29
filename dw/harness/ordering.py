"""Helpers for validating ordered-key command-line arguments."""

from __future__ import annotations


def has_top_level_comma(expression: str) -> bool:
    depth = 0
    for character in expression:
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            return True
    return False
