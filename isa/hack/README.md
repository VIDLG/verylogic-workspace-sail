# Hack Package Reference

[中文文档](README.zh-CN.md) · [Documentation](../../docs/README.md) · [Project tutorial](../../README.md)

A self-contained Sail package for the nand2tetris Hack CPU. `nand2tetris` is the course name; **Hack** is the CPU and ISA name.

## Contents

- [`docs/hack/ISA.md`](../../docs/hack/ISA.md) — Hack ISA, canonical encodings, execution semantics, and Hack+ lowering rules.
- [`docs/hack/ASSEMBLER.md`](../../docs/hack/ASSEMBLER.md) — parser, lowering, two-pass assembly, and annotated artifact internals.
- [`docs/hack/EXECUTION.md`](../../docs/hack/EXECUTION.md) — generated Sail driver, C backend, workflow, and test architecture.
- `hack.sail` — executable ISA semantics: encoding, ALU, registers, RAM, and control flow. It has no program-specific `main()`.
- `justfile` — package-local command interface, imported as the root `hack` module.
- `tools/assembler.py` — dependency-free, two-pass Hack assembler with a small typed parser, Hack+ pseudoinstructions, source directives, and annotated `.hack` I/O.
- `tools/executor.py` — host-side execution entry point using Sail's C backend.
- `tools/workflow.py` — package catalog, regression, and cleanup orchestration.
- `hooks.sail` — default package-local Sail hook API implementation; empty by default.
- `hooks/trace.sail` — quiet example hook that traces execution start and finish.
- `programs.toml` — package-local program catalog.
- `programs/` — runnable assembly programs whose expected results live beside their code.
- `tests/isa_conformance.sail` — direct Sail checks for every ALU operation, jump truth table, destination mask, and critical state-transition rule.

## Execution pipeline

```text
programs/*.asm
  -> tools/assembler.py
  -> annotated .build/<program>.hack
  -> tools/executor.py reloads that .hack file
  -> generated .driver.sail
  -> Sail C backend
  -> .build/<program>.exe
```

The write/reload step is intentional: the generated Sail driver consumes exactly the words and metadata represented in the `.hack` artifact, rather than retaining hidden state from assembly.

## Platform support

The Sail C-backend workflow uses the project-local pinned Sail 0.20.2 binary: Windows AMD64, Linux x86_64, and Linux aarch64 are supported. It uses the Pixi-managed MinGW compiler on Windows and `gcc` on Linux; the shared compatibility source is harmless on Linux. macOS is unsupported because this Sail release has no official macOS binary asset. Run the repository commands below so the workflow can validate or install `.pixi/sail/`; it does not fall back to a system Sail executable.

Execution stops when `PC` reaches a `HALT` address recorded by the assembler or leaves the loaded ROM. `HALT` still expands to an ordinary two-instruction self-loop, so the machine code remains valid Hack code; its loop address is additionally recorded as metadata. With `HALT`, an optional step limit fails if completion takes too long. Without `HALT`, a step limit plus assertions defines a deliberate bounded state snapshot.

## Sail hooks

By default, `hooks.sail` is compiled with `hack.sail` and the generated driver, so hooks execute in the same Sail/C process and may directly inspect or update `A`, `D`, `PC`, and `RAM`. The default functions are no-ops. Every hook source must define this API:

| Function | Timing |
| --- | --- |
| `hack_hook_before_run()` | Once, before the execution loop. |
| `hack_hook_before_step(step)` | Before each instruction; `step` is zero-based. |
| `hack_hook_after_step(step)` | After each instruction; `step` is one-based completed-count. |
| `hack_hook_after_run(steps)` | After source assertions pass, before the final status output. |

Use hooks for tracing, device models, coverage counters, or additional Sail assertions. Source `.assert` directives remain the program's core regression contract; Python does not evaluate either hooks or assertions.

Use `.hook` to select one package-local replacement for a program:

```asm
.hook hooks/trace.sail
```

The path is a nonempty, safe, package-root-relative POSIX `.sail` path. Backslashes are normalized to `/`; absolute paths and `..` are rejected. A custom `.hook` **replaces** `hooks.sail`; hooks do not compose.

## Source directives

Directives may appear anywhere in a normal `.asm` file and do not emit instructions:

```asm
.hook hooks/trace.sail
.assert R2 == 42
.assert R6 < 0
.assert signed(R6) >= -5
.assert unsigned(R6) > 0x8000
.assert PC <= 32767
.max_steps 10_000
```

Targets are `A`, `D`, `PC`, `R0` through `R15`, and `RAM[0]` through `RAM[32767]`. Integer values use Python syntax (`42`, `0x2A`, `0o52`, `0b101010`, and underscores).

| Syntax | Comparison | RHS range |
| --- | --- | --- |
| `.assert target == value` / `!=` | Exact architectural bits. Negative word literals are normalized to 16 bits, so `-1` means `0xFFFF`. | Word: `-32768..65535`; `PC`: `0..32767` |
| `.assert target < value` / `<=` / `>` / `>=` | Plain word targets default to signed 16-bit. | `-32768..32767` |
| `.assert signed(target) op value` | Explicit signed 16-bit relational comparison. | `-32768..32767` |
| `.assert unsigned(target) op value` | Explicit unsigned 16-bit relational comparison. | `0..65535` |
| `.assert PC op value` | Unsigned 15-bit comparison. `unsigned(PC)` is accepted and canonicalized; `signed(PC)` is rejected. | `0..32767` |

`op` is any of `==`, `!=`, `<`, `<=`, `>`, or `>=`. Wrappers are accepted on word equality assertions too, but equality and inequality remain bit-exact rather than numeric signed/unsigned comparisons.

`.hook <relative .sail path>` is optional and may occur at most once; it emits no machine words. Without it, the program selects `hooks.sail`. The executor resolves the selected source only under `isa/hack` after reloading the generated `.hack` artifact.

`.max_steps <positive integer>` is optional and may occur at most once. The executor's `--max-steps` option overrides it. With a recorded `HALT`, reaching the limit before completion fails. Without `HALT`, reaching the limit is the requested stopping point and assertions are evaluated there. Current bundled programs all terminate via `HALT`, so none needs a source step limit.

The executor prints `ASSERT PASS` only when at least one source assertion exists. Programs without assertions print `RUN COMPLETE`. Pass `--require-assertions` to reject programs that do not declare any assertions.

## Annotated `.hack` files

Every instruction remains one 16-bit binary word on one line. A human-readable inline comment records its ROM address, source line, and original source text; pseudoinstruction expansions also show the expanded Hack instruction:

```text
0000000000010001 // ROM[0000] L4: SET R0, 17 => @17
1110110000010000 // ROM[0001] L4: SET R0, 17 => D=A
```

Structured comment-only records carry execution metadata:

```text
//%hack format {"version":3}
//%hack hook {"path":"hooks/trace.sail"}
//%hack halt {"address":42}
//%hack assert {"line":55,"mode":"signed","operator":">=","target":"R2","value":42}
//%hack max_steps {"value":1000}
```

`load_hack()` ignores blank lines and ordinary comments, strictly validates every machine word and structured metadata record, and returns the words plus metadata. Plain, unannotated `.hack` files remain loadable.

## Hack+ pseudocode

Hack+ expands to ordinary Hack A/C instructions before assembly; it does not change the ISA or Sail semantics. Standard Hack assembly and these forms can be mixed in one `.asm` file.

| Pseudocode | Meaning |
| --- | --- |
| `SET target, value` | Store an immediate value or symbol address in RAM `target`. |
| `INC target` / `DEC target` | Increment or decrement RAM `target`. |
| `GOTO label` | Unconditional branch. |
| `JNZ`, `JGT`, `JEQ`, `JGE`, `JLT`, `JLE target, label` | Compare RAM `target` with zero and conditionally branch. |
| `HALT` | Emit a private self-loop and record its ROM address. |

Hack symbols follow `[A-Za-z_.$:][A-Za-z0-9_.$:]*`. Numeric or malformed labels and malformed A-instruction symbols are rejected instead of being silently allocated as variables.

## Programs

- `isa_conformance.asm` — runs direct Sail-level ALU, jump, destination, A/M-selection, old-`A`, and PC-wrap checks.
- `basic_alu.asm` — arithmetic, bitwise operations, negation, destination writes, and a conditional branch.
- `multiply.asm` — repeated-addition multiplication (`6 * 7`).
- `divide.asm` — repeated-subtraction integer division (`100 / 7`).
- `fibonacci.asm` — iterative Fibonacci with loop control.
- `gcd.asm` — subtraction-based Euclidean GCD.

Each program ends with inline `.assert` directives documenting and checking its expected state. The Python assembler suite also fixes all official `comp`, `dest`, and `jump` encodings so the assembler table cannot silently drift from the Hack specification.

## Direct commands

Run from the repository root:

```sh
pixi run just hack asm multiply
pixi run just hack run multiply
pixi run python isa/hack/tools/executor.py path/to/program.asm --output isa/hack/.build/program --max-steps 1000
pixi run python -m pytest isa/hack/tests/test_assembler.py
```

The first two commands use the Hack module and its package-local catalog. The direct executor command is useful for assembly files that are not cataloged.
