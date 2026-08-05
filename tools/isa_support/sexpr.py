from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import sexpdata

MAX_DEPTH = 64
MAX_NODES = 100_000


class SExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Symbol:
    value: str


SExpression: TypeAlias = int | str | Symbol | list["SExpression"]


def parse_one(text: str, *, context: str = "S-expression") -> SExpression:
    try:
        forms = sexpdata.parse(
            text,
            nil=None,
            true=None,
            false=None,
            line_comment=";",
        )
    except Exception as error:
        raise SExpressionError(f"{context}: invalid S-expression: {error}") from error
    if (
        len(forms) == 2
        and isinstance(forms[0], sexpdata.Symbol)
        and forms[0].value() == "#"
        and isinstance(forms[1], list)
    ):
        raise SExpressionError(f"{context}: vector reader syntax is not supported")
    if len(forms) != 1:
        raise SExpressionError(
            f"{context}: expected exactly one top-level S-expression, got {len(forms)}"
        )

    nodes = 0

    def convert(value: object, depth: int) -> SExpression:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            raise SExpressionError(f"{context}: S-expression exceeds {MAX_NODES} nodes")
        if depth > MAX_DEPTH:
            raise SExpressionError(f"{context}: S-expression exceeds depth {MAX_DEPTH}")
        if isinstance(value, bool):
            raise SExpressionError(f"{context}: boolean atoms are not supported")
        if isinstance(value, sexpdata.Symbol):
            symbol = value.value()
            if symbol in {".", "nil", "t", "#t", "#f"} or symbol.startswith((":", "#")):
                raise SExpressionError(
                    f"{context}: reserved Lisp symbol {symbol!r} is not supported"
                )
            return Symbol(symbol)
        if isinstance(value, int | str):
            return value
        if isinstance(value, list):
            return [convert(item, depth + 1) for item in value]
        raise SExpressionError(
            f"{context}: unsupported S-expression node {type(value).__name__}"
        )

    return convert(forms[0], 0)
