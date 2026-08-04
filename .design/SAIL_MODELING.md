# Workspace Sail Modeling Conventions

These conventions keep ISA models executable, readable to learners, and structurally consistent without forcing unrelated architectures into one abstraction.

## 1. Identifier roles

| Role | Convention | Examples |
| --- | --- | --- |
| Types, unions, enums, structs | `lower_snake_case` | `word`, `instruction`, `rv32_decode_result` |
| Functions, parameters, fields, ordinary values | `lower_snake_case` | `decode_hack`, `old_pc`, `jump_control` |
| Constructors | `UpperCamelCase`, or canonical ISA mnemonic spelling when clearer | `AInstruction`, `Decoded`, `ADDI`, `ECALL` |
| Constants | Use one consistent module-local convention; specification names may stay uppercase | `RV32I_XLEN` |
| Architectural registers | Preserve the ISA-visible spelling | Hack `A/D/PC/RAM`, RISC-V `X/PC` |

Avoid C-style `_t` suffixes. When a value would shadow or visually collide with a type, rename the value for its role, such as `encoded`, `value`, `old_pc`, or `target`.

## 2. Typed bit fields

Use named bit-vector types for values that cross important boundaries:

- complete instruction/data words;
- addresses and program counters;
- register indices;
- instruction fields passed from decode to execute;
- immediates, masks, ports, or profile words whose interpretation is otherwise ambiguous.

Do not create a type alias for every one-off local slice. The goal is to expose architectural meaning, not maximize the number of declarations.

## 3. Decode and encode

Teaching models should make both the encoding relation and legality visible:

1. use a bidirectional Sail `mapping` when the legal encoding is a small, clear bijection;
2. expose an explicit `decode_<isa>(encoded)` entry point when instruction classes, reserved prefixes, or illegal fields need a readable `match`;
3. let that decode wrapper call the mapping only after legality is established;
4. return a typed decoded or illegal/reserved result;
5. preserve unknown or reserved encodings explicitly;
6. expose `encode_<isa>(instruction)` through the mapping, or define a separate encoder when the ISA is too complex for one readable bijection.

Hack demonstrates `mapping encdec` plus a legality-checking `decode_hack` wrapper. RV32I demonstrates separate explicit decode/encode functions because opcode, `funct3`, `funct7`, and reserved-field checks are more complex.

Canonical encode/decode round-trip tests are useful, but fixed known words must remain independent test oracles.

## 4. Program images, fetch, and generated drivers

Keep the executable path visibly layered even when a teaching program is embedded into generated Sail:

1. a generated driver loads raw encoded words or bytes into the model's instruction storage;
2. the ISA model fetches a raw instruction word or record from that storage;
3. the ISA decoder turns the raw encoding into a typed instruction, when the ISA has a separate decode stage;
4. execute consumes only the typed instruction;
5. one model-owned step function composes fetch, decode, and execute and returns an explicit outcome.

A driver must not embed decoded instruction constructors or combine address lookup with `decode_<isa>`. Per-word source annotations belong on raw image load statements, so comments describe provenance without becoming semantics.

Respect each machine's memory organization:

- a Harvard machine such as Hack has separate program `ROM` and data `RAM`; the driver initializes `ROM`, `fetch_hack` reads it, and instruction execution never writes it;
- a unified-memory machine such as RV32I, Pancake, or SUBLEQ loads the image into normal memory, so fetch observes the same bytes or words that execution may modify;
- unusual instruction records remain architecture-specific: SUBLEQ fetches three raw address bytes and does not invent an opcode decoder.

The generated driver is a test platform. It may own reset/load orchestration, metadata-based completion or pseudo-HALT detection, watchdog limits, hooks or tracing, source assertions, and host output. Distinguish an architectural halt/trap outcome from a loop stopping policy: a step budget may stop the driver without representing successful ISA completion. A normal executor run must have a finite watchdog; exhausting a default or watchdog-mode budget is a failure, while bounded completion must be explicitly requested and paired with observable assertions. For runtime settings that have both source directives and CLI flags, use one documented precedence (`CLI > source > default`) and serialize effective overrides into the generated artifact before reloading it; do not let driver generation consume hidden pre-artifact state. Keep subtle loop-entry conditions in one clearly named driver helper, then validate the actual stop reason after the loop. Only a real encoded halt/trap belongs in the model; ROM-end policy, lowered self-loop metadata, and `max_steps` remain in the driver. Those responsibilities must not replace the model's fetch/decode/execute path.

## 5. Illegal and reserved encodings

- A wildcard/default decode branch may return `DecodeIllegal`, `Reserved`, or an equivalent outcome; it must not manufacture a legal instruction.
- Preserve the raw word when it improves diagnostics or downstream handling.
- Execute only successfully decoded instructions.
- Illegal/reserved/fault outcomes must not partially update architectural state.
- If an ISA profile has no illegal machine encoding space, document that fact instead of inventing a fake failure branch. SUBLEQ's fetched A/B/C byte record is one such case.

## 6. Architecture-local design

Share conventions, not accidental structure. Each ISA owns its state, decode contract, execution outcome, assembler, driver, and tests. Keep official terms such as `XLEN`, `IALIGN`, instruction mnemonics, and architectural register names recognizable.

When extending an ISA:

- update the model and direct Sail conformance tests together;
- update generated-driver templates when model APIs change;
- synchronize package READMEs and English/Chinese documentation;
- update the ISA's `.design` plan with only architecture-specific decisions and link back to this document for shared conventions.
