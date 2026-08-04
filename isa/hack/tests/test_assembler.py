from pathlib import Path

import pytest

from isa.hack.tools.assembler import (
    AssemblyError,
    apply_runtime_overrides,
    assemble_text,
    load_hack,
    source_description,
    write_hack,
)


def test_valid_hack_symbols_and_numeric_label_rejection() -> None:
    result = assemble_text("($loop.1:)\n@$loop.1:\n0;JMP\n@variable_name\nM=1\n")
    assert result.words[0] == 0
    assert result.words[2] == 16
    assert assemble_text("@R0\n@R15\n").words == [0, 15]

    for source in ("(123)\n", "(bad-name)\n", "@12abc\n", "@bad-name\n", "@\n"):
        with pytest.raises(AssemblyError):
            assemble_text(source)


def test_pseudoinstruction_expansion_preserves_source_mapping() -> None:
    source = "  SET R0, 16 // original comment\nHALT\n.assert R0 == 16\n"
    result = assemble_text(source)

    assert [record.expansion.instruction for record in result.records[:4] if record.expansion] == [
        "@16", "D=A", "@R0", "M=D"
    ]
    assert [
        (record.expansion.index, record.expansion.count)
        for record in result.records[:4]
        if record.expansion
    ] == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert all(record.source.line == 1 for record in result.records[:4])
    assert all(record.source.text == "  SET R0, 16 // original comment" for record in result.records[:4])
    assert result.metadata.halt_addresses == (4,)
    assert result.metadata.assertions[0].target == "R0"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("MOV R1, R0", ["@R0", "D=M", "@R1", "M=D"]),
        ("CLR R0", ["@R0", "M=0"]),
        ("ADD R0, R1", ["@R1", "D=M", "@R0", "M=D+M"]),
        ("SUB R0, R1", ["@R1", "D=M", "@R0", "M=M-D"]),
        ("AND R0, R1", ["@R1", "D=M", "@R0", "M=D&M"]),
        ("OR R0, R1", ["@R1", "D=M", "@R0", "M=D|M"]),
        ("NEG R0", ["@R0", "M=-M"]),
        ("NOT R0", ["@R0", "M=!M"]),
        ("NOP", ["0"]),
        ("JNE R0, DONE", ["@R0", "D=M", "@DONE", "D;JNE"]),
    ],
)
def test_common_pseudoinstruction_expansions(source: str, expected: list[str]) -> None:
    result = assemble_text(source)

    assert [record.expansion.instruction for record in result.records if record.expansion] == expected
    assert [
        (record.expansion.index, record.expansion.count)
        for record in result.records
        if record.expansion
    ] == [(index, len(expected)) for index in range(1, len(expected) + 1)]


def test_annotated_hack_round_trip(tmp_path: Path) -> None:
    source = (
        ".hook hooks\\trace.sail\n"
        "SET R0, 1\nHALT\n"
        ".assert A == -1\n"
        ".assert signed(R0) < -2\n"
        ".assert unsigned(R1) >= 0x8000\n"
        ".assert unsigned(PC) != 0x20\n"
        ".max_steps 0x20\n"
    )
    result = assemble_text(source)
    output = tmp_path / "program.hack"
    write_hack(result, output, "full")

    contents = output.read_text(encoding="utf-8")
    instruction_lines = [line for line in contents.splitlines() if line and not line.startswith("//")]
    assert len(instruction_lines) == len(result.words)
    assert all(line.split(" //", maxsplit=1)[0] and len(line.split(" //", maxsplit=1)[0]) == 16 for line in instruction_lines)
    assert "ROM[0000] L2: SET R0, 1 [1/4] => @1" in contents
    assert '//%hack format {"version":3}' in contents
    assert '//%hack hook {"path":"hooks/trace.sail"}' in contents
    assert '//%hack assert {"line":5,"mode":"signed","operator":"<","target":"R0","value":-2}' in contents
    assert '//%hack assert {"line":6,"mode":"unsigned","operator":">=","target":"R1","value":32768}' in contents

    loaded = load_hack(output)
    assert loaded.words == result.words
    assert loaded.metadata == result.metadata

    output.write_text("// ordinary comment\n0000000000000001 // mapping\n", encoding="utf-8")
    loaded_plain = load_hack(output)
    assert loaded_plain.words == [1]
    assert loaded_plain.metadata.assertions == ()
    assert loaded_plain.metadata.hook_path == "hooks/default.sail"


def test_runtime_overrides_replace_source_metadata_before_write(tmp_path: Path) -> None:
    source = assemble_text(".hook hooks/default.sail\n.max_steps 9\n@0\n")
    overridden = apply_runtime_overrides(
        source,
        max_steps=3,
        hook="hooks/trace.sail",
    )
    output = tmp_path / "overridden.hack"

    write_hack(overridden, output)
    loaded = load_hack(output)

    assert loaded.metadata.max_steps == 3
    assert loaded.metadata.hook_path == "hooks/trace.sail"
    assert loaded.words == source.words


def test_hook_directive_defaults_normalizes_and_does_not_emit_words() -> None:
    default = assemble_text("@0\n")
    custom = assemble_text(".hook hooks\\trace.sail\n@0\n")

    assert default.words == custom.words == [0]
    assert default.metadata.hook_path == "hooks/default.sail"
    assert custom.metadata.hook_path == "hooks/trace.sail"


def test_description_is_source_only_and_does_not_emit_words(tmp_path: Path) -> None:
    text = ".description Demonstrates the Hack ALU\n@0\n"
    described = assemble_text(text)
    baseline = assemble_text("@0\n")
    output = tmp_path / "described.hack"
    write_hack(described, output)

    assert source_description(text) == "Demonstrates the Hack ALU"
    assert described.words == baseline.words == [0]
    assert described.metadata == baseline.metadata
    assert "description" not in output.read_text(encoding="utf-8")


def test_hack_artifact_comment_levels_preserve_machine_contract(tmp_path: Path) -> None:
    assembly = assemble_text("SET R0, 1 // initialize R0\nHALT\n.assert R0 == 1\n")
    contents: dict[str, str] = {}

    for level in ("none", "summary", "full"):
        output = tmp_path / f"{level}.hack"
        write_hack(assembly, output, level)
        contents[level] = output.read_text(encoding="utf-8")
        loaded = load_hack(output)
        assert loaded.words == assembly.words
        assert loaded.metadata == assembly.metadata

    none_words = [line for line in contents["none"].splitlines() if line and not line.startswith("//")]
    assert all(len(line) == 16 for line in none_words)
    assert "//%hack assert" in contents["none"]
    assert "ROM[0000] L1 [1/4] SET R0, 1 => @1 // initialize R0" in contents["summary"]
    assert "ROM[0000] L1: SET R0, 1 // initialize R0 [1/4] => @1" in contents["full"]

    default_output = tmp_path / "default.hack"
    write_hack(assembly, default_output)
    assert default_output.read_text(encoding="utf-8") == contents["summary"]

    with pytest.raises(ValueError, match="comment level"):
        write_hack(assembly, tmp_path / "invalid.hack", "verbose")


def test_summary_shows_standard_assembly_and_places_inline_comment_last(tmp_path: Path) -> None:
    assembly = assemble_text("@R0 // select RAM[0]\nD=M // load RAM[0]\n")
    output = tmp_path / "ordinary.hack"

    write_hack(assembly, output, "summary")

    contents = output.read_text(encoding="utf-8")
    assert "ROM[0000] L1 @R0 // select RAM[0]" in contents
    assert "ROM[0001] L2 D=M // load RAM[0]" in contents


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("A", 0xFFFF),
        ("D", 0x10),
        ("PC", 12),
        ("R0", 0),
        ("R15", 0xFFFF),
        ("RAM[ 32767 ]", 0xFFFF),
    ],
)
def test_assertion_targets_and_python_integer_values(target: str, expected: int) -> None:
    literal = {"A": "-1", "D": "0x10", "PC": "0b1100", "R0": "0o0", "R15": "65535"}.get(target, "-1")
    result = assemble_text(f"@0\n.assert {target} == {literal}\n")
    assertion = result.metadata.assertions[0]
    assert assertion.value == expected
    assert assertion.target == target.replace(" ", "")
    assert assertion.operator == "=="
    assert assertion.mode == ("unsigned" if assertion.target == "PC" else "bits")
    assert result.words == [0]


@pytest.mark.parametrize(
    ("operator", "literal", "expected"),
    [
        ("==", "-1", 0xFFFF),
        ("!=", "0xFFFF", 0xFFFF),
        ("<", "-1", -1),
        ("<=", "-32_768", -32768),
        (">", "0x7FFF", 32767),
        (">=", "0", 0),
    ],
)
def test_all_assertion_operators_and_default_modes(operator: str, literal: str, expected: int) -> None:
    assertion = assemble_text(f".assert R2 {operator} {literal}\n").metadata.assertions[0]

    assert assertion.operator == operator
    assert assertion.value == expected
    assert assertion.mode == ("bits" if operator in {"==", "!="} else "signed")


def test_explicit_modes_and_pc_canonicalization() -> None:
    result = assemble_text(
        ".assert signed(R0) < -1\n"
        ".assert unsigned( RAM[ 12 ] ) > 0x8000\n"
        ".assert unsigned(D) != -1\n"
        ".assert PC >= 0b10\n"
        ".assert unsigned(PC) <= 0x7fff\n"
    )

    assert result.metadata.assertions == (
        result.metadata.assertions[0].__class__("R0", -1, 1, "<", "signed"),
        result.metadata.assertions[0].__class__("RAM[12]", 0x8000, 2, ">", "unsigned"),
        result.metadata.assertions[0].__class__("D", 0xFFFF, 3, "!=", "unsigned"),
        result.metadata.assertions[0].__class__("PC", 2, 4, ">=", "unsigned"),
        result.metadata.assertions[0].__class__("PC", 0x7FFF, 5, "<=", "unsigned"),
    )


def test_directives_do_not_emit_and_max_steps_is_recorded() -> None:
    result = assemble_text(".assert RAM[12] == 0xCAFE\n.max_steps 1_000\n@0\n")
    assert result.words == [0]
    assert result.metadata.max_steps == 1000
    assert result.metadata.assertions[0].value == 0xCAFE


def test_basic_alu_relational_assertions_do_not_change_machine_words() -> None:
    source = (Path(__file__).parents[1] / "programs/basic_alu.asm").read_text(encoding="utf-8")
    without_assertions = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(".assert")
    )

    asserted = assemble_text(source)
    baseline = assemble_text(without_assertions)

    assert asserted.words == baseline.words
    assert {(assertion.target, assertion.operator, assertion.mode) for assertion in asserted.metadata.assertions} >= {
        ("R6", "!=", "bits"),
        ("R6", "<", "signed"),
        ("R6", "<=", "signed"),
        ("R6", ">", "unsigned"),
    }


@pytest.mark.parametrize(
    "source",
    [
        ".description\n",
        ".description // missing text\n",
        ".description first\n.description second\n",
        ".max_steps 0\n",
        ".max_steps 1\n.max_steps 2\n",
        ".max_steps nope\n",
        ".hook\n",
        ".hook hooks/default.sail\n.hook hooks/trace.sail\n",
        ".hook ../hooks.sail\n",
        ".hook /hooks.sail\n",
        ".hook C:\\hooks.sail\n",
        ".hook hooks.txt\n",
        ".assert R16 == 0\n",
        ".assert RAM[32768] == 0\n",
        ".assert PC == -1\n",
        ".assert PC < 32768\n",
        ".assert signed(PC) < 1\n",
        ".assert signed(A) < -32769\n",
        ".assert signed(A) >= 32768\n",
        ".assert unsigned(A) < -1\n",
        ".assert unsigned(A) >= 65536\n",
        ".assert A == 65536\n",
        ".assert A === 1\n",
        ".assert A <> 1\n",
        ".assert A = 1\n",
        ".assert absolute(A) < 1\n",
        ".assert signed() < 1\n",
        ".assert unsigned(R16) < 1\n",
        ".unknown 1\n",
        "SET R0 1\n",
        "MOV R0 R1\n",
        "ADD R0\n",
        "NEG R0, R1\n",
        "NOP R0\n",
        "JNE R0 DONE\n",
        "D=Q\n",
    ],
)
def test_malformed_inputs(source: str) -> None:
    with pytest.raises(AssemblyError):
        assemble_text(source)


def test_loader_rejects_bad_words_and_metadata(tmp_path: Path) -> None:
    output = tmp_path / "bad.hack"
    hook = '//%hack hook {"path":"hooks/default.sail"}\n'
    assertion = '//%hack assert {"line":1,"mode":"bits","operator":"==","target":"A","value":0}\n'
    malformed_assertions = (
        '//%hack assert {"line":1,"mode":"bits","target":"A","value":0}\n',
        '//%hack assert {"line":1,"mode":"bits","operator":"=","target":"A","value":0}\n',
        '//%hack assert {"line":1,"mode":"magnitude","operator":"==","target":"A","value":0}\n',
        '//%hack assert {"line":1,"mode":"bits","operator":"<","target":"A","value":0}\n',
        '//%hack assert {"line":1,"mode":"signed","operator":"<","target":"PC","value":0}\n',
        '//%hack assert {"line":1,"mode":"signed","operator":"<","target":"A","value":32768}\n',
        '//%hack assert {"line":1,"mode":"unsigned","operator":">","target":"D","value":-1}\n',
        '//%hack assert {"line":1,"mode":"unsigned","operator":"==","target":"R0","value":65536}\n',
        '//%hack assert {"line":1,"mode":"unsigned","operator":"<=","target":"PC","value":32768}\n',
        '//%hack assert {"line":true,"mode":"bits","operator":"==","target":"A","value":0}\n',
        '//%hack assert {"line":1,"mode":"bits","operator":"==","target":"A","value":false}\n',
        '//%hack assert {"extra":0,"line":1,"mode":"bits","operator":"==","target":"A","value":0}\n',
    )
    contents_cases = (
        "000000000000001\n",
        "0000000000000002\n",
        "//%hack max_steps {\"value\":0}\n0000000000000000\n",
        "//%hack mystery {}\n0000000000000000\n",
        "//%hack format {\"version\":3,\"version\":3}\n0000000000000000\n",
        "//%hack format {\"version\":2}\n0000000000000000\n",
        "//%hack format {\"version\":3}\n" + hook + "//%hack format {\"version\":3}\n0000000000000000\n",
        "//%hack format {\"version\":3}\n" + hook + "//%hack halt {\"address\":0}\n0000000000000001\n1110101010000111\n",
        "//%hack format {\"version\":3}\n" + hook + assertion + "//%hack max_steps {\"value\":0}\n0000000000000000\n",
        *("//%hack format {\"version\":3}\n" + hook + item + "0000000000000000\n" for item in malformed_assertions),
        "0000000000000000 trailing\n",
    )
    for contents in contents_cases:
        output.write_text(contents, encoding="utf-8")
        with pytest.raises(ValueError):
            load_hack(output)


@pytest.mark.parametrize(
    "metadata",
    [
        '//%hack format {"version":3}\n0000000000000000\n',
        '//%hack format {"version":3}\n//%hack hook {"path":"hooks\\\\trace.sail"}\n0000000000000000\n',
        '//%hack format {"version":3}\n//%hack hook {"path":"../hooks.sail"}\n0000000000000000\n',
        '//%hack format {"version":3}\n//%hack hook {"path":"hooks.txt"}\n0000000000000000\n',
        '//%hack format {"version":3}\n//%hack hook {"path":"hooks/default.sail"}\n//%hack hook {"path":"hooks/trace.sail"}\n0000000000000000\n',
    ],
)
def test_loader_strictly_validates_hook_metadata(tmp_path: Path, metadata: str) -> None:
    output = tmp_path / "bad-hook.hack"
    output.write_text(metadata, encoding="utf-8")

    with pytest.raises(ValueError):
        load_hack(output)


@pytest.mark.parametrize(
    ("mnemonic", "encoding"),
    [
        ("0", "0101010"), ("1", "0111111"), ("-1", "0111010"), ("D", "0001100"),
        ("A", "0110000"), ("!D", "0001101"), ("!A", "0110001"), ("-D", "0001111"),
        ("-A", "0110011"), ("D+1", "0011111"), ("A+1", "0110111"), ("D-1", "0001110"),
        ("A-1", "0110010"), ("D+A", "0000010"), ("D-A", "0010011"), ("A-D", "0000111"),
        ("D&A", "0000000"), ("D|A", "0010101"), ("M", "1110000"), ("!M", "1110001"),
        ("-M", "1110011"), ("M+1", "1110111"), ("M-1", "1110010"), ("D+M", "1000010"),
        ("D-M", "1010011"), ("M-D", "1000111"), ("D&M", "1000000"), ("D|M", "1010101"),
    ],
)
def test_official_comp_encodings(mnemonic: str, encoding: str) -> None:
    word = assemble_text(f"D={mnemonic}\n").words[0]
    assert f"{word:016b}" == f"111{encoding}010000"


@pytest.mark.parametrize(
    ("destination", "encoding"),
    [("", "000"), ("M", "001"), ("D", "010"), ("MD", "011"),
     ("A", "100"), ("AM", "101"), ("AD", "110"), ("AMD", "111")],
)
def test_official_destination_encodings(destination: str, encoding: str) -> None:
    instruction = "0" if destination == "" else f"{destination}=0"
    word = assemble_text(f"{instruction}\n").words[0]
    assert f"{word:016b}" == f"1110101010{encoding}000"


@pytest.mark.parametrize(
    ("jump", "encoding"),
    [("", "000"), ("JGT", "001"), ("JEQ", "010"), ("JGE", "011"),
     ("JLT", "100"), ("JNE", "101"), ("JLE", "110"), ("JMP", "111")],
)
def test_official_jump_encodings(jump: str, encoding: str) -> None:
    instruction = "0" if jump == "" else f"0;{jump}"
    word = assemble_text(f"{instruction}\n").words[0]
    assert f"{word:016b}" == f"1110101010000{encoding}"
