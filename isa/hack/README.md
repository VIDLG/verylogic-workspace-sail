# Hack Sail Module

[中文](README.zh-CN.md) · [Documentation overview](https://vidlg.github.io/verylogic-workspace-sail/hack/) · [Tutorial](https://vidlg.github.io/verylogic-workspace-sail/hack/tutorial) · [ISA guide](https://vidlg.github.io/verylogic-workspace-sail/hack/isa)

This module implements the nand2tetris Hack instruction set in Sail and provides the tools needed to assemble, execute, and test Hack programs.

## Quick commands

Run from the repository root:

```sh
pixi run just hack list                  # List programs/*.asm
pixi run just hack check                 # Type-check hack.sail
pixi run just hack assemble multiply     # Write summary-annotated .build/multiply.hack
pixi run just hack assemble multiply summary --max-steps 10000
pixi run just hack a multiply full       # Short alias; request full annotations
pixi run just hack run multiply none     # Build without explanatory comments
pixi run just hack r multiply            # Short alias for run
pixi run just hack run multiply summary --max-steps 10000
pixi run just hack test                  # Unit tests + every program end to end
pixi run just hack clean                 # Remove generated artifacts
```

## Module map

| Path | Purpose |
| --- | --- |
| `hack.sail` | Canonical nand2tetris Hack 16-bit ISA model: ROM storage, raw-word fetch, A/C decoding, typed stepping, ALU, registers, RAM, and PC transitions |
| `programs/*.asm` | Runnable examples and end-to-end regressions |
| `tools/assembler.py` | Pure library for Hack parsing, symbol resolution, encoding, shared-directive integration, and Hack+ lowering |
| `tools/assembler_cli.py` | Thin CLI boundary for argument handling, runtime overrides, and strict artifact publication |
| `tools/artifact.py` | Manifest creation, annotated `.hack` write/load, strict Hack validation, and runtime overrides |
| `tools/executor.py` | Driver generation, staged Sail/host-C compilation, execution, and artifact-closure publication |
| `tools/workflow.py` | Program discovery and command dispatch |
| `tests/` | Assembler, executor, workflow, and Sail conformance tests |
| `.build/` | Git-ignored machine code, driver, C, and executable artifacts |

## Execution boundary

The Sail model owns `ROM : vector(32768, word)`. `fetch_hack(pc)` returns the raw 16-bit word at `pc`, and `hack_step()` composes fetch → `decode_hack` → execute while returning a typed result. The model, not Python, therefore owns all A/C decoding.

The generated driver emits `load_program()` with raw `ROM[index] = word` assignments and optional source comments; it does not generate `instruction_at`, `execute_at`, or an address-to-decode match. A small `execution_should_continue(pc, steps)` helper centralizes the HALT-metadata, image-boundary, and step-budget conditions, while generated `main()` directly matches each `hack_step()` result and validates why the loop stopped. Reaching HALT metadata is valid completion, leaving the loaded image is an explicit error, and exhausting the default 100000-step watchdog is a failure. These completion, watchdog, assertion, and final-output policies remain driver responsibilities because standard Hack has no architectural HALT instruction.

`run` stages the complete build in a temporary directory: assemble → strict `.hack` reload → driver → Sail C → host compile → execute. Only after successful execution does it publish `.hack`, `.driver.sail`, `.c`, `.h`, and the executable as one artifact closure. Assembly, compilation, assertion, or execution failure therefore leaves the previous successful closure untouched.

## Artifact comment levels

`assemble` and `run` accept an optional comment level. The default is `summary`, which keeps the most useful source-to-machine mapping without overwhelming the artifact:

| Level | `.hack` machine words | Generated `.driver.sail` |
| --- | --- | --- |
| `none` | No explanatory word comments | No explanatory comments |
| `summary` | ROM/source location and normalized assembly for every word; Hack+ also shows `[i/n] source => canonical`; inline comments stay at the far right | Stage comments and concise annotated `ROM[index] = word` load lines |
| `full` | Summary information plus the exact original source text | Stage comments, fully annotated ROM load lines, assertion sources, and output semantics |

Examples:

```sh
pixi run just hack assemble multiply        # summary by default
pixi run just hack assemble multiply full
pixi run just hack run multiply full
```

Every generated annotated machine image `.hack` begins with one contiguous machine-readable `//%` public manifest block. At `summary` and `full`, the canonical S-expression is indented across multiple consecutive prefixed lines; at `none`, the same form is one compact prefixed line. The manifest records schema/version, ISA/profile, source kind/path, description, comment level, resolved `max_steps` value/origin, assertions, completion, and Hack metadata. Direct Hack assembly has no extra frontend transformation lineage, so empty `provenance` is omitted. `completion` is explicitly `lowered_self_loop` with word addresses. Human preamble lines disappear at `none`, but the manifest block remains. Driver configuration and comments are recovered only after strict `.hack` reload rather than from hidden assembler state.

Manifest v1 uses exact public and Hack-specific shapes. The loader validates canonical assertion targets and ranges, equality/ordered modes, display spelling, safe normalized source paths, metadata constants, the comment-level-specific manifest layout, and that every completion address points at the actual lowered `@address; 0;JMP` words. `load_hack()` accepts only this strict annotated format.

### What Hack+ expansion looks like

For `SET R0, 6`, the default `summary` output makes the four real instructions visible:

```text
0000000000000110 // ROM[0000] L4 [1/4] SET R0, 6 => @6
1110110000010000 // ROM[0001] L4 [2/4] SET R0, 6 => D=A
0000000000000000 // ROM[0002] L4 [3/4] SET R0, 6 => @R0
1110001100001000 // ROM[0003] L4 [4/4] SET R0, 6 => M=D
```

`[i/n]` means result `i` of `n` from one source pseudoinstruction. It is explanatory text, not machine code; ordinary A/C instructions have no expansion marker but still show their assembly source in `summary`. Inline assembly comments appear at the far right in `summary`; `full` preserves the exact complete source line. The same per-word text appears beside the corresponding `ROM[index] = word` load line in `.driver.sail` only after strict `.hack` reload.

## Program source format

Workflow discovers every direct `programs/*.asm` file in filename order. The filename stem is the command-line program name. Standard Hack symbols `R0..R15` mean `RAM[0]..RAM[15]`; they are memory aliases, not additional CPU registers. A bundled program contains one nonempty description and at least one assertion:

```asm
.description Repeated-addition multiplication: 6 times 7

SET R0, 6
SET R1, 7
// ...
HALT

.assert R2 == 42
```

`.description` emits no machine word. It is used by `hack list`, retained in assembly metadata, and serialized in the public artifact manifest.

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
.assert unsigned(PC) < 100
```

Targets:

```text
A  D  PC  R0..R15  RAM[0]..RAM[32767]
```

Operators are `==`, `!=`, `<`, `<=`, `>`, and `>=`. The shared directive contract makes `==`/`!=` bit-exact and forbids `signed(...)` or `unsigned(...)` wrappers on equality. Every ordered comparison must explicitly use `signed(target)` or `unsigned(target)`; there is no implicit signed default. Hack additionally rejects `signed(PC)` because `PC` is an unsigned 15-bit value.

| Syntax | Meaning | RHS range |
| --- | --- | --- |
| `.assert target == value` / `!=` | Bit-exact, unwrapped comparison | Word: `-32768..65535`; `PC`: `0..32767` |
| `.assert signed(target) op value` | Explicit signed ordered comparison | `-32768..32767` |
| `.assert unsigned(target) op value` | Explicit unsigned ordered comparison | `0..65535` |
| `.assert unsigned(PC) op value` | Explicit unsigned 15-bit ordered comparison | `0..32767` |

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
.max_steps 10_000
```

- `.max_steps` is a watchdog when `HALT` exists, or an explicitly requested bounded snapshot limit when a program has no `HALT` and has assertions. CLI `--max-steps` overrides it for `assemble` or `run`; without either explicit limit, executor runs use a 100000-step watchdog whose exhaustion is an error.
- Runtime configuration precedence is `CLI override > source directive > default`. The default `max_steps=100000` is materialized with `origin=default`; source and CLI values use `origin=source` and `origin=cli`.
- Effective overrides are serialized into `.hack` before strict reload, so driver generation never depends on hidden in-memory configuration.
- `.description`, `.max_steps`, and `.assert` use `tools.isa_support.directives` and emit no machine words.

| Concern | Source form | CLI form | Classification |
| --- | --- | --- | --- |
| Step budget | `.max_steps N` | `--max-steps N` | Overridable runtime setting |
| Program description | `.description text` | None | Source identity used by discovery |
| Architectural checks | `.assert ...` | None | Source-owned regression contract; CLI cannot weaken or replace it |
| Explanatory artifact text | None | `--comments` | Host presentation only |
| Generated-file location | None | `--output` / workflow-selected `.build` prefix | Host filesystem policy |
| Require at least one assertion | None | `--require-assertions` | Test/workflow gate, not program semantics |

A future initial-state/input facility should follow the dual pattern—for example, a source `.input` plus repeatable CLI `--input` overrides—but it should only be added with a concrete reusable-program use case. It is not needed by the current standalone examples.

## Hack+ pseudoinstructions

| Syntax | Standard Hack effect |
| --- | --- |
| `SET target, value` | Store an immediate or symbol address in `RAM[target]` |
| `MOV target, source` | Copy `RAM[source]` to `RAM[target]` |
| `CLR target` / `INC target` / `DEC target` | Clear, increment, or decrement memory |
| `ADD/SUB/AND/OR target, source` | Update `RAM[target]` with a binary memory operation |
| `NEG target` / `NOT target` | Negate or complement memory |
| `NOP` | Emit one no-operation C-instruction |
| `GOTO label` | Unconditional branch |
| `JNZ/JNE/JGT/JEQ/JGE/JLT/JLE target, label` | Read `RAM[target]` and branch |
| `HALT` | Emit a private two-instruction self-loop and record completion |

Hack+ lowers completely to standard Hack A/C instructions before label collection; it does not extend the ISA. For a pseudoinstruction that lowers to `n` real instructions, annotated artifacts mark each machine word as `[1/n]` through `[n/n]`; ordinary A/C instructions have no expansion marker. Complete expansions and register side effects are documented in [Hack+ lowering](https://vidlg.github.io/verylogic-workspace-sail/hack/isa#how-hack-lowers-to-real-instructions).

## Learn the implementation

1. [Run and inspect a first program](https://vidlg.github.io/verylogic-workspace-sail/hack/tutorial).
2. [Understand the Hack machine contract](https://vidlg.github.io/verylogic-workspace-sail/hack/isa).
3. [Follow parsing, lowering, and two-pass assembly](https://vidlg.github.io/verylogic-workspace-sail/hack/assembler).
4. [Choose a tool, platform, or ISA extension and evolve Hack](https://vidlg.github.io/verylogic-workspace-sail/hack/evolution).
5. [Follow driver generation, native execution, and tests](https://vidlg.github.io/verylogic-workspace-sail/hack/execution).
