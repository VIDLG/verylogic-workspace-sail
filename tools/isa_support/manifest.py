from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from .cli import CommentLevel
from .directives import AssertionDirective, DirectiveSyntaxError, parse_directive
from .sexpr import SExpression, SExpressionError, Symbol, parse_one

FORMAT_TAG = "//% "
SCHEMA = "verylogic.annotated-image"
VERSION = 1
SYMBOL_RE = re.compile(r"[A-Za-z_.$:+*/<>=!?-][A-Za-z0-9_.$:+*/<>=!?/-]*")
FIELD_RE = re.compile(r"[a-z][a-z0-9-]*")
OPERATOR_TO_SYMBOL = {"==": "=", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}
SYMBOL_TO_OPERATOR = {value: key for key, value in OPERATOR_TO_SYMBOL.items()}

SettingOrigin = Literal["cli", "source", "default"]
AssertionOperator = Literal["==", "!=", "<", "<=", ">", ">="]
AssertionMode = Literal["bits", "signed", "unsigned"]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeStrictInt = Annotated[int, Field(strict=True, ge=0)]

ValueT = TypeVar("ValueT")
SourceKindT = TypeVar("SourceKindT")
SourceT = TypeVar("SourceT")
AssertionT = TypeVar("AssertionT")
ProvenanceT = TypeVar("ProvenanceT")
CompletionT = TypeVar("CompletionT")
IsaMetadataT = TypeVar("IsaMetadataT")
ModelT = TypeVar("ModelT", bound="ManifestModel")


class ManifestError(ValueError):
    pass


class ManifestModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )


class ResolvedValue(ManifestModel, Generic[ValueT]):
    value: ValueT
    origin: SettingOrigin


class SourceIdentity(ManifestModel, Generic[SourceKindT]):
    kind: SourceKindT
    path: NonEmptyString

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _normalized_source_path(value)


class ManifestRuntime(ManifestModel):
    max_steps: ResolvedValue[PositiveStrictInt]


class ManifestCompletion(ManifestModel):
    kind: NonEmptyString
    address_unit: NonEmptyString
    addresses: tuple[NonNegativeStrictInt, ...] = Field(strict=False)


class ManifestAssertion(ManifestModel):
    target: NonEmptyString
    operator: AssertionOperator
    value: Annotated[int, Field(strict=True)]
    mode: AssertionMode
    line: PositiveStrictInt
    display_target: NonEmptyString

    @model_validator(mode="after")
    def validate_public_spelling(self) -> ManifestAssertion:
        try:
            parsed = parse_directive(
                f".assert {self.display_target} {self.operator} {self.value}",
                self.line,
            )
        except DirectiveSyntaxError as error:
            raise ValueError(str(error)) from error
        if not isinstance(parsed, AssertionDirective) or parsed.mode != self.mode:
            raise ValueError(
                "display_target, operator, and mode do not form a valid public assertion"
            )
        return self


class ArtifactManifestEnvelope(
    ManifestModel,
    Generic[SourceT, AssertionT, ProvenanceT, CompletionT, IsaMetadataT],
):
    schema_: Literal["verylogic.annotated-image"] = Field(
        default=SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    version: Annotated[int, Field(strict=True, ge=1, le=1)] = VERSION
    isa: NonEmptyString
    profile: NonEmptyString
    source: SourceT
    description: NonEmptyString | None
    comments: CommentLevel
    runtime: ManifestRuntime
    assertions: tuple[AssertionT, ...] = Field(strict=False)
    provenance: ProvenanceT
    completion: CompletionT
    isa_metadata: IsaMetadataT


class ArtifactManifest(
    ArtifactManifestEnvelope[
        SourceIdentity[NonEmptyString],
        ManifestAssertion,
        dict[str, Any],
        ManifestCompletion,
        dict[str, Any],
    ]
):
    pass


def _normalized_source_path(value: str) -> str:
    if value == "<memory>":
        return value
    parsed_path = PurePosixPath(value)
    if (
        parsed_path.is_absolute()
        or parsed_path.as_posix() != value
        or any(part in {"", ".", ".."} or ":" in part for part in parsed_path.parts)
    ):
        raise ValueError("expected a normalized safe relative POSIX path")
    return value


def _location(parts: tuple[str | int, ...]) -> str:
    result = ""
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += ("." if result else "") + part
    return result


def validation_error(error: ValidationError, *, context: str) -> ManifestError:
    messages = []
    for item in error.errors(include_url=False):
        location = _location(item["loc"])
        prefix = f"{context}.{location}" if location else context
        messages.append(f"{prefix}: {item['msg']}")
    return ManifestError("; ".join(messages))


def validate_model(model: type[ModelT], value: object, *, context: str) -> ModelT:
    if isinstance(value, model):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python", by_alias=True)
    try:
        return model.model_validate(value)
    except ValidationError as error:
        raise validation_error(error, context=context) from error


def validate_source_path(value: object, *, context: str = "source.path") -> str:
    try:
        return (
            SourceIdentity[str].model_validate({"kind": "source", "path": value}).path
        )
    except ValidationError as error:
        relevant = [
            item for item in error.errors(include_url=False) if item["loc"] == ("path",)
        ]
        if not relevant:
            raise validation_error(error, context=context) from error
        raise ManifestError(f"{context}: {relevant[0]['msg']}") from error


def resolve_setting(
    cli: ValueT | None,
    source: ValueT | None,
    default: ValueT,
) -> ResolvedValue[ValueT]:
    if cli is not None:
        return ResolvedValue[ValueT](value=cli, origin="cli")
    if source is not None:
        return ResolvedValue[ValueT](value=source, origin="source")
    return ResolvedValue[ValueT](value=default, origin="default")


def validate_manifest(value: object, *, context: str = "manifest") -> ArtifactManifest:
    return validate_model(ArtifactManifest, value, context=context)


def create_manifest(
    *,
    isa: str,
    profile: str,
    source: SourceIdentity[str] | dict[str, Any],
    description: str | None,
    comments: CommentLevel,
    runtime: ManifestRuntime | dict[str, Any],
    assertions: list[ManifestAssertion | dict[str, Any]],
    provenance: dict[str, Any],
    completion: ManifestCompletion | dict[str, Any],
    isa_metadata: dict[str, Any],
) -> ArtifactManifest:
    return validate_manifest(
        {
            "isa": isa,
            "profile": profile,
            "source": source,
            "description": description,
            "comments": comments,
            "runtime": runtime,
            "assertions": assertions,
            "provenance": provenance,
            "completion": completion,
            "isa_metadata": isa_metadata,
        }
    )


def _symbol(value: str, *, context: str) -> Symbol:
    if SYMBOL_RE.fullmatch(value) is None:
        raise ManifestError(f"{context}: {value!r} is not a canonical symbol")
    return Symbol(value)


def _identifier(value: str) -> Symbol | str:
    if SYMBOL_RE.fullmatch(value) is not None:
        return Symbol(value)
    return value


def _field_symbol(value: str, *, context: str) -> Symbol:
    field = value.replace("_", "-")
    if FIELD_RE.fullmatch(field) is None:
        raise ManifestError(f"{context}: {value!r} is not a canonical field name")
    return Symbol(field)


def _encode_generic(value: object, *, context: str) -> SExpression:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python", by_alias=True)
    if value is None:
        return Symbol("none")
    if isinstance(value, bool):
        return Symbol("true" if value else "false")
    if isinstance(value, int | str):
        return value
    if isinstance(value, dict):
        fields: list[SExpression] = [Symbol("object")]
        for key in sorted(value):
            if not isinstance(key, str):
                raise ManifestError(f"{context}: object keys must be strings")
            fields.append(
                [
                    _field_symbol(key, context=context),
                    _encode_generic(value[key], context=f"{context}.{key}"),
                ]
            )
        return fields
    if isinstance(value, list | tuple | set | frozenset):
        items = sorted(value) if isinstance(value, set | frozenset) else value
        return [
            Symbol("array"),
            *(
                _encode_generic(item, context=f"{context}[{index}]")
                for index, item in enumerate(items)
            ),
        ]
    raise ManifestError(f"{context}: unsupported value type {type(value).__name__}")


def _assertion_form(assertion: ManifestAssertion) -> list[SExpression]:
    target: SExpression = _identifier(assertion.target)
    if assertion.mode != "bits":
        target = [Symbol(assertion.mode), target]
    expression: SExpression = [
        Symbol(OPERATOR_TO_SYMBOL[assertion.operator]),
        target,
        assertion.value,
    ]
    form: list[SExpression] = [
        Symbol("assert"),
        expression,
        [Symbol("source-line"), assertion.line],
    ]
    default_display = (
        assertion.target
        if assertion.mode == "bits"
        else f"{assertion.mode}({assertion.target})"
    )
    if assertion.display_target != default_display:
        form.append([Symbol("display-target"), assertion.display_target])
    return form


def _manifest_form(
    manifest: ArtifactManifestEnvelope[Any, Any, Any, Any, Any],
) -> list[SExpression]:
    completion = manifest.completion.model_dump(mode="python")
    form: list[SExpression] = [
        Symbol("artifact"),
        [Symbol("schema"), manifest.schema_],
        [Symbol("version"), manifest.version],
        [Symbol("isa"), _symbol(manifest.isa, context="manifest.isa")],
        [Symbol("profile"), _symbol(manifest.profile, context="manifest.profile")],
        [
            Symbol("source"),
            _symbol(manifest.source.kind, context="manifest.source.kind"),
            manifest.source.path,
        ],
    ]
    if manifest.description is not None:
        form.append([Symbol("description"), manifest.description])
    form.extend(
        [
            [Symbol("comments"), Symbol(manifest.comments)],
            [
                Symbol("runtime"),
                [
                    Symbol("max-steps"),
                    manifest.runtime.max_steps.value,
                    Symbol(manifest.runtime.max_steps.origin),
                ],
            ],
            [
                Symbol("assertions"),
                *(_assertion_form(assertion) for assertion in manifest.assertions),
            ],
        ]
    )
    provenance = _encode_generic(manifest.provenance, context="manifest.provenance")
    if provenance != [Symbol("object")]:
        form.append([Symbol("provenance"), provenance])
    form.extend(
        [
            [
                Symbol("completion"),
                _symbol(
                    completion["kind"].replace("_", "-"),
                    context="manifest.completion.kind",
                ),
                _symbol(
                    completion["address_unit"],
                    context="manifest.completion.address_unit",
                ),
                *completion["addresses"],
            ],
            [
                Symbol("isa-metadata"),
                _encode_generic(manifest.isa_metadata, context="manifest.isa_metadata"),
            ],
        ]
    )
    return form


def _quote_string(value: str) -> str:
    escapes = {
        '"': '\\"',
        "\\": "\\\\",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
        "\b": "\\b",
        "\f": "\\f",
    }
    parts = ['"']
    for character in value:
        if character in escapes:
            parts.append(escapes[character])
        elif ord(character) < 0x20 or ord(character) == 0x7F:
            raise ManifestError(
                f"manifest string contains unsupported control character U+{ord(character):04X}"
            )
        else:
            parts.append(character)
    parts.append('"')
    return "".join(parts)


def _render_atom(value: int | str | Symbol) -> str:
    if isinstance(value, Symbol):
        return value.value
    if isinstance(value, int):
        return str(value)
    return _quote_string(value)


def _compact(value: SExpression) -> str:
    if isinstance(value, list):
        return "(" + " ".join(_compact(item) for item in value) + ")"
    return _render_atom(value)


def _pretty(value: SExpression, indent: int = 0, width: int = 100) -> list[str]:
    compact = _compact(value)
    prefix = " " * indent
    if not isinstance(value, list) or len(prefix) + len(compact) <= width:
        return [prefix + compact]
    if not value:
        return [prefix + "()"]
    lines = [prefix + "(" + _compact(value[0])]
    for item in value[1:]:
        lines.extend(_pretty(item, indent + 2, width))
    lines.append(prefix + ")")
    return lines


def render_manifest(
    manifest: ArtifactManifestEnvelope[Any, Any, Any, Any, Any],
) -> str:
    form = _manifest_form(manifest)
    payload = [_compact(form)] if manifest.comments == "none" else _pretty(form)
    return "".join(f"{FORMAT_TAG}{line}\n" for line in payload)


def _expect_list(value: SExpression, *, context: str) -> list[SExpression]:
    if not isinstance(value, list):
        raise ManifestError(f"{context}: expected a list")
    return value


def _expect_symbol(value: SExpression, *, context: str) -> str:
    if not isinstance(value, Symbol):
        raise ManifestError(f"{context}: expected a symbol")
    return value.value


def _expect_string(value: SExpression, *, context: str) -> str:
    if not isinstance(value, str) or isinstance(value, Symbol):
        raise ManifestError(f"{context}: expected a string")
    return value


def _expect_int(value: SExpression, *, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ManifestError(f"{context}: expected an integer")
    return value


def _expect_form(
    value: SExpression,
    name: str,
    *,
    context: str,
    size: int | None = None,
) -> list[SExpression]:
    form = _expect_list(value, context=context)
    if not form or _expect_symbol(form[0], context=f"{context}[0]") != name:
        raise ManifestError(f"{context}: expected ({name} ...) form")
    if size is not None and len(form) != size:
        raise ManifestError(f"{context}: ({name} ...) expects {size - 1} value(s)")
    return form


def _decode_generic(value: SExpression, *, context: str) -> object:
    if isinstance(value, int | str) and not isinstance(value, Symbol | bool):
        return value
    if isinstance(value, Symbol):
        if value.value == "none":
            return None
        if value.value == "true":
            return True
        if value.value == "false":
            return False
        raise ManifestError(f"{context}: unexpected generic symbol {value.value!r}")
    form = _expect_list(value, context=context)
    if not form:
        raise ManifestError(
            f"{context}: generic containers require object or array tag"
        )
    tag = _expect_symbol(form[0], context=f"{context}[0]")
    if tag == "array":
        return [
            _decode_generic(item, context=f"{context}[{index}]")
            for index, item in enumerate(form[1:])
        ]
    if tag != "object":
        raise ManifestError(f"{context}: expected object or array, got {tag!r}")
    result: dict[str, object] = {}
    for index, item in enumerate(form[1:]):
        field = _expect_list(item, context=f"{context}[{index}]")
        if len(field) != 2:
            raise ManifestError(f"{context}[{index}]: object field expects one value")
        key = _expect_symbol(field[0], context=f"{context}[{index}][0]").replace(
            "-", "_"
        )
        if key in result:
            raise ManifestError(f"{context}: duplicate field {key!r}")
        result[key] = _decode_generic(field[1], context=f"{context}.{key}")
    return result


def _decode_assertion(value: SExpression, *, context: str) -> dict[str, object]:
    form = _expect_form(value, "assert", context=context)
    if len(form) not in (3, 4):
        raise ManifestError(
            f"{context}: assert expects expression, source-line, and optional display-target"
        )
    expression = _expect_list(form[1], context=f"{context}.expression")
    if len(expression) != 3:
        raise ManifestError(f"{context}.expression: expected binary comparison")
    operator_symbol = _expect_symbol(expression[0], context=f"{context}.operator")
    try:
        operator = SYMBOL_TO_OPERATOR[operator_symbol]
    except KeyError as error:
        raise ManifestError(
            f"{context}.operator: unsupported comparison {operator_symbol!r}"
        ) from error

    target_node = expression[1]
    mode = "bits"
    if isinstance(target_node, list):
        wrapper = _expect_list(target_node, context=f"{context}.target")
        if len(wrapper) != 2:
            raise ManifestError(f"{context}.target: wrapper expects one target")
        mode = _expect_symbol(wrapper[0], context=f"{context}.mode")
        if mode not in {"signed", "unsigned"}:
            raise ManifestError(f"{context}.mode: unsupported wrapper {mode!r}")
        target_node = wrapper[1]
    if isinstance(target_node, Symbol):
        target = target_node.value
    else:
        target = _expect_string(target_node, context=f"{context}.target")
    value_number = _expect_int(expression[2], context=f"{context}.value")

    line_form = _expect_form(
        form[2], "source-line", context=f"{context}.source-line", size=2
    )
    line = _expect_int(line_form[1], context=f"{context}.source-line")
    display_target = target if mode == "bits" else f"{mode}({target})"
    if len(form) == 4:
        display_form = _expect_form(
            form[3],
            "display-target",
            context=f"{context}.display-target",
            size=2,
        )
        display_target = _expect_string(
            display_form[1], context=f"{context}.display-target"
        )
    return {
        "target": target,
        "operator": operator,
        "value": value_number,
        "mode": mode,
        "line": line,
        "display_target": display_target,
    }


def _manifest_values(root: SExpression, *, context: str) -> dict[str, object]:
    artifact = _expect_form(root, "artifact", context=context)
    fields: dict[str, list[SExpression]] = {}
    for index, item in enumerate(artifact[1:]):
        field = _expect_list(item, context=f"{context}[{index}]")
        if not field:
            raise ManifestError(f"{context}[{index}]: empty artifact field")
        name = _expect_symbol(field[0], context=f"{context}[{index}][0]")
        if name in fields:
            raise ManifestError(f"{context}: duplicate field {name!r}")
        fields[name] = field

    required = {
        "schema",
        "version",
        "isa",
        "profile",
        "source",
        "comments",
        "runtime",
        "assertions",
        "completion",
        "isa-metadata",
    }
    allowed = required | {"description", "provenance"}
    missing = sorted(required - fields.keys())
    extra = sorted(fields.keys() - allowed)
    if missing:
        raise ManifestError(f"{context}: missing field(s): {', '.join(missing)}")
    if extra:
        raise ManifestError(f"{context}: unknown field(s): {', '.join(extra)}")

    schema = _expect_form(
        fields["schema"], "schema", context=f"{context}.schema", size=2
    )
    version = _expect_form(
        fields["version"], "version", context=f"{context}.version", size=2
    )
    isa = _expect_form(fields["isa"], "isa", context=f"{context}.isa", size=2)
    profile = _expect_form(
        fields["profile"], "profile", context=f"{context}.profile", size=2
    )
    source = _expect_form(
        fields["source"], "source", context=f"{context}.source", size=3
    )
    comments = _expect_form(
        fields["comments"], "comments", context=f"{context}.comments", size=2
    )
    runtime = _expect_form(
        fields["runtime"], "runtime", context=f"{context}.runtime", size=2
    )
    max_steps = _expect_form(
        runtime[1],
        "max-steps",
        context=f"{context}.runtime.max-steps",
        size=3,
    )
    assertions = _expect_form(
        fields["assertions"], "assertions", context=f"{context}.assertions"
    )
    completion = _expect_form(
        fields["completion"], "completion", context=f"{context}.completion"
    )
    if len(completion) < 3:
        raise ManifestError(f"{context}.completion: expected kind and address unit")
    isa_metadata = _expect_form(
        fields["isa-metadata"],
        "isa-metadata",
        context=f"{context}.isa-metadata",
        size=2,
    )

    description: str | None = None
    if "description" in fields:
        description_form = _expect_form(
            fields["description"],
            "description",
            context=f"{context}.description",
            size=2,
        )
        description = _expect_string(
            description_form[1], context=f"{context}.description"
        )

    provenance: object = {}
    if "provenance" in fields:
        provenance_form = _expect_form(
            fields["provenance"],
            "provenance",
            context=f"{context}.provenance",
            size=2,
        )
        provenance = _decode_generic(
            provenance_form[1],
            context=f"{context}.provenance",
        )

    return {
        "schema": _expect_string(schema[1], context=f"{context}.schema"),
        "version": _expect_int(version[1], context=f"{context}.version"),
        "isa": _expect_symbol(isa[1], context=f"{context}.isa"),
        "profile": _expect_symbol(profile[1], context=f"{context}.profile"),
        "source": {
            "kind": _expect_symbol(source[1], context=f"{context}.source.kind"),
            "path": _expect_string(source[2], context=f"{context}.source.path"),
        },
        "description": description,
        "comments": _expect_symbol(comments[1], context=f"{context}.comments"),
        "runtime": {
            "max_steps": {
                "value": _expect_int(
                    max_steps[1], context=f"{context}.runtime.max_steps.value"
                ),
                "origin": _expect_symbol(
                    max_steps[2], context=f"{context}.runtime.max_steps.origin"
                ),
            }
        },
        "assertions": [
            _decode_assertion(item, context=f"{context}.assertions[{index}]")
            for index, item in enumerate(assertions[1:])
        ],
        "provenance": provenance,
        "completion": {
            "kind": _expect_symbol(
                completion[1], context=f"{context}.completion.kind"
            ).replace("-", "_"),
            "address_unit": _expect_symbol(
                completion[2], context=f"{context}.completion.address-unit"
            ),
            "addresses": [
                _expect_int(item, context=f"{context}.completion.addresses[{index}]")
                for index, item in enumerate(completion[3:])
            ],
        },
        "isa_metadata": _decode_generic(
            isa_metadata[1], context=f"{context}.isa-metadata"
        ),
    }


def parse_manifest(text: str, *, context: str = "manifest") -> ArtifactManifest:
    lines = text.splitlines()
    if not lines or any(not line.startswith(FORMAT_TAG) for line in lines):
        raise ManifestError(
            f"{context}: every manifest line must begin with {FORMAT_TAG.strip()}"
        )
    payload = "\n".join(line.removeprefix(FORMAT_TAG) for line in lines)
    try:
        root = parse_one(payload, context=context)
    except SExpressionError as error:
        raise ManifestError(str(error)) from error
    manifest = validate_manifest(
        _manifest_values(root, context=context), context=context
    )
    if lines != render_manifest(manifest).splitlines():
        raise ManifestError(
            f"{context}: manifest formatting does not match comments={manifest.comments}"
        )
    return manifest


def parse_manifest_block(
    lines: Sequence[str],
    *,
    context: str = "manifest",
) -> tuple[ArtifactManifest, int]:
    count = 0
    while count < len(lines) and lines[count].startswith(FORMAT_TAG):
        count += 1
    if count == 0:
        raise ManifestError(
            f"{context}: artifact must begin with a {FORMAT_TAG.strip()} manifest"
        )
    block = list(lines[:count])
    manifest = parse_manifest("\n".join(block), context=context)
    return manifest, count


def assertion_source(assertion: ManifestAssertion) -> str:
    return f"{assertion.display_target} {assertion.operator} {assertion.value}"


def preamble_lines(
    manifest: ArtifactManifestEnvelope[Any, Any, Any, Any, Any],
    comments: CommentLevel | None = None,
) -> tuple[str, ...]:
    level = manifest.comments if comments is None else comments
    if level == "none":
        return ()

    description = manifest.description or manifest.source.path
    lines = [
        f"Annotated image: {description}",
        f"ISA/profile: {manifest.isa}/{manifest.profile}",
        f"Source: {manifest.source.kind} {manifest.source.path}",
        (
            "Runtime: max_steps="
            f"{manifest.runtime.max_steps.value} ({manifest.runtime.max_steps.origin})"
        ),
        f"Assertions: {len(manifest.assertions)}",
    ]
    if level == "full":
        lines.extend(
            f"Assertion line {item.line}: {assertion_source(item)}"
            for item in manifest.assertions
        )
    return tuple(lines)


def render_preamble(
    manifest: ArtifactManifestEnvelope[Any, Any, Any, Any, Any],
    comments: CommentLevel | None = None,
    *,
    prefix: str = "// ",
) -> str:
    return "".join(f"{prefix}{line}\n" for line in preamble_lines(manifest, comments))
