from pathlib import Path

import pytest

from isa.hack.tools import workflow


def test_bundled_programs_are_discovered_and_selected_from_sources() -> None:
    entries = workflow.discover_programs()

    assert [(entry["name"], entry["description"]) for entry in entries] == [
        ("basic_alu", "ALU arithmetic, bitwise operations, negation, and conditional branch"),
        ("divide", "Repeated-subtraction division: 100 divided by 7"),
        ("fibonacci", "Iterative Fibonacci F(10) with loop control"),
        ("gcd", "Subtraction-based Euclidean GCD of 1071 and 462"),
        ("isa_conformance", "Direct Sail checks for ALU, jumps, destinations, and state transitions"),
        ("multiply", "Repeated-addition multiplication: 6 times 7"),
    ]
    assert workflow.selected_program(entries, "gcd")["source"].name == "gcd.asm"
    with pytest.raises(ValueError, match="unknown program"):
        workflow.selected_program(entries, "missing")


def test_discovery_is_direct_only_and_requires_descriptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "hack"
    programs = package_root / "programs"
    programs.mkdir(parents=True)
    (programs / "zeta.asm").write_text(".description Last\n@0\n", encoding="utf-8")
    (programs / "alpha.asm").write_text(".description First\n@0\n", encoding="utf-8")
    nested = programs / "nested"
    nested.mkdir()
    (nested / "ignored.asm").write_text("@0\n", encoding="utf-8")
    (programs / "ignored.txt").write_text(".description Not assembly\n", encoding="utf-8")
    monkeypatch.setattr(workflow, "PACKAGE_ROOT", package_root)
    monkeypatch.setattr(workflow, "PROGRAMS", programs)

    assert [entry["name"] for entry in workflow.discover_programs()] == ["alpha", "zeta"]

    (programs / "missing.asm").write_text("@0\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"missing\.asm: missing \.description directive"):
        workflow.discover_programs()

    outside = tmp_path / "outside.asm"
    outside.write_text(".description Outside\n@0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes the package"):
        workflow.source_path(outside)


def test_artifact_comment_level_is_forwarded_to_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "program.asm"
    source.write_text(".description Test\n@0\n", encoding="utf-8")
    entry: workflow.Program = {"name": "program", "source": source, "description": "Test"}
    commands: list[list[str]] = []

    monkeypatch.setattr(workflow, "PACKAGE_ROOT", tmp_path)
    monkeypatch.setattr(workflow, "command", lambda args, **_kwargs: commands.append(args))

    workflow.assemble(entry, comments="summary")
    workflow.run(entry, comments="none")

    assert commands[0][-2:] == ["--comments", "summary"]
    assert commands[1][-2:] == ["--comments", "none"]
