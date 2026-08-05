import inspect
from pathlib import Path

import pytest

from isa.hack.tools.artifact import (
    apply_runtime_overrides,
    load_hack,
    write_hack,
)
from isa.hack.tools.assembler import AssemblyError, assemble_text, source_description
from tools.isa_support.manifest import (
    FORMAT_TAG,
    parse_manifest_block,
    render_manifest,
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

    assert [
        record.expansion.instruction
        for record in result.records[:4]
        if record.expansion
    ] == ["@16", "D=A", "@R0", "M=D"]
    assert [
        (record.expansion.index, record.expansion.count)
        for record in result.records[:4]
        if record.expansion
    ] == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert all(record.source.line == 1 for record in result.records[:4])
    assert all(
        record.source.text == "  SET R0, 16 // original comment"
        for record in result.records[:4]
    )
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

    assert [
        record.expansion.instruction for record in result.records if record.expansion
    ] == expected
    assert [
        (record.expansion.index, record.expansion.count)
        for record in result.records
        if record.expansion
    ] == [(index, len(expected)) for index in range(1, len(expected) + 1)]


def test_annotated_hack_round_trip(tmp_path: Path) -> None:
    source = (
        "SET R0, 1\nHALT\n"
        ".assert A == -1\n"
        ".assert signed(R0) < -2\n"
        ".assert unsigned(R1) >= 0x8000\n"
        ".assert PC != 0x20\n"
        ".max_steps 0x20\n"
    )
    result = assemble_text(source)
    output = tmp_path / "program.hack"
    write_hack(result, output, "full")

    contents = output.read_text(encoding="utf-8")
    instruction_lines = [
        line for line in contents.splitlines() if line and not line.startswith("//")
    ]
    assert len(instruction_lines) == len(result.words)
    assert all(
        line.split(" //", maxsplit=1)[0] and len(line.split(" //", maxsplit=1)[0]) == 16
        for line in instruction_lines
    )
    assert "ROM[0000] L1: SET R0, 1 [1/4] => @1" in contents
    lines = contents.splitlines()
    manifest, manifest_lines = parse_manifest_block(lines)
    assert manifest_lines > 1
    assert lines[0].startswith(FORMAT_TAG)
    assert "executor" not in manifest.model_dump(mode="python", by_alias=True)
    assert manifest.runtime.max_steps.model_dump(mode="python") == {
        "value": 32,
        "origin": "source",
    }
    assert manifest.assertions[1].model_dump(mode="python") == {
        "display_target": "signed(R0)",
        "line": 4,
        "mode": "signed",
        "operator": "<",
        "target": "R0",
        "value": -2,
    }

    loaded = load_hack(output)
    assert loaded.words == result.words
    assert loaded.metadata == result.metadata


def test_runtime_overrides_replace_source_metadata_before_write(tmp_path: Path) -> None:
    assert tuple(inspect.signature(apply_runtime_overrides).parameters) == (
        "assembly",
        "max_steps",
    )
    source = assemble_text(".max_steps 9\n@0\n")
    overridden = apply_runtime_overrides(source, max_steps=3)
    output = tmp_path / "overridden.hack"

    write_hack(overridden, output)
    loaded = load_hack(output)

    assert loaded.metadata.max_steps == 3
    assert loaded.metadata.max_steps_origin == "cli"
    assert loaded.words == source.words


def test_description_enters_manifest_without_emitting_words(tmp_path: Path) -> None:
    text = ".description Demonstrates the Hack ALU\n@0\n"
    described = assemble_text(text)
    baseline = assemble_text("@0\n")
    output = tmp_path / "described.hack"
    write_hack(described, output)

    assert source_description(text) == "Demonstrates the Hack ALU"
    assert described.words == baseline.words == [0]
    assert described.metadata.description == "Demonstrates the Hack ALU"
    assert baseline.metadata.description is None
    manifest, _ = parse_manifest_block(output.read_text(encoding="utf-8").splitlines())
    assert manifest.description == "Demonstrates the Hack ALU"


def test_manifest_records_complete_hack_contract_and_default_origins(
    tmp_path: Path,
) -> None:
    assembly = assemble_text(
        ".description Minimal completion\nHALT\n.assert PC == 0\n",
        source="isa/hack/programs/minimal.asm",
    )
    output = tmp_path / "minimal.hack"

    write_hack(assembly, output, "summary")

    lines = output.read_text(encoding="utf-8").splitlines()
    manifest, manifest_lines = parse_manifest_block(lines)
    assert manifest.source.model_dump(mode="python") == {
        "kind": "asm",
        "path": "isa/hack/programs/minimal.asm",
    }
    assert manifest.description == "Minimal completion"
    assert manifest.comments == "summary"
    assert manifest.runtime.model_dump(mode="python") == {
        "max_steps": {"value": 100000, "origin": "default"}
    }
    assert manifest.assertions[0].target == "PC"
    assert manifest.assertions[0].display_target == "PC"
    assert manifest.provenance == {}
    assert manifest.completion.model_dump(mode="python") == {
        "kind": "lowered_self_loop",
        "address_unit": "word",
        "addresses": (0,),
    }
    assert manifest.isa_metadata == {
        "word_bits": 16,
        "address_bits": 15,
        "rom_words": 32768,
        "ram_words": 32768,
    }
    assert "executor" not in manifest.model_dump(mode="python", by_alias=True)
    assert lines[manifest_lines] == "// Annotated image: Minimal completion"


def test_hack_artifact_comment_levels_preserve_machine_contract(tmp_path: Path) -> None:
    assembly = assemble_text("SET R0, 1 // initialize R0\nHALT\n.assert R0 == 1\n")
    contents: dict[str, str] = {}

    for level in ("none", "summary", "full"):
        output = tmp_path / f"{level}.hack"
        write_hack(assembly, output, level)
        contents[level] = output.read_text(encoding="utf-8")
        artifact_lines = contents[level].splitlines()
        _, manifest_lines = parse_manifest_block(artifact_lines)
        if level == "none":
            assert manifest_lines == 1
        else:
            assert manifest_lines > 1
        loaded = load_hack(output)
        assert loaded.words == assembly.words
        assert loaded.metadata == assembly.metadata

    none_words = [
        line
        for line in contents["none"].splitlines()
        if line and not line.startswith("//")
    ]
    assert all(len(line) == 16 for line in none_words)
    assert contents["none"].startswith(FORMAT_TAG)
    assert "// Annotated image:" not in contents["none"]
    assert "ROM[0000] L1 [1/4] SET R0, 1 => @1 // initialize R0" in contents["summary"]
    assert "ROM[0000] L1: SET R0, 1 // initialize R0 [1/4] => @1" in contents["full"]

    default_output = tmp_path / "default.hack"
    write_hack(assembly, default_output)
    assert default_output.read_text(encoding="utf-8") == contents["summary"]

    with pytest.raises(ValueError, match="comment level"):
        write_hack(assembly, tmp_path / "invalid.hack", "verbose")


def test_summary_shows_standard_assembly_and_places_inline_comment_last(
    tmp_path: Path,
) -> None:
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
def test_assertion_targets_and_python_integer_values(
    target: str, expected: int
) -> None:
    literal = {"A": "-1", "D": "0x10", "PC": "0b1100", "R0": "0o0", "R15": "65535"}.get(
        target, "-1"
    )
    result = assemble_text(f"@0\n.assert {target} == {literal}\n")
    assertion = result.metadata.assertions[0]
    assert assertion.value == expected
    assert assertion.target == target.replace(" ", "")
    assert assertion.operator == "=="
    assert assertion.mode == "bits"
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
def test_all_assertion_operators_and_explicit_modes(
    operator: str, literal: str, expected: int
) -> None:
    target = "R2" if operator in {"==", "!="} else "signed(R2)"
    assertion = assemble_text(
        f".assert {target} {operator} {literal}\n"
    ).metadata.assertions[0]

    assert assertion.operator == operator
    assert assertion.value == expected
    assert assertion.mode == ("bits" if operator in {"==", "!="} else "signed")


def test_explicit_modes_and_pc_canonicalization() -> None:
    result = assemble_text(
        ".assert signed(R0) < -1\n"
        ".assert unsigned( RAM[ 12 ] ) > 0x8000\n"
        ".assert D != -1\n"
        ".assert unsigned(PC) >= 0b10\n"
        ".assert unsigned(PC) <= 0x7fff\n"
    )

    assert result.metadata.assertions == (
        result.metadata.assertions[0].__class__(
            "R0", -1, 1, "<", "signed", "signed(R0)"
        ),
        result.metadata.assertions[0].__class__(
            "RAM[12]", 0x8000, 2, ">", "unsigned", "unsigned( RAM[ 12 ] )"
        ),
        result.metadata.assertions[0].__class__("D", 0xFFFF, 3, "!=", "bits", "D"),
        result.metadata.assertions[0].__class__(
            "PC", 2, 4, ">=", "unsigned", "unsigned(PC)"
        ),
        result.metadata.assertions[0].__class__(
            "PC", 0x7FFF, 5, "<=", "unsigned", "unsigned(PC)"
        ),
    )


def test_directives_do_not_emit_and_max_steps_is_recorded() -> None:
    result = assemble_text(".assert RAM[12] == 0xCAFE\n.max_steps 1_000\n@0\n")
    assert result.words == [0]
    assert result.metadata.max_steps == 1000
    assert result.metadata.assertions[0].value == 0xCAFE


def test_basic_alu_relational_assertions_do_not_change_machine_words() -> None:
    source = (Path(__file__).parents[1] / "programs/basic_alu.asm").read_text(
        encoding="utf-8"
    )
    without_assertions = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(".assert")
    )

    asserted = assemble_text(source)
    baseline = assemble_text(without_assertions)

    assert asserted.words == baseline.words
    assert {
        (assertion.target, assertion.operator, assertion.mode)
        for assertion in asserted.metadata.assertions
    } >= {
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
        ".assert R16 == 0\n",
        ".assert RAM[32768] == 0\n",
        ".assert PC == -1\n",
        ".assert PC < 32768\n",
        ".assert signed(PC) < 1\n",
        ".assert R0 < 1\n",
        ".assert signed(R0) == 1\n",
        ".assert unsigned(R0) != 1\n",
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


def test_strict_loader_rejects_manifest_and_hack_metadata_tampering(
    tmp_path: Path,
) -> None:
    output = tmp_path / "strict.hack"
    assembly = assemble_text(
        "@0\nHALT\n.assert A == 0\n",
        source="programs/strict.asm",
    )
    write_hack(assembly, output, "summary")
    original = output.read_text(encoding="utf-8")
    lines = original.splitlines()
    base, manifest_lines = parse_manifest_block(lines)

    assertion = base.assertions[0]
    mutations = (
        base.model_copy(
            update={"source": base.source.model_copy(update={"path": "../escape.asm"})}
        ),
        base.model_copy(
            update={"isa_metadata": {**base.isa_metadata, "word_bits": 15}}
        ),
        base.model_copy(
            update={
                "completion": base.completion.model_copy(update={"addresses": (0,)})
            }
        ),
        base.model_copy(
            update={"assertions": (assertion.model_copy(update={"target": "R16"}),)}
        ),
        base.model_copy(
            update={"assertions": (assertion.model_copy(update={"value": 65536}),)}
        ),
        base.model_copy(
            update={
                "assertions": (assertion.model_copy(update={"display_target": "D"}),)
            }
        ),
    )

    for candidate in mutations:
        output.write_text(
            render_manifest(candidate) + "\n".join(lines[manifest_lines:]) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with pytest.raises(ValueError):
            load_hack(output)

    output.write_text("// ordinary comment\n" + original, encoding="utf-8")
    with pytest.raises(ValueError, match="must begin"):
        load_hack(output)


def test_strict_loader_checks_completion_machine_words_and_none_comments(
    tmp_path: Path,
) -> None:
    output = tmp_path / "strict.hack"
    write_hack(assemble_text("HALT\n"), output, "none")
    contents = output.read_text(encoding="utf-8")

    output.write_text(
        contents.replace("1110101010000111", "0000000000000000"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="self-loop"):
        load_hack(output)

    output.write_text(contents.replace("\n", "\n// injected\n", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="comments=none"):
        load_hack(output)


def test_loader_rejects_raw_hack_without_teaching_manifest(tmp_path: Path) -> None:
    output = tmp_path / "plain.hack"
    output.write_text(
        "// external tool output\n0000000000000001 // @1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must begin"):
        load_hack(output)


@pytest.mark.parametrize(
    ("mnemonic", "encoding"),
    [
        ("0", "0101010"),
        ("1", "0111111"),
        ("-1", "0111010"),
        ("D", "0001100"),
        ("A", "0110000"),
        ("!D", "0001101"),
        ("!A", "0110001"),
        ("-D", "0001111"),
        ("-A", "0110011"),
        ("D+1", "0011111"),
        ("A+1", "0110111"),
        ("D-1", "0001110"),
        ("A-1", "0110010"),
        ("D+A", "0000010"),
        ("D-A", "0010011"),
        ("A-D", "0000111"),
        ("D&A", "0000000"),
        ("D|A", "0010101"),
        ("M", "1110000"),
        ("!M", "1110001"),
        ("-M", "1110011"),
        ("M+1", "1110111"),
        ("M-1", "1110010"),
        ("D+M", "1000010"),
        ("D-M", "1010011"),
        ("M-D", "1000111"),
        ("D&M", "1000000"),
        ("D|M", "1010101"),
    ],
)
def test_official_comp_encodings(mnemonic: str, encoding: str) -> None:
    word = assemble_text(f"D={mnemonic}\n").words[0]
    assert f"{word:016b}" == f"111{encoding}010000"


@pytest.mark.parametrize(
    ("destination", "encoding"),
    [
        ("", "000"),
        ("M", "001"),
        ("D", "010"),
        ("MD", "011"),
        ("A", "100"),
        ("AM", "101"),
        ("AD", "110"),
        ("AMD", "111"),
    ],
)
def test_official_destination_encodings(destination: str, encoding: str) -> None:
    instruction = "0" if destination == "" else f"{destination}=0"
    word = assemble_text(f"{instruction}\n").words[0]
    assert f"{word:016b}" == f"1110101010{encoding}000"


@pytest.mark.parametrize(
    ("jump", "encoding"),
    [
        ("", "000"),
        ("JGT", "001"),
        ("JEQ", "010"),
        ("JGE", "011"),
        ("JLT", "100"),
        ("JNE", "101"),
        ("JLE", "110"),
        ("JMP", "111"),
    ],
)
def test_official_jump_encodings(jump: str, encoding: str) -> None:
    instruction = "0" if jump == "" else f"0;{jump}"
    word = assemble_text(f"{instruction}\n").words[0]
    assert f"{word:016b}" == f"1110101010000{encoding}"
