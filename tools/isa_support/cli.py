from __future__ import annotations

import argparse
from typing import Literal, cast

CommentLevel = Literal["none", "summary", "full"]
COMMENT_LEVELS: tuple[CommentLevel, ...] = ("none", "summary", "full")


def validate_comment_level(level: str) -> CommentLevel:
    if level not in COMMENT_LEVELS:
        choices = ", ".join(COMMENT_LEVELS)
        raise ValueError(f"invalid comment level {level!r}; choose from {choices}")
    return cast(CommentLevel, level)


def positive_int_arg(value: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result
