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

The generated driver is a test platform. It may own reset/load orchestration, metadata-based completion or pseudo-HALT detection, watchdog limits, source assertions, and host output. Distinguish an architectural halt/trap outcome from a loop stopping policy: a step budget may stop the driver without representing successful ISA completion. A normal executor run must have a finite watchdog; exhausting a default or watchdog-mode budget is a failure, while bounded completion must be explicitly requested and paired with observable assertions. For runtime settings that have both source directives and CLI flags, use one documented precedence (`CLI > source > default`) and serialize effective overrides into the generated artifact before reloading it; do not let driver generation consume hidden pre-artifact state. Keep subtle loop-entry conditions in one clearly named driver helper, then validate the actual stop reason after the loop. Only a real encoded halt/trap belongs in the model; ROM-end policy, lowered self-loop metadata, and `max_steps` remain in the driver. Those responsibilities must not replace the model's fetch/decode/execute path.

## 5. Teaching source directives and annotated artifacts

All ISA packages share one small teaching-source contract while retaining ISA-specific target and value semantics:

- `.description <text>` gives a bundled lesson a stable human identity and is persisted into generated artifacts;
- `.max_steps <positive integer>` configures the finite executor watchdog without emitting an instruction;
- `.assert <target> == <integer>` and `!=` compare the target's exact bit pattern;
- ordered comparisons require `signed(<target>)` or `unsigned(<target>)` explicitly;
- equality assertions must not use signed/unsigned wrappers.

The shared parser owns this surface grammar, integer syntax, duplicate singleton directives, and comparison-mode spelling. Each ISA owns target canonicalization, aliases, widths, ranges, alignment, and the generated Sail expression. A frontend such as constrained C may carry the same directives in source comments: every marked directive line must be parsed immediately, malformed or unknown marked lines must fail rather than disappear, and generated teaching assembly must preserve the original source line used by diagnostics.

Generated annotated machine images begin with exactly one contiguous, versioned `//%` manifest block. Its common envelope records schema/version, ISA/profile, stable source identity, description, comment level, resolved runtime settings and their origins, canonical assertions plus source display spelling, optional non-empty frontend provenance, completion metadata, and ISA metadata; the public envelope has no executor metadata field. The wire syntax is a repository-defined canonical restricted S-expression, not executable Lisp and not JSON: one proper `(artifact ...)` list containing only symbols, UTF-8 quoted strings, decimal integers, and proper lists. Reject floats, quote/quasiquote forms, dotted pairs, vectors/brackets, keywords, reader booleans, reserved `nil`/`t`, duplicate or unknown fields, and non-canonical formatting. Generic nested values use explicit `(object ...)` and `(array ...)` containers plus `none`, `true`, and `false`; assertions use declarative comparison ASTs such as `(assert (<= (signed R6) -5) (source-line 68))`. `sexpdata` is only a bounded tokenizer/parser; repository code enforces the subset, grammar, one-form rule, depth/node limits, and parse-then-render canonical equality. Define persisted common and ISA-specific shapes as strict, frozen Pydantic v2 models with forbidden extra fields; use validators for local field invariants, but keep machine-context checks such as profile closure, target canonicalization, address alignment, and completion-word binding in the ISA artifact codec. At `summary` and `full`, render one indented form across multiple consecutive lines, prefixing every line with `//% `; at `none`, render the same form as one compact prefixed line. Human-readable preambles derive from the same validated model at `summary` and `full`; `none` retains only the machine-readable manifest block. Annotated artifact loaders are strict: raw or external machine-code formats require separate explicitly named frontends and must not receive invented execution metadata through a permissive fallback.

The wire contract is library-neutral: Python currently uses `sexpdata`, while a future Rust implementation may use `lexpr`/`serde-lexpr`; neither library's broader dialect may redefine the repository subset or canonical spelling.

Runtime settings follow `CLI > source > default`. Resolve them before writing the machine image, serialize the concrete value and origin, strictly reload the file, and generate the driver only from that reloaded contract. Never pass an override to driver generation as hidden Python state.

Keep information at the layer where it is most useful:

- source: intent, labels, aliases, pseudoinstructions, directives, and optional C line provenance;
- teaching assembly: normalized target assembly while preserving useful aliases and pseudo lineage;
- machine image: global manifest plus per-word source/canonical/bits provenance according to comment level;
- generated driver: the same global identity and runtime contract, raw image loads, loop policy, assertions, and diagnostic output;
- ISA model: architectural state, fetch/decode/execute/step, legality, and commit behavior only.

Shared Python infrastructure under `tools/isa_support` owns directive grammar, Pydantic manifest models, canonical restricted S-expression parsing/rendering, process execution, host-C compilation, and rollback-capable artifact publication. ISA packages depend on that infrastructure; the shared package must never import an ISA. Import canonical APIs from their defining submodules; do not add compatibility aliases or broad facade re-exports without a real versioned consumer. Share mechanisms, not assembler semantics or driver policy.

## 6. Illegal and reserved encodings

- A wildcard/default decode branch may return `DecodeIllegal`, `Reserved`, or an equivalent outcome; it must not manufacture a legal instruction.
- Preserve the raw word when it improves diagnostics or downstream handling.
- Execute only successfully decoded instructions.
- Illegal/reserved/fault outcomes must not partially update architectural state.
- If an ISA profile has no illegal machine encoding space, document that fact instead of inventing a fake failure branch. SUBLEQ's fetched A/B/C byte record is one such case.

## 7. Architecture-local design

Share conventions and infrastructure, not accidental architecture structure. Each ISA owns its state, decode contract, execution outcome, assembly syntax/lowering/encoding, artifact-specific validation, generated driver template and completion policy, workflow stages, and tests. Common source directives, manifest primitives, publication, and host build mechanics remain workspace infrastructure. Keep official terms such as `XLEN`, `IALIGN`, instruction mnemonics, and architectural register names recognizable.

When extending an ISA:

- update the model and direct Sail conformance tests together;
- update generated-driver templates when model APIs change;
- synchronize package READMEs and English/Chinese documentation;
- update the ISA's `.design` plan with only architecture-specific decisions and link back to this document for shared conventions.
