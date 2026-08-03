from pathlib import Path

import pytest

from isa.hack.tools import executor
from isa.hack.tools.assembler import AssemblyMetadata, Assertion, LoadedHack, load_hack
from isa.hack.tools.executor import artifact, resolve_hook_source, write_driver


def test_driver_stops_at_or_beyond_rom_end(tmp_path: Path) -> None:
    program = LoadedHack([0], AssemblyMetadata(assertions=(Assertion("A", 0, 1),)))
    driver = tmp_path / "finite.driver.sail"

    write_driver(program, None, driver, tmp_path / "finite.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "unsigned(pc) >= 1" in generated
    assert "while execution_complete(PC) == false" in generated
    assert 'print_endline("ASSERT PASS")' in generated
    assert "hack_hook_before_run();" in generated
    assert "hack_hook_before_step(steps);" in generated
    assert "hack_hook_after_step(steps)" in generated
    assert "hack_hook_after_run(steps);" in generated


def test_bounded_nonterminating_driver_runs_exact_steps(tmp_path: Path) -> None:
    metadata = AssemblyMetadata(assertions=(Assertion("PC", 1, 5, "==", "unsigned"),), max_steps=3)
    program = LoadedHack([0, int("1110101010000111", 2)], metadata)
    driver = tmp_path / "bounded.driver.sail"

    write_driver(program, metadata.max_steps, driver, tmp_path / "bounded.hack")

    generated = driver.read_text(encoding="utf-8")
    assert "steps < 3" in generated
    assert "maximum step limit reached" not in generated


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

    assert resolve_hook_source("hooks.sail") == (package_root / "hooks.sail")
    assert resolve_hook_source("hooks/trace.sail") == (package_root / "hooks/trace.sail")
    for hook_path in ("../hooks.sail", "/hooks.sail", "hooks/missing.sail"):
        with pytest.raises((OSError, ValueError)):
            resolve_hook_source(hook_path)


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
            "hooks.sail",
        )
        return LoadedHack(loaded.words, metadata)

    def capture_compile(_output: Path, _driver: Path, hook_source: Path) -> None:
        selected.append(hook_source)

    monkeypatch.setattr(executor, "load_hack", reload_with_default_hook)
    monkeypatch.setattr(executor, "compile_and_run", capture_compile)

    executor.run(source, tmp_path / "output")

    assert selected == [resolve_hook_source("hooks.sail")]


def test_hook_call_order_preserves_core_assertions(tmp_path: Path) -> None:
    program = LoadedHack([0], AssemblyMetadata(assertions=(Assertion("A", 0, 1),)))
    driver = tmp_path / "hooks.driver.sail"

    write_driver(program, None, driver, tmp_path / "hooks.hack")

    generated = driver.read_text(encoding="utf-8")
    assert generated.index("hack_hook_before_run();") < generated.index("while execution_complete")
    assert generated.index("hack_hook_before_step(steps);") < generated.index("execute(instruction_at(PC));")
    assert generated.index("execute(instruction_at(PC));") < generated.index("hack_hook_after_step(steps)")
    assert generated.index("assert (A == 0x0000") < generated.index("hack_hook_after_run(steps);")


def test_artifact_suffix_is_appended_to_complete_prefix():
    assert artifact(Path("program.v1"), ".hack") == Path("program.v1.hack")
