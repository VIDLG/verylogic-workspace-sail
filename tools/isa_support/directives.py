from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

_ASSERT_RE = re.compile(
    r"^\.assert\s+(?P<display_target>.+?)\s*"
    r"(?P<operator>==|!=|<=|>=|<|>)\s*(?P<value>\S+)\s*$"
)
_WRAPPED_TARGET_RE = re.compile(r"^(?P<mode>signed|unsigned)\((?P<target>.*)\)$")


class DirectiveSyntaxError(ValueError):
    def __init__(self, message: str, line: int):
        super().__init__(f"line {line}: {message}")
        self.line = line


@dataclass(frozen=True)
class DescriptionDirective:
    text: str
    line: int


@dataclass(frozen=True)
class MaxStepsDirective:
    value: int
    line: int


@dataclass(frozen=True)
class AssertionDirective:
    target: str
    operator: str
    value: int
    mode: str
    line: int
    display_target: str


PublicDirective: TypeAlias = (
    DescriptionDirective | MaxStepsDirective | AssertionDirective
)


def _python_int(text: str, line: int) -> int:
    try:
        return int(text, 0)
    except ValueError as error:
        raise DirectiveSyntaxError(f"invalid integer {text!r}", line) from error


def _parse_assertion(code: str, line: int) -> AssertionDirective:
    match = _ASSERT_RE.fullmatch(code)
    if match is None:
        raise DirectiveSyntaxError("expected .assert TARGET OP INTEGER", line)

    display_target = match.group("display_target").strip()
    operator = match.group("operator")
    wrapped = _WRAPPED_TARGET_RE.fullmatch(display_target)
    value = _python_int(match.group("value"), line)

    if operator in {"==", "!="}:
        if wrapped is not None:
            raise DirectiveSyntaxError(
                "equality assertions cannot use signed/unsigned wrappers", line
            )
        target = display_target
        mode = "bits"
    else:
        if wrapped is None or not wrapped.group("target").strip():
            raise DirectiveSyntaxError(
                "ordered assertions require signed(target) or unsigned(target)", line
            )
        target = wrapped.group("target").strip()
        mode = wrapped.group("mode")

    if not target:
        raise DirectiveSyntaxError("assertion target must be nonempty", line)
    return AssertionDirective(target, operator, value, mode, line, display_target)


def parse_directive(code: str, line: int) -> PublicDirective | None:
    """Parse one complete, comment-stripped source line.

    ISA-specific directives and ordinary source lines are deliberately ignored.
    """
    stripped = code.strip()
    if not stripped:
        return None
    name = stripped.split(maxsplit=1)[0]
    if name not in {".description", ".max_steps", ".assert"}:
        return None

    if name == ".description":
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            raise DirectiveSyntaxError("expected .description TEXT", line)
        return DescriptionDirective(parts[1].strip(), line)

    if name == ".max_steps":
        parts = stripped.split()
        if len(parts) != 2:
            raise DirectiveSyntaxError("expected .max_steps POSITIVE_INT", line)
        value = _python_int(parts[1], line)
        if value <= 0:
            raise DirectiveSyntaxError(".max_steps must be a positive integer", line)
        return MaxStepsDirective(value, line)

    return _parse_assertion(stripped, line)


class DirectiveAccumulator:
    def __init__(self) -> None:
        self._description: DescriptionDirective | None = None
        self._max_steps: MaxStepsDirective | None = None
        self._assertions: list[AssertionDirective] = []

    def add(self, directive: PublicDirective | None) -> None:
        if directive is None:
            return
        if isinstance(directive, DescriptionDirective):
            if self._description is not None:
                raise DirectiveSyntaxError(
                    "duplicate .description directive", directive.line
                )
            self._description = directive
        elif isinstance(directive, MaxStepsDirective):
            if self._max_steps is not None:
                raise DirectiveSyntaxError(
                    "duplicate .max_steps directive", directive.line
                )
            self._max_steps = directive
        else:
            self._assertions.append(directive)

    @property
    def description(self) -> DescriptionDirective | None:
        return self._description

    @property
    def max_steps(self) -> MaxStepsDirective | None:
        return self._max_steps

    @property
    def assertions(self) -> tuple[AssertionDirective, ...]:
        return tuple(self._assertions)
