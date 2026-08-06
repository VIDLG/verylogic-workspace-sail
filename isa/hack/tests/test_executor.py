import os
from pathlib import Path

import pytest

from isa.hack.tools import executor
from isa.hack.tools.artifact import LoadedHack, create_hack_manifest, load_hack
from isa.hack.tools.assembler import AssemblyMetadata, Assertion
from isa.hack.tools.executor import artifact_path, write_driver
from isa.hack.tools.profiles import get_profile


def loaded_hack(
    words: list[int],
    metadata: AssemblyMetadata,
    word_comments: tuple[str | None, ...] = (),
    *,
    comments: str = "summary",
    profile_name: str = "hack16",
) -> LoadedHack:
    profile = get_profile(profile_name)
    return LoadedHack(
        profile,
        words,
        metadata,
        word_comments,
        create_hack_manifest(profile, metadata, comments),
    )


def create_staged_closure(_profile: object, output: Path, _driver: Path) -> None:
    artifact_path(output, ".c").write_text("generated C\n", encoding="utf-8")
    artifact_path(output, ".h").write_text("generated H\n", encoding="utf-8")
    executable = artifact_path(output, ".exe") if os.name == "nt" else output
    executable.write_text("executable\n", encoding="utf-8")


def test_driver_rejects_pc_at_or_beyond_rom_end(tmp_path: Path) -> None:
    program = loaded_hack([0], AssemblyMetadata(assertions=(Assertion("A", 0, 1),)))
    driver = tmp_path / "finite.driver.sail"

    write_driver(program, driver, tmp_path / "finite.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "function load_program() -> unit" in generated
    assert "ROM[0] = 0b0000000000000000" in generated
    assert "    hack_step();" in generated
    assert "HackIllegalInstruction" not in generated
    assert "instruction_at" not in generated
    assert "decode_hack(" not in generated
    assert "function run_hack_step" not in generated
    assert "function execution_complete" not in generated
    assert (
        "function execution_should_continue(pc : program_counter, steps : int) -> bool"
        in generated
    )
    assert "let loaded_rom_words : int = 1" in generated
    assert "unsigned(PC) < loaded_rom_words" in generated
    assert "while execution_should_continue(PC, steps)" in generated
    assert (
        'assert (unsigned(PC) < loaded_rom_words, "program counter left the loaded ROM image")'
        in generated
    )
    assert 'print_endline("ASSERT PASS")' in generated


def test_hack32_driver_uses_profile_word_width_and_assertions(tmp_path: Path) -> None:
    metadata = AssemblyMetadata(assertions=(Assertion("A", 0xFFFFFFFF, 1),))
    program = loaded_hack([0x0000002A, 0xFFFFE308], metadata, profile_name="hack32")
    driver = tmp_path / "hack32.driver.sail"

    write_driver(program, driver, tmp_path / "hack32.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "ROM[0] = 0b00000000000000000000000000101010" in generated
    assert "ROM[1] = 0b11111111111111111110001100001000" in generated
    assert "A == 0xFFFFFFFF" in generated


def test_driver_comment_levels_control_teaching_annotations(tmp_path: Path) -> None:
    metadata = AssemblyMetadata(assertions=(Assertion("A", 0, 3),))
    word_comments = ("ROM[0000] L2: @0",)
    contents: dict[str, str] = {}

    for level in ("none", "summary", "full"):
        program = loaded_hack([0], metadata, word_comments, comments=level)
        driver = tmp_path / f"{level}.driver.sail"
        write_driver(program, driver, tmp_path / "program.hack", level)
        contents[level] = driver.read_text(encoding="utf-8")

    assert "//" not in contents["none"]
    assert "Annotated image: <memory>" in contents["summary"]
    assert "Runtime: max_steps=100000 (default)" in contents["summary"]
    assert "Loaded artifact size, not an execution step limit" in contents["summary"]
    assert "Load raw machine words into the model-owned ROM" in contents["summary"]
    assert "Return whether another instruction attempt may begin" in contents["summary"]
    assert "Load the ROM, run while another attempt is allowed" in contents["summary"]
    assert "Run one model-owned fetch, decode, and execute step" in contents["summary"]
    assert "ROM[0000] L2: @0" in contents["summary"]
    assert "Source line 3: .assert A == 0x0000" not in contents["summary"]
    assert "Source line 3: .assert A == 0x0000" in contents["full"]
    assert "Sail assertions and exit status determine success" in contents["full"]

    default_driver = tmp_path / "default.driver.sail"
    default_program = loaded_hack([0], metadata, word_comments)
    write_driver(default_program, default_driver, tmp_path / "program.hack")
    assert default_driver.read_text(encoding="utf-8") == contents["summary"]

    with pytest.raises(ValueError, match="comment level"):
        write_driver(
            default_program,
            tmp_path / "invalid.driver.sail",
            tmp_path / "program.hack",
            "verbose",
        )


def test_bounded_nonterminating_driver_runs_exact_steps(tmp_path: Path) -> None:
    metadata = AssemblyMetadata(
        assertions=(Assertion("PC", 1, 5, "==", "bits", "PC"),),
        max_steps=3,
        max_steps_origin="source",
    )
    program = loaded_hack([0, int("1110101010000111", 2)], metadata)
    driver = tmp_path / "bounded.driver.sail"

    write_driver(
        program,
        driver,
        tmp_path / "bounded.hack",
        bounded_snapshot=True,
    )

    generated = driver.read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 3" in generated
    assert "steps < driver_max_steps" in generated
    assert "maximum step limit reached" not in generated


def test_watchdog_helper_checks_halt_image_and_step_budget(tmp_path: Path) -> None:
    metadata = AssemblyMetadata(
        halt_addresses=(1,),
        assertions=(Assertion("PC", 1, 5, "==", "bits", "PC"),),
        max_steps=3,
        max_steps_origin="source",
    )
    program = loaded_hack([0, int("1110101010000111", 2)], metadata)
    driver = tmp_path / "watchdog.driver.sail"

    write_driver(program, driver, tmp_path / "watchdog.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "let lowered_halt_0 : program_counter = 0b000000000000001" in generated
    assert "Lowered HALT metadata at ROM[0001]; not an ISA encoding" in generated
    assert "pc != lowered_halt_0" in generated
    assert "PC == lowered_halt_0" in generated
    assert "let loaded_rom_words : int = 2" in generated
    assert "unsigned(PC) < loaded_rom_words" in generated
    assert (
        'assert (unsigned(PC) < loaded_rom_words, "program counter left the loaded ROM image")'
        in generated
    )
    assert "let driver_max_steps : int = 3" in generated
    assert "steps < driver_max_steps" in generated
    assert "maximum step limit reached before lowered HALT" in generated
    assert "function execution_complete" not in generated


def test_bounded_snapshot_rejects_ambiguous_completion_contracts(
    tmp_path: Path,
) -> None:
    assertion = Assertion("PC", 0, 1, "==", "bits", "PC")
    cases = (
        loaded_hack([0], AssemblyMetadata(assertions=(assertion,))),
        loaded_hack(
            [0],
            AssemblyMetadata(
                halt_addresses=(0,),
                assertions=(assertion,),
                max_steps=1,
                max_steps_origin="source",
            ),
        ),
        loaded_hack(
            [0],
            AssemblyMetadata(max_steps=1, max_steps_origin="source"),
        ),
    )

    for index, program in enumerate(cases):
        with pytest.raises(ValueError, match="bounded snapshot requires"):
            write_driver(
                program,
                tmp_path / f"invalid-{index}.driver.sail",
                tmp_path / f"invalid-{index}.hack",
                bounded_snapshot=True,
            )


def test_driver_generates_bit_exact_signed_unsigned_and_pc_assertions(
    tmp_path: Path,
) -> None:
    assertions = (
        Assertion("A", 0xFFFF, 1, "==", "bits"),
        Assertion("D", 0, 2, "!=", "bits"),
        Assertion("R0", -1, 3, "<", "signed"),
        Assertion("RAM[12]", -32768, 4, "<=", "signed"),
        Assertion("R1", 0x8000, 5, ">", "unsigned"),
        Assertion("R2", 42, 6, ">=", "unsigned"),
        Assertion("PC", 7, 7, ">", "unsigned"),
    )
    program = loaded_hack([0], AssemblyMetadata(assertions=assertions))
    driver = tmp_path / "assertions.driver.sail"

    write_driver(program, driver, tmp_path / "assertions.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "A == 0xFFFF" in generated
    assert "D != 0x0000" in generated
    assert "signed(RAM[0]) < -1" in generated
    assert "signed(RAM[12]) <= -32768" in generated
    assert "unsigned(RAM[1]) > 32768" in generated
    assert "unsigned(RAM[2]) >= 42" in generated
    assert "unsigned(PC) > 7" in generated
    assert '"assertion signed(R0) < -1 from source line 3 failed"' in generated
    assert '"assertion unsigned(PC) > 7 from source line 7 failed"' in generated


def test_equality_driver_is_bit_exact_and_unwrapped(tmp_path: Path) -> None:
    assertion = Assertion("R6", 0xFFFB, 9, "!=", "bits", "R6")
    program = loaded_hack([0], AssemblyMetadata(assertions=(assertion,)))
    driver = tmp_path / "equality.driver.sail"

    write_driver(program, driver, tmp_path / "equality.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "RAM[6] != 0xFFFB" in generated
    assert "signed(RAM[6])" not in generated
    assert "assertion R6 != 0xFFFB" in generated


def test_cli_overrides_are_serialized_before_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "program.asm"
    source.write_text(".max_steps 9\n@0\nHALT\n", encoding="utf-8")
    compiled: list[tuple[Path, Path]] = []

    def capture_compile(_profile: object, output: Path, driver: Path) -> None:
        compiled.append((output, driver))
        create_staged_closure(_profile, output, driver)

    monkeypatch.setattr(executor, "compile_and_run", capture_compile)

    executor.run(source, tmp_path / "output", max_steps=3)

    artifact = load_hack(tmp_path / "output.hack")
    assert artifact.metadata.max_steps == 3
    assert artifact.metadata.max_steps_origin == "cli"
    assert len(compiled) == 1
    assert compiled[0][1].name == "output.driver.sail_project"
    generated = (tmp_path / "output.driver.sail").read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 3" in generated


def test_default_watchdog_is_not_bounded_snapshot_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "loop.asm"
    source.write_text("(LOOP)\n@LOOP\n0;JMP\n.assert PC == 0\n", encoding="utf-8")
    monkeypatch.setattr(executor, "compile_and_run", create_staged_closure)

    executor.run(source, tmp_path / "loop")

    generated = (tmp_path / "loop.driver.sail").read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 100000" in generated
    assert "steps < driver_max_steps" in generated
    assert (
        "maximum step limit reached without lowered HALT or an explicit bounded snapshot"
        in generated
    )


def test_explicit_limit_with_assertions_selects_bounded_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "snapshot.asm"
    source.write_text(
        ".max_steps 3\n(LOOP)\n@LOOP\n0;JMP\n.assert PC == 1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(executor, "compile_and_run", create_staged_closure)

    executor.run(source, tmp_path / "snapshot")

    generated = (tmp_path / "snapshot.driver.sail").read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 3" in generated
    assert "steps < driver_max_steps" in generated
    assert "maximum step limit reached" not in generated


def test_failed_staged_run_preserves_previous_successful_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "program.asm"
    source.write_text("HALT\n", encoding="utf-8")
    output = tmp_path / "program"
    final = (
        artifact_path(output, ".hack"),
        artifact_path(output, ".driver.sail"),
        artifact_path(output, ".driver.sail_project"),
        artifact_path(output, ".c"),
        artifact_path(output, ".h"),
        artifact_path(output, ".exe") if os.name == "nt" else output,
    )
    for path in final:
        path.write_text(f"old {path.name}\n", encoding="utf-8")

    def fail_compile(_profile: object, staged_output: Path, _driver: Path) -> None:
        artifact_path(staged_output, ".c").write_text("partial\n", encoding="utf-8")
        raise OSError("host compile failed")

    monkeypatch.setattr(executor, "compile_and_run", fail_compile)

    with pytest.raises(OSError, match="host compile failed"):
        executor.run(source, output)

    assert [path.read_text(encoding="utf-8") for path in final] == [
        f"old {path.name}\n" for path in final
    ]


def test_artifact_path_appends_suffix_to_complete_prefix() -> None:
    assert artifact_path(Path("program.v1"), ".hack") == Path("program.v1.hack")
