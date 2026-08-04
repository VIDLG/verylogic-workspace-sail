from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TypeAlias

COMP = {
    "0": "0101010", "1": "0111111", "-1": "0111010", "D": "0001100",
    "A": "0110000", "!D": "0001101", "!A": "0110001", "-D": "0001111",
    "-A": "0110011", "D+1": "0011111", "A+1": "0110111", "D-1": "0001110",
    "A-1": "0110010", "D+A": "0000010", "D-A": "0010011", "A-D": "0000111",
    "D&A": "0000000", "D|A": "0010101", "M": "1110000", "!M": "1110001",
    "-M": "1110011", "M+1": "1110111", "M-1": "1110010", "D+M": "1000010",
    "D-M": "1010011", "M-D": "1000111", "D&M": "1000000", "D|M": "1010101",
}
DEST = {"": "000", "M": "001", "D": "010", "MD": "011", "A": "100", "AM": "101", "AD": "110", "AMD": "111"}
JUMP = {"": "000", "JGT": "001", "JEQ": "010", "JGE": "011", "JLT": "100", "JNE": "101", "JLE": "110", "JMP": "111"}
SYMBOLS = {
    **{f"R{index}": index for index in range(16)},
    "SP": 0, "LCL": 1, "ARG": 2, "THIS": 3, "THAT": 4, "SCREEN": 16384, "KBD": 24576,
}

SYMBOL_PATTERN = r"[A-Za-z_.$:][A-Za-z0-9_.$:]*"
SYMBOL_RE = re.compile(SYMBOL_PATTERN)
DECIMAL_RE = re.compile(r"[0-9]+")
PYTHON_INT_RE = re.compile(
    r"[+-]?(?:0[bB][01](?:_?[01])*|0[oO][0-7](?:_?[0-7])*|"
    r"0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*|0|[1-9](?:_?[0-9])*)"
)
LABEL_RE = re.compile(rf"\(\s*(?P<name>{SYMBOL_PATTERN})\s*\)")
A_INSTRUCTION_RE = re.compile(r"@\s*(?P<operand>\S+)\s*")
C_INSTRUCTION_RE = re.compile(
    r"(?:(?P<dest>[ADM\s]+?)\s*=\s*)?"
    r"(?P<comp>[01ADM!+&|\-\s]+?)"
    r"(?:\s*;\s*(?P<jump>[A-Z\s]+))?"
)
ASSERT_RE = re.compile(
    r"\.assert\s+(?P<target>.+?)\s*(?P<operator>==|!=|<=|>=|<|>)\s*(?P<value>\S+)\s*"
)
MAX_STEPS_RE = re.compile(r"\.max_steps\s+(?P<value>\S+)\s*")
HOOK_RE = re.compile(r"\.hook\s+(?P<path>\S+)\s*")
DESCRIPTION_RE = re.compile(r"\.description\s+(?P<text>.+?)\s*")
DEFAULT_HOOK_PATH = "hooks.sail"
ASSERT_TARGET_RE = re.compile(r"A|D|PC|R(?:[0-9]|1[0-5])|RAM\[\s*(?:0|[1-9][0-9]*)\s*\]")
ASSERT_WRAPPER_RE = re.compile(r"(?P<mode>signed|unsigned)\s*\(\s*(?P<target>.*?)\s*\)")
EQUALITY_OPERATORS = {"==", "!="}
RELATIONAL_OPERATORS = {"<", "<=", ">", ">="}
ASSERTION_OPERATORS = EQUALITY_OPERATORS | RELATIONAL_OPERATORS
ASSERTION_MODES = {"bits", "signed", "unsigned"}
PSEUDO_NAMES = {"SET", "INC", "DEC", "GOTO", "JNZ", "JGT", "JEQ", "JGE", "JLT", "JLE", "HALT"}
PSEUDO_PATTERNS = {
    "SET": re.compile(r"SET\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE),
    "INC": re.compile(r"INC\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "DEC": re.compile(r"DEC\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "GOTO": re.compile(r"GOTO\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "JNZ": re.compile(r"JNZ\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE),
    "JGT": re.compile(r"JGT\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE),
    "JEQ": re.compile(r"JEQ\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE),
    "JGE": re.compile(r"JGE\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE),
    "JLT": re.compile(r"JLT\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE),
    "JLE": re.compile(r"JLE\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE),
    "HALT": re.compile(r"HALT", re.IGNORECASE),
}
HACK_WORD_RE = re.compile(r"\s*(?P<word>[01]{16})(?:\s+//\s*(?P<comment>.*?))?\s*")
METADATA_RE = re.compile(r"//%hack\s+(?P<kind>[a-z_]+)\s+(?P<payload>\{.*\})\s*")
COMMENT_LEVELS = ("none", "summary", "full")


class AssemblyError(ValueError):
    def __init__(self, line: int, message: str) -> None:
        self.line = line
        self.message = message
        super().__init__(f"line {line}: {message}")


@dataclass(frozen=True)
class SourceLine:
    line: int
    text: str


@dataclass(frozen=True)
class PseudoExpansion:
    instruction: str
    index: int
    count: int


@dataclass(frozen=True)
class AInstruction:
    source: SourceLine
    operand: str
    expansion: PseudoExpansion | None = None


@dataclass(frozen=True)
class CInstruction:
    source: SourceLine
    dest: str
    comp: str
    jump: str
    expansion: PseudoExpansion | None = None


@dataclass(frozen=True)
class Label:
    source: SourceLine
    name: str


@dataclass(frozen=True)
class PseudoInstruction:
    source: SourceLine
    name: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class AssertionDirective:
    source: SourceLine
    target: str
    operator: str
    mode: str
    value: int


@dataclass(frozen=True)
class MaxStepsDirective:
    source: SourceLine
    value: int


@dataclass(frozen=True)
class HookDirective:
    source: SourceLine
    path: str


@dataclass(frozen=True)
class DescriptionDirective:
    source: SourceLine
    text: str


Statement: TypeAlias = AInstruction | CInstruction | Label | PseudoInstruction | AssertionDirective | MaxStepsDirective | HookDirective | DescriptionDirective
Instruction: TypeAlias = AInstruction | CInstruction


@dataclass(frozen=True)
class Assertion:
    target: str
    value: int
    line: int
    operator: str = "=="
    mode: str = "bits"


@dataclass(frozen=True)
class AssemblyMetadata:
    halt_addresses: tuple[int, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    max_steps: int | None = None
    hook_path: str = DEFAULT_HOOK_PATH


@dataclass(frozen=True)
class MachineWord:
    value: int
    source: SourceLine
    expansion: PseudoExpansion | None = None


@dataclass(frozen=True)
class AssemblyResult:
    records: tuple[MachineWord, ...]
    metadata: AssemblyMetadata

    @property
    def words(self) -> list[int]:
        return [record.value for record in self.records]


@dataclass(frozen=True)
class LoadedHack:
    words: list[int]
    metadata: AssemblyMetadata
    word_comments: tuple[str | None, ...] = ()


class Parser:
    def parse(self, text: str) -> list[Statement]:
        statements: list[Statement] = []
        seen_max_steps = False
        seen_hook = False
        seen_description = False
        for line_number, raw in enumerate(text.splitlines(), start=1):
            code = raw.split("//", maxsplit=1)[0].strip()
            if not code:
                continue
            source = SourceLine(line_number, raw)

            if code.startswith(".description"):
                if seen_description:
                    raise AssemblyError(line_number, "duplicate .description directive")
                statement = self._parse_description(code, source)
                seen_description = True
                statements.append(statement)
                continue
            if code.startswith(".assert"):
                statements.append(self._parse_assertion(code, source))
                continue
            if code.startswith(".max_steps"):
                if seen_max_steps:
                    raise AssemblyError(line_number, "duplicate .max_steps directive")
                statement = self._parse_max_steps(code, source)
                seen_max_steps = True
                statements.append(statement)
                continue
            if code.startswith(".hook"):
                if seen_hook:
                    raise AssemblyError(line_number, "duplicate .hook directive")
                statement = self._parse_hook(code, source)
                seen_hook = True
                statements.append(statement)
                continue
            if code.startswith("."):
                raise AssemblyError(line_number, f"unknown directive {code.split()[0]!r}")

            label_match = LABEL_RE.fullmatch(code)
            if label_match is not None:
                statements.append(Label(source, label_match.group("name")))
                continue
            if code.startswith("(") or code.endswith(")"):
                raise AssemblyError(line_number, "invalid label declaration")

            if code.startswith("@"):
                statements.append(self._parse_instruction(code, source))
                continue

            head = code.split(maxsplit=1)[0].upper()
            if head in PSEUDO_NAMES:
                statements.append(self._parse_pseudo(code, source, head))
                continue

            statements.append(self._parse_instruction(code, source))
        return statements

    def _parse_description(self, code: str, source: SourceLine) -> DescriptionDirective:
        match = DESCRIPTION_RE.fullmatch(code)
        if match is None:
            raise AssemblyError(source.line, "expected .description <nonempty text>")
        return DescriptionDirective(source, match.group("text"))

    def _parse_assertion(self, code: str, source: SourceLine) -> AssertionDirective:
        match = ASSERT_RE.fullmatch(code)
        if match is None:
            raise AssemblyError(source.line, "expected .assert <target> <operator> <integer>")
        target, wrapper = parse_assertion_target(match.group("target"), source.line)
        operator = match.group("operator")
        mode = assertion_mode(target, operator, wrapper)
        value = parse_expected_value(match.group("value"), source.line, target, operator, mode)
        return AssertionDirective(source, target, operator, mode, value)

    def _parse_max_steps(self, code: str, source: SourceLine) -> MaxStepsDirective:
        match = MAX_STEPS_RE.fullmatch(code)
        if match is None:
            raise AssemblyError(source.line, "expected .max_steps <positive integer>")
        value = parse_python_int(match.group("value"), source.line)
        if value <= 0:
            raise AssemblyError(source.line, ".max_steps must be a positive integer")
        return MaxStepsDirective(source, value)

    def _parse_hook(self, code: str, source: SourceLine) -> HookDirective:
        match = HOOK_RE.fullmatch(code)
        if match is None:
            raise AssemblyError(source.line, "expected .hook <relative .sail path>")
        try:
            path = normalize_hook_path(match.group("path"))
        except ValueError as error:
            raise AssemblyError(source.line, str(error)) from error
        return HookDirective(source, path)

    def _parse_pseudo(self, code: str, source: SourceLine, name: str) -> PseudoInstruction:
        match = PSEUDO_PATTERNS[name].fullmatch(code)
        if match is None:
            raise AssemblyError(source.line, f"invalid {name} pseudoinstruction")
        arguments = tuple(value for key in ("first", "second") if (value := match.groupdict().get(key)) is not None)
        for argument in arguments:
            validate_a_operand(argument, source.line)
        return PseudoInstruction(source, name, arguments)

    def _parse_instruction(
        self, code: str, source: SourceLine, expansion: PseudoExpansion | None = None
    ) -> Instruction:
        a_match = A_INSTRUCTION_RE.fullmatch(code)
        if a_match is not None:
            operand = a_match.group("operand")
            validate_a_operand(operand, source.line)
            return AInstruction(source, operand, expansion)
        if code.startswith("@"):
            raise AssemblyError(source.line, "malformed A-instruction")

        c_match = C_INSTRUCTION_RE.fullmatch(code)
        if c_match is None:
            raise AssemblyError(source.line, f"malformed instruction {code!r}")
        dest = "".join((c_match.group("dest") or "").split())
        comp = "".join(c_match.group("comp").split())
        jump = "".join((c_match.group("jump") or "").split())
        if dest not in DEST:
            raise AssemblyError(source.line, f"invalid destination {dest!r}")
        if comp not in COMP:
            raise AssemblyError(source.line, f"invalid computation {comp!r}")
        if jump not in JUMP:
            raise AssemblyError(source.line, f"invalid jump {jump!r}")
        return CInstruction(source, dest, comp, jump, expansion)


def normalize_hook_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part == ".." or ":" in part for part in path.parts)
        or path.suffix != ".sail"
    ):
        raise ValueError("hook path must be a nonempty safe relative .sail path")
    return path.as_posix()


def parse_python_int(token: str, line: int) -> int:
    if PYTHON_INT_RE.fullmatch(token) is None:
        raise AssemblyError(line, f"invalid integer {token!r}")
    return int(token, 0)


def parse_expected_value(token: str, line: int, target: str, operator: str, mode: str) -> int:
    value = parse_python_int(token, line)
    if target == "PC":
        if not 0 <= value <= 32767:
            raise AssemblyError(line, "PC assertion value must be in 0..32767")
        return value
    if operator in EQUALITY_OPERATORS:
        if not -32768 <= value <= 65535:
            raise AssemblyError(line, "bit-exact assertion value must fit a signed or unsigned 16-bit word")
        return value & 0xFFFF
    if mode == "signed":
        if not -32768 <= value <= 32767:
            raise AssemblyError(line, "signed relational assertion value must be in -32768..32767")
        return value
    if not 0 <= value <= 65535:
        raise AssemblyError(line, "unsigned relational assertion value must be in 0..65535")
    return value


def parse_assertion_target(expression: str, line: int) -> tuple[str, str | None]:
    expression = expression.strip()
    wrapper_match = ASSERT_WRAPPER_RE.fullmatch(expression)
    if wrapper_match is None:
        return canonical_assertion_target(expression, line), None
    mode = wrapper_match.group("mode")
    target = canonical_assertion_target(wrapper_match.group("target"), line)
    if target == "PC" and mode == "signed":
        raise AssemblyError(line, "signed(PC) is invalid because PC is an unsigned 15-bit value")
    return target, mode


def assertion_mode(target: str, operator: str, wrapper: str | None) -> str:
    if target == "PC":
        return "unsigned"
    if wrapper is not None:
        return wrapper
    return "bits" if operator in EQUALITY_OPERATORS else "signed"


def canonical_assertion_target(target: str, line: int) -> str:
    target = target.strip()
    if ASSERT_TARGET_RE.fullmatch(target) is None:
        raise AssemblyError(line, f"invalid assertion target {target!r}")
    if target.startswith("RAM["):
        index = int(target[4:-1].strip())
        if index >= 32768:
            raise AssemblyError(line, "RAM assertion index must be in 0..32767")
        return f"RAM[{index}]"
    return target


def validate_a_operand(operand: str, line: int) -> None:
    if DECIMAL_RE.fullmatch(operand) is not None:
        if int(operand) >= 32768:
            raise AssemblyError(line, "A-instruction value must be in 0..32767")
        return
    if SYMBOL_RE.fullmatch(operand) is None:
        raise AssemblyError(line, f"invalid Hack symbol {operand!r}")


def parse(text: str) -> list[Statement]:
    return Parser().parse(text)


def source_description(text: str) -> str | None:
    for statement in parse(text):
        if isinstance(statement, DescriptionDirective):
            return statement.text
    return None


def _expanded_instruction(
    parser: Parser, source: SourceLine, text: str, index: int, count: int
) -> Instruction:
    return parser._parse_instruction(text, source, PseudoExpansion(text, index, count))


def expand(statements: list[Statement]) -> tuple[list[Instruction | Label], list[AssertionDirective], MaxStepsDirective | None, HookDirective | None, list[tuple[SourceLine, str]]]:
    parser = Parser()
    code: list[Instruction | Label] = []
    assertions: list[AssertionDirective] = []
    max_steps: MaxStepsDirective | None = None
    hook: HookDirective | None = None
    halts: list[tuple[SourceLine, str]] = []
    halt_index = 0

    for statement in statements:
        if isinstance(statement, AssertionDirective):
            assertions.append(statement)
        elif isinstance(statement, MaxStepsDirective):
            max_steps = statement
        elif isinstance(statement, HookDirective):
            hook = statement
        elif isinstance(statement, DescriptionDirective):
            continue
        elif not isinstance(statement, PseudoInstruction):
            code.append(statement)
        else:
            name = statement.name
            args = statement.arguments
            if name == "SET":
                expanded = [f"@{args[1]}", "D=A", f"@{args[0]}", "M=D"]
            elif name == "INC":
                expanded = [f"@{args[0]}", "M=M+1"]
            elif name == "DEC":
                expanded = [f"@{args[0]}", "M=M-1"]
            elif name == "GOTO":
                expanded = [f"@{args[0]}", "0;JMP"]
            elif name in {"JNZ", "JGT", "JEQ", "JGE", "JLT", "JLE"}:
                jump = "JNE" if name == "JNZ" else name
                expanded = [f"@{args[0]}", "D=M", f"@{args[1]}", f"D;{jump}"]
            else:
                label = f"__HACKPLUS_HALT_{halt_index}"
                halt_index += 1
                code.append(Label(statement.source, label))
                halts.append((statement.source, label))
                expanded = [f"@{label}", "0;JMP"]
            count = len(expanded)
            code.extend(
                _expanded_instruction(parser, statement.source, text, index, count)
                for index, text in enumerate(expanded, start=1)
            )
    return code, assertions, max_steps, hook, halts


def assemble_text(text: str) -> AssemblyResult:
    code, assertion_directives, max_steps_directive, hook_directive, halt_labels = expand(parse(text))
    symbols = SYMBOLS.copy()
    instructions: list[Instruction] = []
    address = 0

    for statement in code:
        if isinstance(statement, Label):
            if statement.name in symbols:
                raise AssemblyError(statement.source.line, f"duplicate symbol {statement.name!r}")
            symbols[statement.name] = address
        else:
            instructions.append(statement)
            address += 1
            if address > 32768:
                raise AssemblyError(statement.source.line, "program exceeds the 32768-word Hack ROM")

    next_variable = 16
    records: list[MachineWord] = []
    for instruction in instructions:
        if isinstance(instruction, AInstruction):
            operand = instruction.operand
            if DECIMAL_RE.fullmatch(operand) is not None:
                value = int(operand)
            else:
                if operand not in symbols:
                    if next_variable >= 32768:
                        raise AssemblyError(instruction.source.line, "variable allocation exceeds Hack address space")
                    symbols[operand] = next_variable
                    next_variable += 1
                value = symbols[operand]
            if not 0 <= value < 32768:
                raise AssemblyError(instruction.source.line, "A-instruction value must be in 0..32767")
            word = value
        else:
            word = int(f"111{COMP[instruction.comp]}{DEST[instruction.dest]}{JUMP[instruction.jump]}", 2)
        records.append(MachineWord(word, instruction.source, instruction.expansion))

    halt_addresses = tuple(symbols[label] for _, label in halt_labels)
    assertions = tuple(
        Assertion(
            statement.target,
            statement.value,
            statement.source.line,
            statement.operator,
            statement.mode,
        )
        for statement in assertion_directives
    )
    max_steps = None if max_steps_directive is None else max_steps_directive.value
    hook_path = DEFAULT_HOOK_PATH if hook_directive is None else hook_directive.path
    return AssemblyResult(tuple(records), AssemblyMetadata(halt_addresses, assertions, max_steps, hook_path))


def assemble(source: Path) -> AssemblyResult:
    return assemble_text(source.read_text(encoding="utf-8"))


def _metadata_comment(kind: str, payload: dict[str, int | str]) -> str:
    return f"//%hack {kind} {json.dumps(payload, separators=(',', ':'), sort_keys=True)}\n"


def validate_comment_level(value: str) -> str:
    if value not in COMMENT_LEVELS:
        raise ValueError(f"comment level must be one of {', '.join(COMMENT_LEVELS)}")
    return value


def write_hack(assembly: AssemblyResult, path: Path, comments: str = "summary") -> None:
    comments = validate_comment_level(comments)
    hook_path = normalize_hook_path(assembly.metadata.hook_path)
    lines = [
        _metadata_comment("format", {"version": 3}),
        _metadata_comment("hook", {"path": hook_path}),
    ]
    lines.extend(_metadata_comment("halt", {"address": address}) for address in assembly.metadata.halt_addresses)
    lines.extend(
        _metadata_comment(
            "assert",
            {
                "line": assertion.line,
                "mode": assertion.mode,
                "operator": assertion.operator,
                "target": assertion.target,
                "value": assertion.value,
            },
        )
        for assertion in assembly.metadata.assertions
    )
    if assembly.metadata.max_steps is not None:
        lines.append(_metadata_comment("max_steps", {"value": assembly.metadata.max_steps}))
    for address, record in enumerate(assembly.records):
        suffix = ""
        if comments == "summary":
            mapping = f"ROM[{address:04d}] L{record.source.line}"
            if record.expansion is not None:
                source = record.source.text.split("//", maxsplit=1)[0].strip()
                expansion = record.expansion
                mapping += f" [{expansion.index}/{expansion.count}] {source} => {expansion.instruction}"
            suffix = f" // {mapping}"
        elif comments == "full":
            mapping = f"ROM[{address:04d}] L{record.source.line}: {record.source.text.strip()}"
            if record.expansion is not None:
                expansion = record.expansion
                mapping += f" [{expansion.index}/{expansion.count}] => {expansion.instruction}"
            suffix = f" // {mapping}"
        lines.append(f"{record.value:016b}{suffix}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _metadata_object(path: Path, line_number: int, payload: str) -> dict[str, object]:
    try:
        pairs = json.loads(payload, object_pairs_hook=lambda items: items)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}:{line_number}: invalid Hack metadata JSON: {error.msg}") from error
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"{path}:{line_number}: duplicate Hack metadata key {key!r}")
        value[key] = item
    return value


def _exact_keys(path: Path, line_number: int, value: dict[str, object], keys: set[str]) -> None:
    if set(value) != keys:
        raise ValueError(f"{path}:{line_number}: expected metadata keys {sorted(keys)!r}")


def load_hack(path: Path) -> LoadedHack:
    words: list[int] = []
    word_comments: list[str | None] = []
    halts: list[int] = []
    assertions: list[Assertion] = []
    max_steps: int | None = None
    hook_path: str | None = None
    format_seen = False
    words_started = False

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        metadata_match = METADATA_RE.fullmatch(stripped)
        if metadata_match is not None:
            kind = metadata_match.group("kind")
            payload = _metadata_object(path, line_number, metadata_match.group("payload"))
            if words_started:
                raise ValueError(f"{path}:{line_number}: Hack metadata must precede machine words")
            if kind != "format" and not format_seen:
                raise ValueError(f"{path}:{line_number}: Hack metadata requires a preceding format record")
            if kind == "format":
                _exact_keys(path, line_number, payload, {"version"})
                version = payload["version"]
                if format_seen or not isinstance(version, int) or isinstance(version, bool) or version != 3:
                    raise ValueError(f"{path}:{line_number}: unsupported or duplicate Hack metadata format")
                format_seen = True
            elif kind == "hook":
                _exact_keys(path, line_number, payload, {"path"})
                value = payload["path"]
                if hook_path is not None or not isinstance(value, str):
                    raise ValueError(f"{path}:{line_number}: invalid or duplicate hook metadata")
                try:
                    normalized = normalize_hook_path(value)
                except ValueError as error:
                    raise ValueError(f"{path}:{line_number}: {error}") from error
                if value != normalized:
                    raise ValueError(f"{path}:{line_number}: hook path must be normalized POSIX")
                hook_path = normalized
            elif kind == "halt":
                _exact_keys(path, line_number, payload, {"address"})
                address = payload["address"]
                if not isinstance(address, int) or isinstance(address, bool) or not 0 <= address < 32768:
                    raise ValueError(f"{path}:{line_number}: invalid halt address")
                if address in halts:
                    raise ValueError(f"{path}:{line_number}: duplicate halt address {address}")
                halts.append(address)
            elif kind == "assert":
                _exact_keys(path, line_number, payload, {"line", "mode", "operator", "target", "value"})
                source_line = payload["line"]
                target = payload["target"]
                operator = payload["operator"]
                mode = payload["mode"]
                value = payload["value"]
                if not isinstance(source_line, int) or isinstance(source_line, bool) or source_line <= 0:
                    raise ValueError(f"{path}:{line_number}: invalid assertion source line")
                if not isinstance(target, str):
                    raise ValueError(f"{path}:{line_number}: invalid assertion target")
                try:
                    canonical_target = canonical_assertion_target(target, source_line)
                except AssemblyError as error:
                    raise ValueError(f"{path}:{line_number}: {error.message}") from error
                if not isinstance(operator, str) or operator not in ASSERTION_OPERATORS:
                    raise ValueError(f"{path}:{line_number}: invalid assertion operator")
                if not isinstance(mode, str) or mode not in ASSERTION_MODES:
                    raise ValueError(f"{path}:{line_number}: invalid assertion comparison mode")
                if canonical_target == "PC" and mode != "unsigned":
                    raise ValueError(f"{path}:{line_number}: PC assertion mode must be unsigned")
                if canonical_target != "PC" and operator in RELATIONAL_OPERATORS and mode == "bits":
                    raise ValueError(f"{path}:{line_number}: relational word assertion mode must be signed or unsigned")
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ValueError(f"{path}:{line_number}: invalid assertion value")
                if canonical_target == "PC":
                    valid_value = 0 <= value <= 32767
                elif operator in EQUALITY_OPERATORS:
                    valid_value = 0 <= value <= 65535
                elif mode == "signed":
                    valid_value = -32768 <= value <= 32767
                else:
                    valid_value = 0 <= value <= 65535
                if not valid_value:
                    raise ValueError(f"{path}:{line_number}: assertion value is out of range for its mode")
                assertions.append(Assertion(canonical_target, value, source_line, operator, mode))
            elif kind == "max_steps":
                _exact_keys(path, line_number, payload, {"value"})
                value = payload["value"]
                if max_steps is not None:
                    raise ValueError(f"{path}:{line_number}: duplicate max_steps metadata")
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    raise ValueError(f"{path}:{line_number}: invalid max_steps metadata")
                max_steps = value
            else:
                raise ValueError(f"{path}:{line_number}: unknown Hack metadata kind {kind!r}")
            continue
        if stripped.startswith("//%hack"):
            raise ValueError(f"{path}:{line_number}: malformed Hack metadata comment")
        if stripped.startswith("//"):
            continue
        word_match = HACK_WORD_RE.fullmatch(line)
        if word_match is None:
            raise ValueError(f"{path}:{line_number}: expected a 16-bit binary word or comment")
        words_started = True
        words.append(int(word_match.group("word"), 2))
        word_comments.append(word_match.group("comment"))
        if len(words) > 32768:
            raise ValueError(f"{path}:{line_number}: program exceeds the 32768-word Hack ROM")

    if format_seen and hook_path is None:
        raise ValueError(f"{path}: missing hook metadata")

    halt_jump = int("1110101010000111", 2)
    for address in halts:
        if address + 1 >= len(words):
            raise ValueError(f"{path}: halt address {address} is outside the {len(words)}-word ROM")
        if words[address] != address or words[address + 1] != halt_jump:
            raise ValueError(f"{path}: halt address {address} does not point to an @address; 0;JMP self-loop")
    return LoadedHack(
        words,
        AssemblyMetadata(tuple(halts), tuple(assertions), max_steps, hook_path or DEFAULT_HOOK_PATH),
        tuple(word_comments),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble a Hack .asm program into annotated .hack machine code")
    _ = parser.add_argument("source", type=Path)
    _ = parser.add_argument("-o", "--output", type=Path, required=True)
    _ = parser.add_argument(
        "--comments",
        choices=COMMENT_LEVELS,
        default="summary",
        help="explanatory artifact comments: none, summary (default), or full",
    )
    args = parser.parse_args()

    try:
        source = Path(args.source)
        output = Path(args.output)
        assembly = assemble(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        write_hack(assembly, output, args.comments)
    except (AssemblyError, OSError, ValueError) as error:
        parser.error(str(error))

    print(f"ASSEMBLED {source} -> {output} ({len(assembly.records)} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
