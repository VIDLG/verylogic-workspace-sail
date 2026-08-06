from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from isa.hack.tools.assembler import (
    AssemblyError,
    AssemblyMetadata,
    AssemblyResult,
    Assertion,
    MachineWord,
    canonical_assertion_target,
    parse_expected_value,
)
from isa.hack.tools.profiles import Profile, get_profile
from tools.isa_support.cli import validate_comment_level
from tools.isa_support.manifest import (
    FORMAT_TAG,
    ArtifactManifestEnvelope,
    ManifestAssertion,
    ManifestModel,
    SourceIdentity,
    parse_manifest_block,
    render_manifest,
    render_preamble,
    validate_model,
    validate_source_path,
)
from tools.isa_support.publish import atomic_write_text

HackAddress = Annotated[int, Field(strict=True, ge=0, lt=32768)]
PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]


class HackProvenance(ManifestModel):
    pass


class HackManifestAssertion(ManifestAssertion):
    @model_validator(mode="after")
    def validate_hack_semantics(self) -> HackManifestAssertion:
        try:
            canonical_target = canonical_assertion_target(self.target, self.line)
        except AssemblyError as error:
            raise ValueError(error.message) from error
        if canonical_target != self.target:
            raise ValueError(
                f"target must use canonical Hack spelling {canonical_target!r}"
            )

        displayed_target = self.display_target
        if self.mode != "bits":
            prefix = f"{self.mode}("
            if not displayed_target.startswith(prefix) or not displayed_target.endswith(
                ")"
            ):
                raise ValueError("display_target does not match assertion mode")
            displayed_target = displayed_target[len(prefix) : -1]
        try:
            displayed_canonical = canonical_assertion_target(
                displayed_target, self.line
            )
        except AssemblyError as error:
            raise ValueError(error.message) from error
        if displayed_canonical != self.target:
            raise ValueError("display_target does not name canonical target")
        return self


class HackCompletion(ManifestModel):
    kind: Literal["lowered_self_loop"]
    address_unit: Literal["word"]
    addresses: tuple[HackAddress, ...] = Field(strict=False)

    @model_validator(mode="after")
    def validate_addresses(self) -> HackCompletion:
        if len(self.addresses) != len(set(self.addresses)):
            raise ValueError("addresses must not contain duplicates")
        if self.addresses != tuple(sorted(self.addresses)):
            raise ValueError("addresses must be sorted")
        return self


class HackIsaMetadata(ManifestModel):
    word_bits: PositiveStrictInt
    a_immediate_bits: PositiveStrictInt
    address_bits: PositiveStrictInt
    pc_bits: PositiveStrictInt
    rom_words: PositiveStrictInt
    ram_words: PositiveStrictInt
    sail_project: str


class HackManifest(
    ArtifactManifestEnvelope[
        SourceIdentity[Literal["asm"]],
        HackManifestAssertion,
        HackProvenance,
        HackCompletion,
        HackIsaMetadata,
    ]
):
    @model_validator(mode="after")
    def validate_identity(self) -> HackManifest:
        if self.isa != "hack":
            raise ValueError("ISA must be hack")
        return self


@dataclass(frozen=True)
class LoadedHack:
    profile: Profile
    words: list[int]
    metadata: AssemblyMetadata
    word_comments: tuple[str | None, ...]
    manifest: HackManifest


def _assertion_manifest(assertion: Assertion) -> dict[str, object]:
    return {
        "target": assertion.target,
        "operator": assertion.operator,
        "value": assertion.value,
        "mode": assertion.mode,
        "line": assertion.line,
        "display_target": assertion.display_target,
    }


def _expected_isa_metadata(profile: Profile) -> dict[str, object]:
    return {
        "word_bits": profile.word_bits,
        "a_immediate_bits": profile.a_immediate_bits,
        "address_bits": profile.address_bits,
        "pc_bits": profile.pc_bits,
        "rom_words": profile.rom_words,
        "ram_words": profile.ram_words,
        "sail_project": profile.sail_project.name,
    }


def create_hack_manifest(
    profile: Profile, metadata: AssemblyMetadata, comments: str
) -> HackManifest:
    source_path = validate_source_path(metadata.source_path)
    return validate_model(
        HackManifest,
        {
            "isa": "hack",
            "profile": profile.name,
            "source": {"kind": metadata.source_kind, "path": source_path},
            "description": metadata.description,
            "comments": validate_comment_level(comments),
            "runtime": {
                "max_steps": {
                    "value": metadata.max_steps,
                    "origin": metadata.max_steps_origin,
                }
            },
            "assertions": [
                _assertion_manifest(assertion) for assertion in metadata.assertions
            ],
            "provenance": {},
            "completion": {
                "kind": "lowered_self_loop",
                "address_unit": "word",
                "addresses": list(metadata.halt_addresses),
            },
            "isa_metadata": _expected_isa_metadata(profile),
        },
        context="manifest",
    )


def apply_runtime_overrides(
    assembly: AssemblyResult,
    *,
    max_steps: int | None = None,
) -> AssemblyResult:
    if max_steps is not None and max_steps <= 0:
        raise ValueError("--max-steps must be a positive integer")
    metadata = assembly.metadata
    return replace(
        assembly,
        metadata=replace(
            metadata,
            max_steps=metadata.max_steps if max_steps is None else max_steps,
            max_steps_origin=metadata.max_steps_origin if max_steps is None else "cli",
        ),
    )


def _word_line(
    profile: Profile, address: int, record: MachineWord, comments: str
) -> str:
    suffix = ""
    if comments == "summary":
        source, separator, inline_comment = record.source.text.partition("//")
        source = source.strip()
        mapping = f"ROM[{address:04d}] L{record.source.line}"
        if record.expansion is None:
            mapping += f" {source}"
        else:
            expansion = record.expansion
            mapping += (
                f" [{expansion.index}/{expansion.count}] {source}"
                f" => {expansion.instruction}"
            )
        inline_comment = inline_comment.strip()
        if separator and inline_comment:
            mapping += f" // {inline_comment}"
        suffix = f" // {mapping}"
    elif comments == "full":
        mapping = (
            f"ROM[{address:04d}] L{record.source.line}: {record.source.text.strip()}"
        )
        if record.expansion is not None:
            expansion = record.expansion
            mapping += (
                f" [{expansion.index}/{expansion.count}] => {expansion.instruction}"
            )
        suffix = f" // {mapping}"
    return f"{record.value:0{profile.word_bits}b}{suffix}\n"


def write_hack(assembly: AssemblyResult, path: Path, comments: str = "summary") -> None:
    comments = validate_comment_level(comments)
    manifest = create_hack_manifest(assembly.profile, assembly.metadata, comments)
    text = render_manifest(manifest)
    text += render_preamble(manifest, comments)
    text += "".join(
        _word_line(assembly.profile, address, record, comments)
        for address, record in enumerate(assembly.records)
    )
    atomic_write_text(path, text)


def _metadata_from_manifest(manifest: HackManifest) -> AssemblyMetadata:
    assertions = tuple(
        Assertion(
            item.target,
            item.value,
            item.line,
            item.operator,
            item.mode,
            item.display_target,
        )
        for item in manifest.assertions
    )
    return AssemblyMetadata(
        manifest.completion.addresses,
        assertions,
        manifest.runtime.max_steps.value,
        manifest.description,
        manifest.runtime.max_steps.origin,
        manifest.source.kind,
        manifest.source.path,
    )


def _parse_words(
    path: Path,
    lines: list[str],
    *,
    profile: Profile,
    comments: str,
    first_line: int,
) -> tuple[list[int], tuple[str | None, ...]]:
    word_re = re.compile(
        rf"\s*(?P<word>[01]{{{profile.word_bits}}})(?:\s+//\s*(?P<comment>.*?))?\s*"
    )
    words: list[int] = []
    word_comments: list[str | None] = []
    for line_number, line in enumerate(lines, start=first_line):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(FORMAT_TAG):
            raise ValueError(
                f"{path}:{line_number}: manifest is only allowed at the start of the file"
            )
        if stripped.startswith("//"):
            if comments == "none":
                raise ValueError(
                    f"{path}:{line_number}: comments=none artifact contains human comments"
                )
            continue
        match = word_re.fullmatch(line)
        if match is None:
            raise ValueError(
                f"{path}:{line_number}: expected a {profile.word_bits}-bit binary word or comment"
            )
        comment = match.group("comment")
        if comments == "none" and comment is not None:
            raise ValueError(
                f"{path}:{line_number}: comments=none artifact contains word comments"
            )
        words.append(int(match.group("word"), 2))
        word_comments.append(comment)
        if len(words) > profile.rom_words:
            raise ValueError(
                f"{path}:{line_number}: program exceeds the {profile.rom_words}-word Hack ROM"
            )
    return words, tuple(word_comments)


def _validate_completion_words(
    path: Path, profile: Profile, words: list[int], addresses: tuple[int, ...]
) -> None:
    halt_jump = profile.encode_c(int("1110101010000111", 2))
    for address in addresses:
        if address + 1 >= len(words):
            raise ValueError(
                f"{path}: completion address {address} is outside the {len(words)}-word ROM"
            )
        if words[address] != address or words[address + 1] != halt_jump:
            raise ValueError(
                f"{path}: completion address {address} does not point to an "
                "@address; 0;JMP self-loop"
            )


def _validate_manifest_contract(manifest: HackManifest) -> Profile:
    profile = get_profile(manifest.profile)
    actual_metadata = manifest.isa_metadata.model_dump(mode="python")
    if actual_metadata != _expected_isa_metadata(profile):
        raise ValueError(f"manifest ISA metadata does not match profile {profile.name}")
    for assertion in manifest.assertions:
        try:
            normalized = parse_expected_value(
                str(assertion.value),
                assertion.line,
                assertion.target,
                assertion.operator,
                assertion.mode,
                profile,
            )
        except AssemblyError as error:
            raise ValueError(error.message) from error
        if normalized != assertion.value:
            raise ValueError("bit-exact assertion value must be serialized canonically")
    return profile


def load_hack(path: Path, *, expected_profile: str | None = None) -> LoadedHack:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith(FORMAT_TAG):
        raise ValueError(
            f"{path}: Hack artifact must begin with a {FORMAT_TAG.strip()} manifest"
        )

    public_manifest, manifest_lines = parse_manifest_block(lines, context=f"{path}:1")
    manifest = validate_model(
        HackManifest,
        public_manifest.model_dump(mode="python", by_alias=True),
        context="manifest",
    )
    profile = _validate_manifest_contract(manifest)
    if expected_profile is not None and profile.name != expected_profile:
        raise ValueError(
            f"artifact profile {profile.name!r} does not match expected profile "
            f"{expected_profile!r}"
        )
    metadata = _metadata_from_manifest(manifest)
    words, word_comments = _parse_words(
        path,
        lines[manifest_lines:],
        profile=profile,
        comments=manifest.comments,
        first_line=manifest_lines + 1,
    )
    _validate_completion_words(path, profile, words, metadata.halt_addresses)
    return LoadedHack(profile, words, metadata, word_comments, manifest)
