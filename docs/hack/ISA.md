# The Hack Instruction Set Architecture

[中文](ISA.zh-CN.md) · [Documentation index](../README.md) · [Assembler internals](ASSEMBLER.md) · [Execution internals](EXECUTION.md)

This document focuses on the **Hack ISA itself**: the state visible to software, machine-instruction encodings, and the state transition caused by each instruction. See the [Hack package reference](../../isa/hack/README.md) for commands, hooks, assertions, and annotated `.hack` metadata.

## What an ISA is

An instruction set architecture (ISA) is the contract between software and a processor implementation. It defines:

- registers and memory visible to programs;
- how machine words decode;
- what every instruction reads, computes, and writes;
- how the program counter advances or branches.

An ISA does not specify how many NAND gates form an adder, how long signals take to settle, or whether an implementation uses a pipeline or cache. Those are circuit or microarchitecture concerns. Two processors implement the same ISA when they produce the same architectural result from the same machine state and instruction.

The layers used by this project are distinct:

| Layer | Example | Part of the Hack ISA? |
| --- | --- | --- |
| 16-bit machine instruction | `0000000000000010`, `1110001100001000` | Yes |
| Standard Hack assembly | `@2`, `M=D`, `D;JGT` | Textual representation of machine instructions |
| Labels and symbols | `(LOOP)`, `@R0`, `@variable` | Assembler syntax, not CPU instructions |
| Hack+ pseudoinstruction | `SET`, `JEQ target,label`, `HALT` | Project-specific assembler convenience, not ISA |
| Test directive | `.assert`, `.hook`, `.max_steps` | Execution metadata; never enters ROM |
| Sail model | `hack.sail` | Executable description of the ISA semantics |

Only 16-bit A or C instructions ultimately reach the Hack CPU.

## Architecture overview

Hack is a 16-bit teaching computer with separate instruction and data storage. Programs are fetched from ROM while data is read and written in RAM, commonly described as a Harvard architecture.

### Architectural state

| State | Width | Purpose | Sail representation |
| --- | ---: | --- | --- |
| `A` | 16 bits | Address/data register; supplies addresses for `M` and jumps | `register A : word` |
| `D` | 16 bits | General data register and fixed ALU input | `register D : word` |
| `PC` | 15 bits | Address of the next ROM instruction | `register PC : program_counter` |
| RAM | 32768 × 16 bits | Data address space | `register RAM : vector(32768, word)` |
| ROM | Up to 32768 × 16 bits | Program machine words | Loaded and fetched by the generated driver |

Assembly `M` is **not a separate register**. It denotes memory at the current A address:

```text
M ≡ RAM[A[14:0]]
```

`A` is 16 bits, but memory addresses and jump targets use only its low 15 bits. An A instruction can load only `0..32767`; a C instruction that writes `A` can produce any 16-bit value.

### Hack platform memory map

The complete nand2tetris Hack platform normally interprets data addresses as:

| Address | Platform meaning |
| --- | --- |
| `0..16383` | General RAM |
| `16384..24575` | Screen bitmap (`SCREEN = 16384`) |
| `24576` | Keyboard register (`KBD = 24576`) |

The current Sail model implements every address from `0` through `32767` as plain RAM and does not yet model screen refresh or keyboard input. The instruction addressing rules are present; the device behavior is not.

## Machine-instruction formats

Every Hack machine word is 16 bits, with only two instruction forms.

### A instruction

```text
15              0
┌─┬───────────────┐
│0│ vvvvvvvvvvvvvvv│
└─┴───────────────┘
```

Standard assembly syntax:

```asm
@value
```

Semantics:

```text
A  := zero_extend_16(value)
PC := (PC + 1) mod 32768
```

For example, `@42` encodes as:

```text
0000000000101010
```

The operand may be a decimal value or a symbol. Symbol resolution is an assembler operation; the CPU sees only the final 15-bit value.

### C instruction

```text
15  13 12  6 5  3 2  0
┌─────┬───────┬────┬────┐
│ 111 │a cccccc│ddd │jjj │
└─────┴───────┴────┴────┘
```

Standard assembly syntax:

```text
[dest=]comp[;jump]
```

The fields select:

- `a + comp`: the ALU computation;
- `dest`: any combination of `A`, `D`, and `M` to receive the result;
- `jump`: whether `PC` receives the address from the old value of `A`.

`dest` and `jump` are optional; `comp` is required.

## `comp`: ALU operations

The fixed ALU input `x` is `D`. When `a=0`, `y=A`; when `a=1`, `y=M=RAM[A]`.

This table lists the canonical encodings accepted by the standard Hack assembler. `—` means that no canonical assembly form uses that combination.

| `cccccc` | `a=0` | `a=1` |
| --- | --- | --- |
| `101010` | `0` | — |
| `111111` | `1` | — |
| `111010` | `-1` | — |
| `001100` | `D` | — |
| `110000` | `A` | `M` |
| `001101` | `!D` | — |
| `110001` | `!A` | `!M` |
| `001111` | `-D` | — |
| `110011` | `-A` | `-M` |
| `011111` | `D+1` | — |
| `110111` | `A+1` | `M+1` |
| `001110` | `D-1` | — |
| `110010` | `A-1` | `M-1` |
| `000010` | `D+A` | `D+M` |
| `010011` | `D-A` | `D-M` |
| `000111` | `A-D` | `M-D` |
| `000000` | `D&A` | `D&M` |
| `010101` | `D|A` | `D|M` |

Bitwise and arithmetic results are truncated to 16 bits, so overflow wraps modulo `2^16`. Hack has no separate flags register. Jump conditions inspect whether the current ALU result is zero and whether its most significant bit is one.

## `dest`: write-back targets

From high to low, the `ddd` bits are write enables for `A`, `D`, and `M`:

| `ddd` | Assembly | Written locations |
| --- | --- | --- |
| `000` | omitted | None |
| `001` | `M` | `RAM[old_A]` |
| `010` | `D` | `D` |
| `011` | `MD` | `M`, `D` |
| `100` | `A` | `A` |
| `101` | `AM` | `A`, `M` |
| `110` | `AD` | `A`, `D` |
| `111` | `AMD` | `A`, `M`, `D` |

Multiple destinations are architecturally simultaneous. In particular, for `AM=...` or `AMD=...`, `A` receives the new result while `M` still writes RAM at the address from `old_A`.

## `jump`: conditional control flow

A jump interprets the ALU result `out` as a 16-bit two's-complement value:

| `jjj` | Assembly | Condition |
| --- | --- | --- |
| `000` | omitted | Never jump |
| `001` | `JGT` | `out > 0` |
| `010` | `JEQ` | `out == 0` |
| `011` | `JGE` | `out >= 0` |
| `100` | `JLT` | `out < 0` |
| `101` | `JNE` | `out != 0` |
| `110` | `JLE` | `out <= 0` |
| `111` | `JMP` | Always jump |

When the condition holds, the target is the low 15 bits of `A` from the start of the instruction—not the ALU result or a newly written value of `A`.

## Executing one instruction

Sail's `execute` function can be summarized as the following architectural pseudocode.

### A instruction

```text
A  = 0 @ value[14:0]
PC = PC + 1
```

### C instruction

```text
old_A    = A
y        = (a == 0) ? A : RAM[old_A[14:0]]
out      = ALU(comp, D, y)
next_PC  = (PC + 1) mod 32768

if dest.A: A = out
if dest.D: D = out
if dest.M: RAM[old_A[14:0]] = out

if jump_condition(jump, out):
    PC = old_A[14:0]
else:
    PC = next_PC
```

Saving `old_A` is the crucial detail. For example:

```asm
AM=D+1;JGT
```

If the condition holds, this one instruction:

1. computes `D+1`;
2. writes the result to `A`;
3. writes the result to RAM addressed by **old `A`**;
4. jumps to the ROM address from **old `A`**.

That is why [`hack.sail`](../../isa/hack/hack.sail) begins the C-instruction path with `let old_a = A`.

## From standard assembly to machine code

The assembler uses two passes:

1. Parse source and expand Hack+ into standard A/C instructions.
2. In pass one, record the ROM address of every `(LABEL)`; labels occupy no ROM word.
3. In pass two, resolve A-instruction symbols and encode every machine instruction.
4. Allocate previously unknown variable symbols consecutively from RAM address `16`.

Predefined symbols include:

- `R0..R15`;
- `SP=0`, `LCL=1`, `ARG=2`, `THIS=3`, and `THAT=4`;
- `SCREEN=16384` and `KBD=24576`.

An A instruction is encoded directly as `0` followed by its 15-bit value. A C instruction is concatenated as:

```text
111 + COMP[comp] + DEST[dest] + JUMP[jump]
```

For example:

```asm
M=D
```

uses `comp=D`, `dest=M`, and no jump:

```text
111 0001100 001 000
1110001100001000
```

## How Hack+ lowers to real instructions

Hack+ expansion happens **before** label resolution and machine-code encoding. Every expanded line is a standard nand2tetris Hack A or C instruction.

| Hack+ source | Standard Hack expansion | Main side effects |
| --- | --- | --- |
| `SET target, value` | `@value` / `D=A` / `@target` / `M=D` | Changes `A`, `D`, and `RAM[target]` |
| `INC target` | `@target` / `M=M+1` | Changes `A` and `RAM[target]` |
| `DEC target` | `@target` / `M=M-1` | Changes `A` and `RAM[target]` |
| `GOTO label` | `@label` / `0;JMP` | Changes `A` and jumps |
| `JNZ target, label` | `@target` / `D=M` / `@label` / `D;JNE` | Changes `A` and `D`; jumps if nonzero |
| `JGT target, label` | `@target` / `D=M` / `@label` / `D;JGT` | Changes `A` and `D`; jumps if positive |
| `JEQ target, label` | `@target` / `D=M` / `@label` / `D;JEQ` | Changes `A` and `D`; jumps if zero |
| `JGE target, label` | `@target` / `D=M` / `@label` / `D;JGE` | Changes `A` and `D`; jumps if nonnegative |
| `JLT target, label` | `@target` / `D=M` / `@label` / `D;JLT` | Changes `A` and `D`; jumps if negative |
| `JLE target, label` | `@target` / `D=M` / `@label` / `D;JLE` | Changes `A` and `D`; jumps if nonpositive |
| `HALT` | Private label + `@private-label` / `0;JMP` | Forms a self-loop on native Hack |

Subtleties worth making explicit:

- `SET R0, R1` stores the symbol `R1`'s **address value `1`** in `R0`; it does not copy the contents of `RAM[R1]`.
- Conditional pseudoinstructions read `RAM[target]` and overwrite `D`.
- `JNZ` is a readability alias; the standard Hack jump mnemonic is `JNE`.
- `HALT` is not a Hack instruction. The assembler creates a unique `__HACKPLUS_HALT_n` label and a two-instruction self-loop, then records that ROM address as execution metadata. This project's executor stops when it reaches the address; native Hack hardware would remain in the loop.

### Complete lowering example

Source:

```asm
SET R0, 6
JEQ R0, DONE
(DONE)
HALT
```

Conceptual standard Hack assembly after expansion:

```asm
@6
D=A
@R0
M=D

@R0
D=M
@DONE
D;JEQ

(DONE)
(__HACKPLUS_HALT_0)
@__HACKPLUS_HALT_0
0;JMP
```

Only after this expansion does pass one compute the ROM addresses of `DONE` and the private HALT label; pass two then emits 16-bit words. Expanded instructions therefore consume real ROM addresses, and all label addresses refer to the **expanded** program.

## Mapping this ISA to Sail

The structure of [`hack.sail`](../../isa/hack/hack.sail) follows this document closely:

| Sail definition | ISA concept |
| --- | --- |
| `type word = bits(16)` | 16-bit machine and data words |
| `union instruction` | A/C decoded forms |
| `mapping encdec` | Bidirectional mapping between words and decoded instructions |
| `register A/D/PC/RAM` | Architectural state |
| `alu` | `comp` semantics |
| `should_jump` | `jump` truth table |
| `execute` | One-instruction state transition |

The standard assembler emits only the canonical `comp` encodings in the tables above. Sail models `a` separately from the six `comp` bits; for operations that do not read `y`, noncanonical encodings with `a=1` behave as aliases in the circuit and current model, but this project's assembler never emits them.

## Model boundaries

Keep the Hack platform separate from the current executable model when interpreting results:

- ROM is owned and fetched by the generated Sail driver, not declared as a register in `hack.sail`.
- RAM currently has no Screen or Keyboard device side effects.
- `HALT`, Hack+, `.assert`, `.hook`, and `.max_steps` belong to the tool layer, not the Hack ISA.
- The model specifies architectural transitions, not gate delays, clock-edge details, or nand2tetris HDL.
- The project currently executes the model through Sail's C backend; it does not claim a completed formal equivalence proof.

## Recommended reading path

1. Read the A/C encodings and execution pseudocode in this document.
2. Open [`hack.sail`](../../isa/hack/hack.sail) and follow `encdec → alu → should_jump → execute`.
3. Compare standard assembly and Hack+ in [`programs/basic_alu.asm`](../../isa/hack/programs/basic_alu.asm).
4. Run `pixi run just hack asm basic_alu` and inspect `isa/hack/.build/basic_alu.hack`.
5. Read [`tests/isa_conformance.sail`](../../isa/hack/tests/isa_conformance.sail) to see ISA rules turned directly into tests.

## Specification sources

- [nand2tetris Chapter 4 / Project 04](https://www.nand2tetris.org/project04): Hack machine language;
- [nand2tetris Project 05](https://www.nand2tetris.org/project05): Hack CPU, Memory, and Computer;
- [nand2tetris Project 06](https://www.nand2tetris.org/project06): Hack assembler;
- [Sail Language Reference](https://alasdair.github.io/manual.html): Sail language and backends.
