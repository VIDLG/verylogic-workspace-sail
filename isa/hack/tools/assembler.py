from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from isa.hack.tools.profiles import DEFAULT_PROFILE, Profile, get_profile
from tools.isa_support.directives import (
    AssertionDirective,
    DescriptionDirective,
    DirectiveAccumulator,
    DirectiveSyntaxError,
    MaxStepsDirective,
    parse_directive,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

COMP = {
    "0": "0101010",
    "1": "0111111",
    "-1": "0111010",
    "D": "0001100",
    "A": "0110000",
    "!D": "0001101",
    "!A": "0110001",
    "-D": "0001111",
    "-A": "0110011",
    "D+1": "0011111",
    "A+1": "0110111",
    "D-1": "0001110",
    "A-1": "0110010",
    "D+A": "0000010",
    "D-A": "0010011",
    "A-D": "0000111",
    "D&A": "0000000",
    "D|A": "0010101",
    "M": "1110000",
    "!M": "1110001",
    "-M": "1110011",
    "M+1": "1110111",
    "M-1": "1110010",
    "D+M": "1000010",
    "D-M": "1010011",
    "M-D": "1000111",
    "D&M": "1000000",
    "D|M": "1010101",
}
DEST = {
    "": "000",
    "M": "001",
    "D": "010",
    "MD": "011",
    "A": "100",
    "AM": "101",
    "AD": "110",
    "AMD": "111",
}
JUMP = {
    "": "000",
    "JGT": "001",
    "JEQ": "010",
    "JGE": "011",
    "JLT": "100",
    "JNE": "101",
    "JLE": "110",
    "JMP": "111",
}
REGISTER_SYMBOLS = {f"R{index}": index for index in range(16)}
SYMBOLS = {
    **REGISTER_SYMBOLS,
    "SP": 0,
    "LCL": 1,
    "ARG": 2,
    "THIS": 3,
    "THAT": 4,
    "SCREEN": 16384,
    "KBD": 24576,
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
DEFAULT_MAX_STEPS = 100_000
ASSERT_TARGET_RE = re.compile(
    r"A|D|PC|R(?:[0-9]|1[0-5])|RAM\[\s*(?:0|[1-9][0-9]*)\s*\]"
)
ASSERT_WRAPPER_RE = re.compile(r"(?P<mode>signed|unsigned)\s*\(\s*(?P<target>.*?)\s*\)")
EQUALITY_OPERATORS = {"==", "!="}
RELATIONAL_OPERATORS = {"<", "<=", ">", ">="}
ASSERTION_OPERATORS = EQUALITY_OPERATORS | RELATIONAL_OPERATORS
ASSERTION_MODES = {"bits", "signed", "unsigned"}
PSEUDO_NAMES = {
    "SET",
    "MOV",
    "CLR",
    "INC",
    "DEC",
    "ADD",
    "SUB",
    "AND",
    "OR",
    "NEG",
    "NOT",
    "NOP",
    "GOTO",
    "JNZ",
    "JNE",
    "JGT",
    "JEQ",
    "JGE",
    "JLT",
    "JLE",
    "HALT",
}
PSEUDO_PATTERNS = {
    "SET": re.compile(
        r"SET\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "MOV": re.compile(
        r"MOV\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "CLR": re.compile(r"CLR\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "INC": re.compile(r"INC\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "DEC": re.compile(r"DEC\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "ADD": re.compile(
        r"ADD\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "SUB": re.compile(
        r"SUB\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "AND": re.compile(
        r"AND\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "OR": re.compile(
        r"OR\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "NEG": re.compile(r"NEG\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "NOT": re.compile(r"NOT\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "NOP": re.compile(r"NOP", re.IGNORECASE),
    "GOTO": re.compile(r"GOTO\s+(?P<first>[^,\s]+)", re.IGNORECASE),
    "JNZ": re.compile(
        r"JNZ\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "JNE": re.compile(
        r"JNE\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "JGT": re.compile(
        r"JGT\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "JEQ": re.compile(
        r"JEQ\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "JGE": re.compile(
        r"JGE\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "JLT": re.compile(
        r"JLT\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "JLE": re.compile(
        r"JLE\s+(?P<first>[^,\s]+)\s*,\s*(?P<second>[^,\s]+)", re.IGNORECASE
    ),
    "HALT": re.compile(r"HALT", re.IGNORECASE),
}


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


Statement: TypeAlias = (
    AInstruction
    | CInstruction
    | Label
    | PseudoInstruction
    | AssertionDirective
    | MaxStepsDirective
    | DescriptionDirective
)
Instruction: TypeAlias = AInstruction | CInstruction


@dataclass(frozen=True)
class Assertion:
    target: str
    value: int
    line: int
    operator: str = "=="
    mode: str = "bits"
    display_target: str | None = None

    def __post_init__(self) -> None:
        if self.display_target is None:
            display = (
                self.target if self.mode == "bits" else f"{self.mode}({self.target})"
            )
            object.__setattr__(self, "display_target", display)


@dataclass(frozen=True)
class AssemblyMetadata:
    halt_addresses: tuple[int, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    max_steps: int = DEFAULT_MAX_STEPS
    description: str | None = None
    max_steps_origin: str = "default"
    source_kind: str = "asm"
    source_path: str = "<memory>"


@dataclass(frozen=True)
class MachineWord:
    value: int
    source: SourceLine
    expansion: PseudoExpansion | None = None


@dataclass(frozen=True)
class AssemblyResult:
    profile: Profile
    records: tuple[MachineWord, ...]
    metadata: AssemblyMetadata

    @property
    def words(self) -> list[int]:
        return [record.value for record in self.records]


class Parser:
    def parse(self, text: str) -> list[Statement]:
        statements: list[Statement] = []
        public_directives = DirectiveAccumulator()
        for line_number, raw in enumerate(text.splitlines(), start=1):
            code = raw.split("//", maxsplit=1)[0].strip()
            if not code:
                continue
            source = SourceLine(line_number, raw)

            try:
                directive = parse_directive(code, line_number)
                public_directives.add(directive)
            except DirectiveSyntaxError as error:
                message = str(error).removeprefix(f"line {error.line}: ")
                raise AssemblyError(error.line, message) from error
            if directive is not None:
                statements.append(directive)
                continue

            if code.startswith("."):
                raise AssemblyError(
                    line_number, f"unknown directive {code.split()[0]!r}"
                )

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

    def _parse_pseudo(
        self, code: str, source: SourceLine, name: str
    ) -> PseudoInstruction:
        match = PSEUDO_PATTERNS[name].fullmatch(code)
        if match is None:
            raise AssemblyError(source.line, f"invalid {name} pseudoinstruction")
        arguments = tuple(
            value
            for key in ("first", "second")
            if (value := match.groupdict().get(key)) is not None
        )
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


def parse_python_int(token: str, line: int) -> int:
    if PYTHON_INT_RE.fullmatch(token) is None:
        raise AssemblyError(line, f"invalid integer {token!r}")
    return int(token, 0)


def parse_expected_value(
    token: str,
    line: int,
    target: str,
    operator: str,
    mode: str,
    profile: Profile,
) -> int:
    value = parse_python_int(token, line)
    if target == "PC":
        if not 0 <= value < (1 << profile.pc_bits):
            raise AssemblyError(line, "PC assertion value must be in 0..32767")
        return value
    signed_minimum = -(1 << (profile.word_bits - 1))
    signed_maximum = (1 << (profile.word_bits - 1)) - 1
    unsigned_maximum = profile.word_mask
    if operator in EQUALITY_OPERATORS:
        if not signed_minimum <= value <= unsigned_maximum:
            raise AssemblyError(
                line,
                f"bit-exact assertion value must fit a signed or unsigned {profile.word_bits}-bit word",
            )
        return value & profile.word_mask
    if mode == "signed":
        if not signed_minimum <= value <= signed_maximum:
            raise AssemblyError(
                line,
                f"signed relational assertion value must be in {signed_minimum}..{signed_maximum}",
            )
        return value
    if not 0 <= value <= unsigned_maximum:
        raise AssemblyError(
            line,
            f"unsigned relational assertion value must be in 0..{unsigned_maximum}",
        )
    return value


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


def _source_identity(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return path.name


def _assertion_from_directive(
    statement: AssertionDirective, profile: Profile
) -> Assertion:
    target = canonical_assertion_target(statement.target, statement.line)
    if target == "PC" and statement.mode == "signed":
        raise AssemblyError(
            statement.line,
            "signed(PC) is invalid because PC is an unsigned 15-bit value",
        )
    value = parse_expected_value(
        str(statement.value),
        statement.line,
        target,
        statement.operator,
        statement.mode,
        profile,
    )
    return Assertion(
        target,
        value,
        statement.line,
        statement.operator,
        statement.mode,
        statement.display_target,
    )


def _expanded_instruction(
    parser: Parser, source: SourceLine, text: str, index: int, count: int
) -> Instruction:
    return parser._parse_instruction(text, source, PseudoExpansion(text, index, count))


def _validate_profile_operand(operand: str, line: int, maximum: int, role: str) -> None:
    if DECIMAL_RE.fullmatch(operand) is not None and int(operand) > maximum:
        raise AssemblyError(line, f"{role} must be in 0..{maximum}")


def expand(
    statements: list[Statement], profile: Profile
) -> tuple[
    list[Instruction | Label],
    list[AssertionDirective],
    MaxStepsDirective | None,
    list[tuple[SourceLine, str]],
]:
    parser = Parser()
    code: list[Instruction | Label] = []
    assertions: list[AssertionDirective] = []
    max_steps: MaxStepsDirective | None = None
    halts: list[tuple[SourceLine, str]] = []
    halt_index = 0

    for statement in statements:
        if isinstance(statement, AssertionDirective):
            assertions.append(statement)
        elif isinstance(statement, MaxStepsDirective):
            max_steps = statement
        elif isinstance(statement, DescriptionDirective):
            continue
        elif not isinstance(statement, PseudoInstruction):
            code.append(statement)
        else:
            name = statement.name
            args = statement.arguments
            address_operands = {
                "SET": args[:1],
                "MOV": args,
                "CLR": args,
                "INC": args,
                "DEC": args,
                "ADD": args,
                "SUB": args,
                "AND": args,
                "OR": args,
                "NEG": args,
                "NOT": args,
                "GOTO": args,
                "JNZ": args,
                "JNE": args,
                "JGT": args,
                "JEQ": args,
                "JGE": args,
                "JLT": args,
                "JLE": args,
            }.get(name, ())
            for operand in address_operands:
                _validate_profile_operand(
                    operand,
                    statement.source.line,
                    profile.ram_words - 1,
                    "Hack memory/jump address",
                )
            if name == "SET":
                _validate_profile_operand(
                    args[1],
                    statement.source.line,
                    profile.a_immediate_max,
                    f"{profile.name} A-instruction value",
                )
                expanded = [f"@{args[1]}", "D=A", f"@{args[0]}", "M=D"]
            elif name == "MOV":
                expanded = [f"@{args[1]}", "D=M", f"@{args[0]}", "M=D"]
            elif name == "CLR":
                expanded = [f"@{args[0]}", "M=0"]
            elif name == "INC":
                expanded = [f"@{args[0]}", "M=M+1"]
            elif name == "DEC":
                expanded = [f"@{args[0]}", "M=M-1"]
            elif name in {"ADD", "SUB", "AND", "OR"}:
                operation = {"ADD": "D+M", "SUB": "M-D", "AND": "D&M", "OR": "D|M"}[
                    name
                ]
                expanded = [f"@{args[1]}", "D=M", f"@{args[0]}", f"M={operation}"]
            elif name in {"NEG", "NOT"}:
                operation = "-M" if name == "NEG" else "!M"
                expanded = [f"@{args[0]}", f"M={operation}"]
            elif name == "NOP":
                expanded = ["0"]
            elif name == "GOTO":
                expanded = [f"@{args[0]}", "0;JMP"]
            elif name in {"JNZ", "JNE", "JGT", "JEQ", "JGE", "JLT", "JLE"}:
                jump = "JNE" if name in {"JNZ", "JNE"} else name
                expanded = [f"@{args[0]}", "D=M", f"@{args[1]}", f"D;{jump}"]
            elif name == "HALT":
                label = f"__HACKPLUS_HALT_{halt_index}"
                halt_index += 1
                code.append(Label(statement.source, label))
                halts.append((statement.source, label))
                expanded = [f"@{label}", "0;JMP"]
            else:
                raise AssertionError(f"unhandled pseudoinstruction {name}")
            count = len(expanded)
            code.extend(
                _expanded_instruction(parser, statement.source, text, index, count)
                for index, text in enumerate(expanded, start=1)
            )
    return code, assertions, max_steps, halts


def assemble_text(
    text: str,
    *,
    source: str = "<memory>",
    source_kind: str = "asm",
    profile: str = DEFAULT_PROFILE,
) -> AssemblyResult:
    selected_profile = get_profile(profile)
    statements = parse(text)
    code, assertion_directives, max_steps_directive, halt_labels = expand(
        statements, selected_profile
    )
    symbols = SYMBOLS.copy()
    instructions: list[Instruction] = []
    address = 0

    for statement in code:
        if isinstance(statement, Label):
            if statement.name in symbols:
                raise AssemblyError(
                    statement.source.line, f"duplicate symbol {statement.name!r}"
                )
            symbols[statement.name] = address
        else:
            instructions.append(statement)
            address += 1
            if address > selected_profile.rom_words:
                raise AssemblyError(
                    statement.source.line,
                    f"program exceeds the {selected_profile.rom_words}-word Hack ROM",
                )

    next_variable = 16
    records: list[MachineWord] = []
    for instruction in instructions:
        if isinstance(instruction, AInstruction):
            operand = instruction.operand
            if DECIMAL_RE.fullmatch(operand) is not None:
                value = int(operand)
            else:
                if operand not in symbols:
                    if next_variable >= selected_profile.ram_words:
                        raise AssemblyError(
                            instruction.source.line,
                            "variable allocation exceeds Hack address space",
                        )
                    symbols[operand] = next_variable
                    next_variable += 1
                value = symbols[operand]
            if not 0 <= value <= selected_profile.a_immediate_max:
                raise AssemblyError(
                    instruction.source.line,
                    f"{selected_profile.name} A-instruction value must be in "
                    f"0..{selected_profile.a_immediate_max}",
                )
            word = value
        else:
            canonical = int(
                f"111{COMP[instruction.comp]}{DEST[instruction.dest]}{JUMP[instruction.jump]}",
                2,
            )
            word = selected_profile.encode_c(canonical)
        records.append(MachineWord(word, instruction.source, instruction.expansion))

    halt_addresses = tuple(symbols[label] for _, label in halt_labels)
    assertions = tuple(
        _assertion_from_directive(statement, selected_profile)
        for statement in assertion_directives
    )
    description = next(
        (
            statement.text
            for statement in statements
            if isinstance(statement, DescriptionDirective)
        ),
        None,
    )
    max_steps = (
        DEFAULT_MAX_STEPS if max_steps_directive is None else max_steps_directive.value
    )
    max_steps_origin = "default" if max_steps_directive is None else "source"
    metadata = AssemblyMetadata(
        halt_addresses,
        assertions,
        max_steps,
        description,
        max_steps_origin,
        source_kind,
        source.replace("\\", "/"),
    )
    return AssemblyResult(selected_profile, tuple(records), metadata)


def assemble(
    source: Path,
    *,
    source_kind: str = "asm",
    profile: str = DEFAULT_PROFILE,
) -> AssemblyResult:
    return assemble_text(
        source.read_text(encoding="utf-8"),
        source=_source_identity(source),
        source_kind=source_kind,
        profile=profile,
    )
