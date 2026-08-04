# Repository agent guidance

## Sail models

Before changing or adding an ISA model, follow [`.design/SAIL_MODELING.md`](.design/SAIL_MODELING.md).

Key rules:

- Use `lower_snake_case` for types, unions, enums, structs, functions, parameters, fields, and ordinary values.
- Use `UpperCamelCase` for constructors, except when the canonical ISA mnemonic spelling such as `ADDI` or `ECALL` is clearer and intentionally preserved.
- Keep architectural register names in their ISA spelling, such as Hack `A/D/PC/RAM` and RISC-V `X/PC`.
- Give instruction words and important fields named bit-vector types when they cross decode, execute, or public API boundaries. Do not create aliases for every one-off slice.
- Use a compact bidirectional `mapping` when an encoding is a clear bijection. Wrap it in an explicit `decode_<isa>` `match` when legality or reserved encodings need to remain visible; use separate decode/encode functions for more complex ISAs.
- Unknown or reserved encodings must produce an explicit illegal/reserved result or a documented non-match. A wildcard must never silently construct a legal instruction.
- Decode before execute. Faulting or illegal paths must not partially commit architectural state.
- Generated drivers load raw program words or bytes into model-owned instruction storage; they must not embed decoded constructors or combine address lookup with decoding. The ISA model owns fetch/decode/execute and a composed step function, while the driver owns completion, watchdogs, assertions, hooks, and output.
- Runtime settings exposed by both source directives and CLI flags use `CLI > source > default`; effective overrides must be serialized into the generated artifact before reload, not passed to driver generation as hidden state.
- Keep generated drivers, direct Sail conformance tests, package references, and English/Chinese documentation synchronized with model API changes.

## Validation

Run the narrow ISA workflow first, then its complete test command when available. For example:

```sh
pixi run just hack check
pixi run just hack test
pixi run just riscv check
pixi run just riscv test
```

Do not edit generated files under an ISA's `.build/` directory.
