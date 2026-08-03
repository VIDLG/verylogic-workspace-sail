# Hack Sail Module

[中文](README.zh-CN.md) · [Documentation overview](https://vidlg.github.io/verylogic-workspace-sail/hack/) · [Tutorial](https://vidlg.github.io/verylogic-workspace-sail/hack/tutorial) · [ISA guide](https://vidlg.github.io/verylogic-workspace-sail/hack/isa)

This module implements the nand2tetris Hack instruction set in Sail and provides the tools needed to assemble, execute, and test Hack programs.

## Quick commands

Run from the repository root:

```sh
pixi run just hack list               # List programs/*.asm
pixi run just hack check              # Type-check hack.sail
pixi run just hack asm multiply       # Write fully annotated .build/multiply.hack
pixi run just hack asm multiply summary
pixi run just hack run multiply none  # Build without explanatory comments
pixi run just hack test               # Unit tests + every program end to end
pixi run just hack clean              # Remove generated artifacts
```

## Module map

| Path | Purpose |
| --- | --- |
| `hack.sail` | A/C decoding, ALU, registers, RAM, and PC transitions |
| `programs/*.asm` | Runnable examples and end-to-end regressions |
| `tools/assembler.py` | Standard Hack assembly, Hack+ lowering, and `.hack` I/O |
| `tools/executor.py` | Driver generation, Sail C-backend compilation, and execution |
| `tools/workflow.py` | Program discovery and command dispatch |
| `hooks.sail` / `hooks/` | Default and optional execution hooks |
| `tests/` | Assembler, executor, workflow, and Sail conformance tests |
| `.build/` | Git-ignored machine code, driver, C, and executable artifacts |

## Artifact comment levels

`asm` and `run` accept an optional comment level. The default is `full` because generated artifacts are part of the teaching interface:

| Level | `.hack` machine words | Generated `.driver.sail` |
| --- | --- | --- |
| `none` | No explanatory word comments | No explanatory comments |
| `summary` | ROM address and original source line | Stage comments and concise per-ROM mappings |
| `full` | ROM address, source text, and Hack+ expansion | Stage comments, full per-ROM mappings, assertion sources, and output semantics |

Examples:

```sh
pixi run just hack asm multiply summary
pixi run just hack run multiply full
```

Machine-readable `//%hack` metadata is always written, including at `none`; it carries assertions, HALT addresses, the hook, and the step limit required by the executor. Driver comments are recovered from the reloaded `.hack` artifact rather than from hidden assembler state.

## Program source format

Workflow discovers every direct `programs/*.asm` file in filename order. The filename stem is the command-line program name. A bundled program contains one nonempty description and at least one assertion:

```asm
.description Repeated-addition multiplication: 6 times 7

SET R0, 6
SET R1, 7
// ...
HALT

.assert R2 == 42
```

`.description` is used by `hack list`; it emits no machine word, does not enter `AssemblyMetadata`, and is not serialized to `.hack`.

To add a program:

1. create `programs/<name>.asm`;
2. add one `.description ...`;
3. add one or more `.assert` contracts;
4. run `pixi run just hack run <name>`;
5. run `pixi run just hack test`.

## Using `.assert`

Assertions describe expected architectural state without adding machine instructions. They are usually placed after `HALT`:

```asm
.description Assertion example
@1
D=A
HALT

.assert D == 1
.assert A != 0
.assert signed(R0) >= -5
.assert unsigned(R1) <= 0xFFFF
.assert PC == 2
```

Targets:

```text
A  D  PC  R0..R15  RAM[0]..RAM[32767]
```

Operators are `==`, `!=`, `<`, `<=`, `>`, and `>=`. Equality compares exact bits. Plain relational comparisons on 16-bit words default to signed interpretation; `signed(...)` and `unsigned(...)` select the mode explicitly. `PC` is always unsigned 15-bit.

| Syntax | Meaning | RHS range |
| --- | --- | --- |
| `.assert target == value` / `!=` | Bit-exact comparison | Word: `-32768..65535`; `PC`: `0..32767` |
| `.assert target < value`, etc. | Signed 16-bit relation by default | `-32768..32767` |
| `.assert signed(target) op value` | Explicit signed relation | `-32768..32767` |
| `.assert unsigned(target) op value` | Explicit unsigned relation | `0..65535` |
| `.assert PC op value` | Unsigned 15-bit relation | `0..32767` |

### Success

When every assertion passes, the executable prints:

```text
ASSERT PASS
A  = ...
D  = ...
PC = ...
R0 = ...
```

The Sail assertions and process exit status determine success; the register dump is diagnostic output.

### Failure

Changing the example to `.assert D == 2` produces a diagnostic like:

```text
Assertion failed: assertion D == 0x0002 from source line 6 failed
```

The generated program exits with status `1`, so both `hack run` and `hack test` fail. The line number points to the original `.asm` source.

Normal `run` permits a program without assertions and prints `RUN COMPLETE`. `hack test` requires assertions for every discovered program, preventing examples that execute without checking a result.

## Other source directives

```asm
.hook hooks/trace.sail
.max_steps 10_000
```

- `.hook` selects one package-relative `.sail` hook. Absolute paths and `..` are rejected.
- `.max_steps` is a watchdog when `HALT` exists, or a bounded snapshot limit when a program intentionally has no `HALT`.
- Directives emit no machine words. Assertions, HALT addresses, hooks, and step limits are stored as execution metadata.

## Hack+ pseudoinstructions

| Syntax | Standard Hack effect |
| --- | --- |
| `SET target, value` | Store an immediate or symbol address in `RAM[target]` |
| `INC target` / `DEC target` | Increment or decrement memory |
| `GOTO label` | Unconditional branch |
| `JNZ/JGT/JEQ/JGE/JLT/JLE target, label` | Read `RAM[target]` and branch |
| `HALT` | Emit a private two-instruction self-loop and record completion |

Hack+ lowers completely to standard Hack A/C instructions before label collection; it does not extend the ISA. Complete expansions and register side effects are documented in [Hack+ lowering](https://vidlg.github.io/verylogic-workspace-sail/hack/isa#how-hack-lowers-to-real-instructions).

## Sail hook API

A selected hook defines:

| Function | Called |
| --- | --- |
| `hack_hook_before_run()` | Once before execution |
| `hack_hook_before_step(step)` | Before each instruction |
| `hack_hook_after_step(step)` | After each instruction |
| `hack_hook_after_run(steps)` | After assertions pass, before final output |

Hooks run in the same Sail/C process as `hack.sail` and the generated driver, so they can read or update `A`, `D`, `PC`, and `RAM`. A custom hook replaces the default `hooks.sail`.

## Learn the implementation

1. [Run and inspect a first program](https://vidlg.github.io/verylogic-workspace-sail/hack/tutorial).
2. [Understand the Hack machine contract](https://vidlg.github.io/verylogic-workspace-sail/hack/isa).
3. [Follow parsing, lowering, and two-pass assembly](https://vidlg.github.io/verylogic-workspace-sail/hack/assembler).
4. [Follow driver generation, native execution, and tests](https://vidlg.github.io/verylogic-workspace-sail/hack/execution).
