from pathlib import Path

import pytest

from isa.hack.tools import executor
from isa.hack.tools.assembler import AssemblyMetadata, Assertion, LoadedHack, load_hack
from isa.hack.tools.executor import artifact, resolve_hook_source, write_driver


def test_driver_rejects_pc_at_or_beyond_rom_end(tmp_path: Path) -> None:
    program = LoadedHack([0], AssemblyMetadata(assertions=(Assertion("A", 0, 1),)))
    driver = tmp_path / "finite.driver.sail"

    write_driver(program, None, driver, tmp_path / "finite.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "function load_program() -> unit" in generated
    assert "ROM[0] = 0b0000000000000000" in generated
    assert "match hack_step()" in generated
    assert "HackIllegalInstruction(_) => assert(false" in generated
    assert "instruction_at" not in generated
    assert "decode_hack(" not in generated
    assert "function run_hack_step" not in generated
    assert "function execution_complete" not in generated
    assert "function execution_should_continue(pc : program_counter, steps : int) -> bool" in generated
    assert "let loaded_rom_words : int = 1" in generated
    assert "unsigned(PC) < loaded_rom_words" in generated
    assert "while execution_should_continue(PC, steps)" in generated
    assert 'assert (unsigned(PC) < loaded_rom_words, "program counter left the loaded ROM image")' in generated
    assert 'print_endline("ASSERT PASS")' in generated
    assert "hack_hook_before_run();" in generated
    assert "hack_hook_before_step(steps);" in generated
    assert "hack_hook_after_step(steps)" in generated
    assert "hack_hook_after_run(steps);" in generated


def test_driver_comment_levels_control_teaching_annotations(tmp_path: Path) -> None:
    metadata = AssemblyMetadata(assertions=(Assertion("A", 0, 3),))
    program = LoadedHack([0], metadata, ("ROM[0000] L2: @0",))
    contents: dict[str, str] = {}

    for level in ("none", "summary", "full"):
        driver = tmp_path / f"{level}.driver.sail"
        write_driver(program, None, driver, tmp_path / "program.hack", level)
        contents[level] = driver.read_text(encoding="utf-8")

    assert "//" not in contents["none"]
    assert "Loaded artifact size, not an execution step limit" in contents["summary"]
    assert "Load raw machine words into the model-owned ROM" in contents["summary"]
    assert "Return whether another instruction attempt may begin" in contents["summary"]
    assert "Load the ROM, run while another attempt is allowed" in contents["summary"]
    assert "Check the model-owned fetch, decode, and execute outcome" in contents["summary"]
    assert "ROM[0000] L2: @0" in contents["summary"]
    assert "Source line 3: .assert A == 0x0000" not in contents["summary"]
    assert "Source line 3: .assert A == 0x0000" in contents["full"]
    assert "Sail assertions and exit status determine success" in contents["full"]

    default_driver = tmp_path / "default.driver.sail"
    write_driver(program, None, default_driver, tmp_path / "program.hack")
    assert default_driver.read_text(encoding="utf-8") == contents["summary"]

    with pytest.raises(ValueError, match="comment level"):
        write_driver(program, None, tmp_path / "invalid.driver.sail", tmp_path / "program.hack", "verbose")


def test_bounded_nonterminating_driver_runs_exact_steps(tmp_path: Path) -> None:
    metadata = AssemblyMetadata(assertions=(Assertion("PC", 1, 5, "==", "unsigned"),), max_steps=3)
    program = LoadedHack([0, int("1110101010000111", 2)], metadata)
    driver = tmp_path / "bounded.driver.sail"

    write_driver(
        program,
        metadata.max_steps,
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
        assertions=(Assertion("PC", 1, 5, "==", "unsigned"),),
        max_steps=3,
    )
    program = LoadedHack([0, int("1110101010000111", 2)], metadata)
    driver = tmp_path / "watchdog.driver.sail"

    write_driver(program, metadata.max_steps, driver, tmp_path / "watchdog.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "let lowered_halt_0 : program_counter = 0b000000000000001" in generated
    assert "Lowered HALT metadata at ROM[0001]; not an ISA encoding" in generated
    assert "pc != lowered_halt_0" in generated
    assert "PC == lowered_halt_0" in generated
    assert "let loaded_rom_words : int = 2" in generated
    assert "unsigned(PC) < loaded_rom_words" in generated
    assert 'assert (unsigned(PC) < loaded_rom_words, "program counter left the loaded ROM image")' in generated
    assert "let driver_max_steps : int = 3" in generated
    assert "steps < driver_max_steps" in generated
    assert "maximum step limit reached before lowered HALT" in generated
    assert "function execution_complete" not in generated


def test_bounded_snapshot_rejects_ambiguous_completion_contracts(tmp_path: Path) -> None:
    assertion = Assertion("PC", 0, 1, "==", "unsigned")
    cases = (
        (LoadedHack([0], AssemblyMetadata(assertions=(assertion,))), None),
        (LoadedHack([0], AssemblyMetadata(halt_addresses=(0,), assertions=(assertion,))), 1),
        (LoadedHack([0], AssemblyMetadata()), 1),
    )

    for index, (program, max_steps) in enumerate(cases):
        with pytest.raises(ValueError, match="bounded snapshot requires"):
            write_driver(
                program,
                max_steps,
                tmp_path / f"invalid-{index}.driver.sail",
                tmp_path / f"invalid-{index}.hack",
                bounded_snapshot=True,
            )


def test_driver_generates_bit_exact_signed_unsigned_and_pc_assertions(tmp_path: Path) -> None:
    assertions = (
        Assertion("A", 0xFFFF, 1, "==", "bits"),
        Assertion("D", 0, 2, "!=", "bits"),
        Assertion("R0", -1, 3, "<", "signed"),
        Assertion("RAM[12]", -32768, 4, "<=", "signed"),
        Assertion("R1", 0x8000, 5, ">", "unsigned"),
        Assertion("R2", 42, 6, ">=", "unsigned"),
        Assertion("PC", 7, 7, ">", "unsigned"),
    )
    program = LoadedHack([0], AssemblyMetadata(assertions=assertions))
    driver = tmp_path / "assertions.driver.sail"

    write_driver(program, None, driver, tmp_path / "assertions.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "A == 0xFFFF" in generated
    assert "D != 0x0000" in generated
    assert "signed(RAM[0]) < -1" in generated
    assert "signed(RAM[12]) <= -32768" in generated
    assert "unsigned(RAM[1]) > 32768" in generated
    assert "unsigned(RAM[2]) >= 42" in generated
    assert "unsigned(PC) > 7" in generated
    assert '"assertion signed(R0) < -1 from source line 3 failed"' in generated
    assert '"assertion PC > 7 from source line 7 failed"' in generated


def test_wrapped_equality_remains_bit_exact(tmp_path: Path) -> None:
    assertion = Assertion("R6", 0xFFFB, 9, "!=", "signed")
    program = LoadedHack([0], AssemblyMetadata(assertions=(assertion,)))
    driver = tmp_path / "equality.driver.sail"

    write_driver(program, None, driver, tmp_path / "equality.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "RAM[6] != 0xFFFB" in generated
    assert "signed(RAM[6])" not in generated
    assert "assertion signed(R6) != 0xFFFB" in generated


def test_hook_source_resolution_uses_package_local_sources() -> None:
    package_root = Path(__file__).parents[1].resolve()

    assert resolve_hook_source("hooks/default.sail") == (package_root / "hooks/default.sail")
    assert resolve_hook_source("hooks/trace.sail") == (package_root / "hooks/trace.sail")
    for hook_path in ("../hooks.sail", "/hooks.sail", "hooks/missing.sail"):
        with pytest.raises((OSError, ValueError)):
            resolve_hook_source(hook_path)


def test_cli_overrides_are_serialized_before_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "program.asm"
    source.write_text(
        ".hook hooks/default.sail\n.max_steps 9\n@0\nHALT\n",
        encoding="utf-8",
    )
    selected: list[Path] = []

    def capture_compile(_output: Path, _driver: Path, hook_source: Path) -> None:
        selected.append(hook_source)

    monkeypatch.setattr(executor, "compile_and_run", capture_compile)

    executor.run(
        source,
        tmp_path / "output",
        max_steps=3,
        hook="hooks/trace.sail",
    )

    artifact = load_hack(tmp_path / "output.hack")
    assert artifact.metadata.max_steps == 3
    assert artifact.metadata.hook_path == "hooks/trace.sail"
    assert selected == [resolve_hook_source("hooks/trace.sail")]
    generated = (tmp_path / "output.driver.sail").read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 3" in generated


def test_run_uses_hook_path_from_reloaded_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "program.asm"
    source.write_text(".hook hooks/trace.sail\n@0\nHALT\n", encoding="utf-8")
    selected: list[Path] = []
    actual_load_hack = load_hack

    def reload_with_default_hook(path: Path) -> LoadedHack:
        loaded = actual_load_hack(path)
        metadata = AssemblyMetadata(
            loaded.metadata.halt_addresses,
            loaded.metadata.assertions,
            loaded.metadata.max_steps,
            "hooks/default.sail",
        )
        return LoadedHack(loaded.words, metadata)

    def capture_compile(_output: Path, _driver: Path, hook_source: Path) -> None:
        selected.append(hook_source)

    monkeypatch.setattr(executor, "load_hack", reload_with_default_hook)
    monkeypatch.setattr(executor, "compile_and_run", capture_compile)

    executor.run(source, tmp_path / "output")

    assert selected == [resolve_hook_source("hooks/default.sail")]
    generated = (tmp_path / "output.driver.sail").read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 100000" in generated
    assert "steps < driver_max_steps" in generated


def test_default_watchdog_is_not_bounded_snapshot_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "loop.asm"
    source.write_text("(LOOP)\n@LOOP\n0;JMP\n.assert PC == 0\n", encoding="utf-8")
    monkeypatch.setattr(executor, "compile_and_run", lambda *_args: None)

    executor.run(source, tmp_path / "loop")

    generated = (tmp_path / "loop.driver.sail").read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 100000" in generated
    assert "steps < driver_max_steps" in generated
    assert "maximum step limit reached without lowered HALT or an explicit bounded snapshot" in generated


def test_explicit_limit_with_assertions_selects_bounded_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "snapshot.asm"
    source.write_text(
        ".max_steps 3\n(LOOP)\n@LOOP\n0;JMP\n.assert PC == 1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(executor, "compile_and_run", lambda *_args: None)

    executor.run(source, tmp_path / "snapshot")

    generated = (tmp_path / "snapshot.driver.sail").read_text(encoding="utf-8")
    assert "let driver_max_steps : int = 3" in generated
    assert "steps < driver_max_steps" in generated
    assert "maximum step limit reached" not in generated


def test_hook_call_order_preserves_core_assertions(tmp_path: Path) -> None:
    program = LoadedHack([0], AssemblyMetadata(assertions=(Assertion("A", 0, 1),)))
    driver = tmp_path / "hooks.driver.sail"

    write_driver(program, None, driver, tmp_path / "hooks.hack")

    generated = driver.read_text(encoding="utf-8")
    assert generated.index("load_program();") < generated.index("hack_hook_before_run();")
    assert generated.index("hack_hook_before_run();") < generated.index("while execution_should_continue(PC, steps)")
    assert generated.index("hack_hook_before_step(steps);") < generated.index("match hack_step()")
    assert generated.index("match hack_step()") < generated.index("hack_hook_after_step(steps)")
    assert generated.index("assert (A == 0x0000") < generated.index("hack_hook_after_run(steps);")


def test_artifact_suffix_is_appended_to_complete_prefix():
    assert artifact(Path("program.v1"), ".hack") == Path("program.v1.hack")
