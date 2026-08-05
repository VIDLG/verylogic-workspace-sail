from __future__ import annotations

import argparse
import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.isa_support import host_c, publish
from tools.isa_support.cli import (
    COMMENT_LEVELS,
    positive_int_arg,
    validate_comment_level,
)
from tools.isa_support.directives import (
    AssertionDirective,
    DescriptionDirective,
    DirectiveAccumulator,
    DirectiveSyntaxError,
    MaxStepsDirective,
    parse_directive,
)
from tools.isa_support.manifest import (
    FORMAT_TAG,
    SCHEMA,
    VERSION,
    ArtifactManifest,
    ArtifactManifestEnvelope,
    ManifestError,
    ResolvedValue,
    assertion_source,
    create_manifest,
    parse_manifest,
    parse_manifest_block,
    render_manifest,
    render_preamble,
    resolve_setting,
    validate_manifest,
)
from tools.isa_support.sexpr import SExpressionError, parse_one


def assertion(
    target: str = "R0",
    operator: str = "==",
    value: int = 7,
    mode: str = "bits",
    line: int = 4,
) -> dict[str, object]:
    display_target = target if mode == "bits" else f"{mode}({target})"
    return {
        "target": target,
        "operator": operator,
        "value": value,
        "mode": mode,
        "line": line,
        "display_target": display_target,
    }


def manifest(**changes: object) -> ArtifactManifest:
    values: dict[str, Any] = {
        "isa": "hack",
        "profile": "standard",
        "source": {"kind": "asm", "path": "programs/add.asm"},
        "description": "Add two values",
        "comments": "summary",
        "runtime": {"max_steps": {"value": 100, "origin": "source"}},
        "assertions": [assertion()],
        "provenance": {},
        "completion": {
            "kind": "lowered_self_loop",
            "address_unit": "word",
            "addresses": [7],
        },
        "isa_metadata": {"word_bits": 16},
    }
    values.update(changes)
    return create_manifest(**values)  # type: ignore[arg-type]


def test_cli_comment_levels_and_positive_integer_type() -> None:
    assert COMMENT_LEVELS == ("none", "summary", "full")
    assert [validate_comment_level(level) for level in COMMENT_LEVELS] == list(
        COMMENT_LEVELS
    )
    assert positive_int_arg("0x10") == 16
    with pytest.raises(ValueError, match="invalid comment level"):
        validate_comment_level("verbose")
    for value in ("0", "-1", "12garbage"):
        with pytest.raises(argparse.ArgumentTypeError):
            positive_int_arg(value)


def test_public_directives_parse_without_interpreting_isa_targets() -> None:
    description = parse_directive("  .description Add values  ", 2)
    max_steps = parse_directive(".max_steps 0b1010", 3)
    equality = parse_directive(".assert ISA_SPECIFIC[target] == 0xFF", 4)
    assert description == DescriptionDirective("Add values", 2)
    assert max_steps == MaxStepsDirective(10, 3)
    assert equality == AssertionDirective(
        "ISA_SPECIFIC[target]", "==", 255, "bits", 4, "ISA_SPECIFIC[target]"
    )
    assert parse_directive(".input 2 = 4", 5) is None
    assert parse_directive("addi x1, x0, 1", 6) is None


def test_ordered_assertions_require_and_preserve_explicit_mode_order() -> None:
    signed = parse_directive(".assert signed(R0) < -0o10", 8)
    unsigned = parse_directive(".assert unsigned(MEM[42]) >= 0b11", 9)
    assert isinstance(signed, AssertionDirective)
    assert isinstance(unsigned, AssertionDirective)
    assert (signed.target, signed.operator, signed.value, signed.mode) == (
        "R0",
        "<",
        -8,
        "signed",
    )
    assert (unsigned.target, unsigned.operator, unsigned.value, unsigned.mode) == (
        "MEM[42]",
        ">=",
        3,
        "unsigned",
    )

    accumulator = DirectiveAccumulator()
    accumulator.add(unsigned)
    accumulator.add(signed)
    assert accumulator.assertions == (unsigned, signed)


@pytest.mark.parametrize(
    "source",
    [
        ".assert signed(R0) == 1",
        ".assert unsigned(R0) != 1",
        ".assert R0 < 1",
        ".assert R0 <= 1garbage",
    ],
)
def test_assertion_mode_and_integer_syntax_rejections_include_line(source: str) -> None:
    with pytest.raises(DirectiveSyntaxError, match="line 17") as caught:
        parse_directive(source, 17)
    assert caught.value.line == 17


def test_directive_dataclasses_are_frozen_and_duplicates_are_rejected() -> None:
    parsed = parse_directive(".description first", 1)
    assert isinstance(parsed, DescriptionDirective)
    with pytest.raises(FrozenInstanceError):
        parsed.text = "changed"  # type: ignore[misc]

    accumulator = DirectiveAccumulator()
    accumulator.add(parsed)
    with pytest.raises(DirectiveSyntaxError, match="line 4: duplicate .description"):
        accumulator.add(parse_directive(".description second", 4))
    accumulator.add(parse_directive(".max_steps 1", 5))
    with pytest.raises(DirectiveSyntaxError, match="line 6: duplicate .max_steps"):
        accumulator.add(parse_directive(".max_steps 2", 6))


def test_strict_sexpr_requires_one_supported_top_level_form() -> None:
    with pytest.raises(SExpressionError, match="exactly one top-level"):
        parse_one("(first) (second)", context="lesson")

    for source in (
        "#(1 2)",
        "'foo",
        "(a . b)",
        "[1 2]",
        ":keyword",
        "#t",
        "nil",
        "t",
        "1.5",
    ):
        with pytest.raises(SExpressionError):
            parse_one(source, context="lesson")


def test_resolve_setting_uses_cli_source_default_precedence() -> None:
    assert resolve_setting(30, 20, 10) == ResolvedValue(value=30, origin="cli")
    assert resolve_setting(None, 20, 10) == ResolvedValue(value=20, origin="source")
    assert resolve_setting(None, None, 10) == ResolvedValue(value=10, origin="default")


def test_manifest_models_are_frozen() -> None:
    value = manifest()
    with pytest.raises(ValidationError, match="Instance is frozen"):
        value.comments = "none"  # type: ignore[misc]


def test_manifest_creation_round_trip_and_exact_public_shape() -> None:
    value = manifest()
    assert isinstance(value, ArtifactManifest)
    assert isinstance(value, ArtifactManifestEnvelope)
    assert value.schema_ == SCHEMA == "verylogic.annotated-image"
    assert value.version == VERSION == 1
    dumped = value.model_dump(mode="json", by_alias=True)
    assert set(dumped) == {
        "schema",
        "version",
        "isa",
        "profile",
        "source",
        "description",
        "comments",
        "runtime",
        "assertions",
        "provenance",
        "completion",
        "isa_metadata",
    }
    rendered = render_manifest(value)
    assert parse_manifest(rendered) == value


def test_manifest_rendering_and_block_parsing_follow_comment_level() -> None:
    assert FORMAT_TAG == "//% "
    summary = manifest(comments="summary")
    full = manifest(comments="full")
    none = manifest(comments="none")

    for value in (summary, full):
        rendered = render_manifest(value)
        block = rendered.splitlines()
        assert len(block) > 1
        assert all(line.startswith(FORMAT_TAG) for line in block)
        assert "(provenance" not in rendered
        assert parse_manifest(rendered) == value
        parsed, consumed = parse_manifest_block([*block, "0000000000000000"])
        assert parsed == value
        assert consumed == len(block)

    compact = render_manifest(none)
    assert len(compact.splitlines()) == 1
    assert compact.startswith(FORMAT_TAG + "(artifact ")
    assert parse_manifest(compact) == none
    assert parse_manifest_block([compact.rstrip("\n"), "0000000000000000"]) == (
        none,
        1,
    )


def test_manifest_assertion_ast_and_nested_values_round_trip() -> None:
    signed = assertion("R6", "<=", -5, "signed", 68)
    aliased = assertion("x8", "==", 42, "bits", 69)
    aliased["display_target"] = "fp"
    memory = assertion("MEM32[0]", "==", 7, "bits", 70)
    value = manifest(
        assertions=[signed, aliased, memory],
        provenance={
            "compiler": {"name": "clang", "flags": ["-O0"], "lto": False},
            "empty": [],
            "escaped": 'quote " slash \\ newline\n',
        },
    )

    rendered = render_manifest(value)
    assert "(assert (<= (signed R6) -5) (source-line 68))" in rendered
    assert '(assert (= x8 42) (source-line 69) (display-target "fp"))' in rendered
    assert '(assert (= "MEM32[0]" 7) (source-line 70))' in rendered
    assert "(empty (array))" in rendered
    assert "(lto false)" in rendered
    assert 'quote \\" slash \\\\ newline\\n' in rendered
    assert parse_manifest(rendered) == value

    with pytest.raises(ManifestError, match="unsupported control character U\\+0001"):
        render_manifest(manifest(description="control \x01"))


def test_manifest_parser_rejects_duplicate_fields_and_invalid_shape() -> None:
    rendered = render_manifest(manifest())
    schema_line = FORMAT_TAG + '  (schema "verylogic.annotated-image")\n'
    duplicate = rendered.replace(
        schema_line,
        schema_line + FORMAT_TAG + '  (schema "other")\n',
    )
    with pytest.raises(ManifestError, match="duplicate field 'schema'"):
        parse_manifest(duplicate, context="image.hex:1")

    version_line = FORMAT_TAG + "  (version 1)\n"
    unknown = rendered.replace(
        version_line,
        version_line + FORMAT_TAG + "  (mystery 7)\n",
    )
    with pytest.raises(ManifestError, match="unknown field.*mystery"):
        parse_manifest(unknown)

    metadata_line = FORMAT_TAG + "  (isa-metadata (object (word-bits 16)))\n"
    duplicate_object = rendered.replace(
        metadata_line,
        FORMAT_TAG
        + "  (isa-metadata\n"
        + FORMAT_TAG
        + "    (object\n"
        + FORMAT_TAG
        + "      (word-bits 16)\n"
        + FORMAT_TAG
        + "      (word-bits 32)\n"
        + FORMAT_TAG
        + "    )\n"
        + FORMAT_TAG
        + "  )\n",
    )
    with pytest.raises(ManifestError, match="duplicate field 'word_bits'"):
        parse_manifest(duplicate_object)

    completion_line = FORMAT_TAG + "  (completion lowered-self-loop word 7)\n"
    explicit_empty_provenance = rendered.replace(
        completion_line,
        FORMAT_TAG + "  (provenance (object))\n" + completion_line,
    )
    with pytest.raises(ManifestError, match="formatting does not match"):
        parse_manifest(explicit_empty_provenance)

    noncanonical = rendered.replace("(version 1)", "(version  1)")
    with pytest.raises(ManifestError, match="formatting does not match"):
        parse_manifest(noncanonical)

    for malformed in (
        FORMAT_TAG + "(artifact",
        FORMAT_TAG + '(artifact (schema "unterminated))',
    ):
        with pytest.raises(ManifestError, match="invalid S-expression"):
            parse_manifest(malformed)

    value = manifest().model_dump(mode="python", by_alias=True)
    value["extra"] = True
    with pytest.raises(ManifestError, match="Extra inputs are not permitted"):
        validate_manifest(value)

    value = manifest().model_dump(mode="python", by_alias=True)
    value["version"] = True
    with pytest.raises(ManifestError, match="manifest.version"):
        validate_manifest(value)

    value = manifest().model_dump(mode="python", by_alias=True)
    value["runtime"] = {"max_steps": {"value": 0, "origin": "source"}}
    with pytest.raises(ManifestError, match="greater than 0"):
        validate_manifest(value)

    with pytest.raises(ManifestError, match="normalized safe relative POSIX path"):
        manifest(source={"kind": "asm", "path": "../outside.asm"})


def test_manifest_assertions_are_strict_without_isa_range_validation() -> None:
    ordered = assertion("ANY_ISA_TARGET[999999]", "<", -2, "signed", 12)
    value = manifest(assertions=[ordered])
    assert (
        assertion_source(value.assertions[0]) == "signed(ANY_ISA_TARGET[999999]) < -2"
    )

    aliased = assertion("x10", "==", 42)
    aliased["display_target"] = "a0"
    value = manifest(assertions=[aliased])
    assert assertion_source(value.assertions[0]) == "a0 == 42"

    invalid = assertion()
    invalid["extra"] = "not public"
    with pytest.raises(ManifestError, match="Extra inputs are not permitted"):
        manifest(assertions=[invalid])

    wrapped_equality = assertion("R0", "==", 1, "signed")
    with pytest.raises(ManifestError, match="equality assertions cannot use"):
        manifest(assertions=[wrapped_equality])


def test_summary_and_full_human_preambles_are_reusable() -> None:
    value = manifest()
    summary = render_preamble(value, "summary")
    full = render_preamble(value, "full", prefix="# ")
    assert "// Annotated image: Add two values\n" in summary
    assert "// Runtime: max_steps=100 (source)\n" in summary
    assert "Assertion line" not in summary
    assert "# Assertion line 4: R0 == 7\n" in full
    assert render_preamble(value, "none") == ""


def test_publish_prechecks_every_staged_file_before_touching_destinations(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "published.txt"
    destination.write_text("old\n", encoding="utf-8")
    with pytest.raises(OSError, match="staged artifact does not exist"):
        publish.publish_artifact_closure([(tmp_path / "missing.txt", destination)])
    assert destination.read_text(encoding="utf-8") == "old\n"


def test_shared_removal_handles_files_and_trees(tmp_path: Path) -> None:
    generated = tmp_path / "generated.txt"
    generated.write_text("generated\n", encoding="utf-8")
    directory = tmp_path / "build"
    directory.mkdir()
    (directory / "artifact").write_text("artifact\n", encoding="utf-8")

    publish.remove_file(generated)
    publish.remove_tree(directory)

    assert not generated.exists()
    assert not directory.exists()
    publish.remove_file(generated)
    publish.remove_tree(directory)


def test_publish_artifact_closure_rolls_back_if_install_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged_first = tmp_path / "first.staged"
    staged_second = tmp_path / "second.staged"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    staged_first.write_text("new first\n", encoding="utf-8")
    staged_second.write_text("new second\n", encoding="utf-8")
    first.write_text("old first\n", encoding="utf-8")
    second.write_text("old second\n", encoding="utf-8")
    real_replace = publish.os.replace
    calls = 0

    def flaky_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("second install failed")
        real_replace(source, destination)

    monkeypatch.setattr(publish.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="second install failed"):
        publish.publish_artifact_closure(
            [(staged_first, first), (staged_second, second)]
        )
    assert first.read_text(encoding="utf-8") == "old first\n"
    assert second.read_text(encoding="utf-8") == "old second\n"


def test_keyboard_interrupt_rolls_back_complete_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged_first = tmp_path / "first.staged"
    staged_second = tmp_path / "second.staged"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    staged_first.write_text("new first\n", encoding="utf-8")
    staged_second.write_text("new second\n", encoding="utf-8")
    first.write_text("old first\n", encoding="utf-8")
    second.write_text("old second\n", encoding="utf-8")
    real_replace = publish.replace_path

    def interrupt_second_install(source: Path, destination: Path) -> None:
        if source == staged_second:
            raise KeyboardInterrupt
        real_replace(source, destination)

    monkeypatch.setattr(publish, "replace_path", interrupt_second_install)
    with pytest.raises(KeyboardInterrupt):
        publish.publish_artifact_closure(
            [(staged_first, first), (staged_second, second)]
        )

    assert first.read_text(encoding="utf-8") == "old first\n"
    assert second.read_text(encoding="utf-8") == "old second\n"
    assert not list(tmp_path.glob(".*.backup.*"))


def test_incomplete_rollback_preserves_recovery_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged_first = tmp_path / "first.staged"
    staged_second = tmp_path / "second.staged"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    staged_first.write_text("new first\n", encoding="utf-8")
    staged_second.write_text("new second\n", encoding="utf-8")
    first.write_text("old first\n", encoding="utf-8")
    second.write_text("old second\n", encoding="utf-8")
    real_replace = publish.replace_path
    real_remove = publish.remove_file

    def flaky_replace(source: Path, destination: Path) -> None:
        if source == staged_second:
            raise OSError("second install failed")
        if ".backup." in source.name and destination == first:
            raise PermissionError("restore blocked")
        real_replace(source, destination)

    def flaky_remove(path: Path) -> None:
        if path == first:
            raise PermissionError("new destination locked")
        real_remove(path)

    monkeypatch.setattr(publish, "replace_path", flaky_replace)
    monkeypatch.setattr(publish, "remove_file", flaky_remove)
    with pytest.raises(RuntimeError, match="rollback was incomplete"):
        publish.publish_artifact_closure(
            [(staged_first, first), (staged_second, second)]
        )

    backups = list(tmp_path.glob(".first.txt.backup.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old first\n"
    assert second.read_text(encoding="utf-8") == "old second\n"


def test_host_c_compiles_generated_c_without_sail_frontend_or_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    sail = tmp_path / "sail-root/bin/sail"
    sail_lib = tmp_path / "sail-root/share/sail/lib"
    sail_lib.mkdir(parents=True)
    generated_c = tmp_path / "program.c"
    executable = tmp_path / "program"
    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> object:
        calls.append((args, cwd))
        return object()

    monkeypatch.setattr(host_c, "run_checked", fake_run)
    monkeypatch.setattr(host_c, "host_c_compiler", lambda: "test-gcc")
    if os.name != "nt":
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
    else:
        monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "conda"))

    host_c.compile_sail_generated_c(sail, generated_c, executable, workspace)
    assert len(calls) == 1
    args, cwd = calls[0]
    assert args[0] == "test-gcc"
    assert str(generated_c) in args
    assert str(executable) in args
    assert str(workspace / "support/sail_windows_compat.c") in args
    assert [str(sail_lib / f"{name}.c") for name in host_c.SAIL_RUNTIME_SOURCES] == [
        item for item in args if item.startswith(str(sail_lib)) and item.endswith(".c")
    ]
    assert str(sail) not in args
    assert cwd == workspace
