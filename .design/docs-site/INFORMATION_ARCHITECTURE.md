# Information Architecture: verylogic Sail ISA Documentation

## Audience and Task Priority

Reader needs are ranked by expected frequency:

1. **Newcomers and evaluators** understand why Sail is used at the ISA layer and where prose, C/C++, HDL, custom models, and proof assistants still fit.
2. **Learners** run a Hack example, inspect the generated artifacts, and understand the ISA.
3. **Contributors** trace or change the assembler, executor, workflow, and tests.
4. **Maintainers** add another self-contained ISA module and its documentation.

The primary reading view—the place readers are expected to spend most of their time—is a long-form article in the Rspress content pane, with the locale-specific sidebar preserving learning context. Navigation should reach any article within three choices: locale, section, article.

## Site Map

- Documentation home `/` and `/zh/`
  - Why Sail `/why-sail` and `/zh/why-sail`
  - Hack overview `/hack/` and `/zh/hack/`
    - Tutorial `/hack/tutorial` and `/zh/hack/tutorial`
    - Instruction set `/hack/isa` and `/zh/hack/isa`
    - Evolve Hack `/hack/evolution` and `/zh/hack/evolution`
    - Toolchain internals
      - Assembler `/hack/assembler` and `/zh/hack/assembler`
      - Execution and tests `/hack/execution` and `/zh/hack/execution`
- Repository entry points on GitHub
  - Workspace README `/README.md` and `/README.zh-CN.md`
  - Hack package reference `/isa/hack/README.md` and `/isa/hack/README.zh-CN.md`

## Navigation Model

- **Primary navigation**: the site title/home link and locale switcher in the Rspress header. The workspace home first explains the shared Sail approach, then selects an ISA rather than duplicating each ISA's task menu.
- **Secondary navigation**: a locale-specific sidebar grouped as Workspace, Hack, and Toolchain internals. Workspace contains the documentation home followed by Why Sail. Within Hack, the order is overview, tutorial, ISA, then Evolve Hack; the advanced group contains assembler, then execution.
- **Utility navigation**: repository and package-reference links appear contextually in page introductions.
- **Small screens**: use the Rspress theme's collapsible sidebar and locale selector without a second custom navigation system.
- **Maximum depth**: three levels: locale, ISA, article.

## Content Hierarchy

### Workspace documentation home

1. Explain the workspace's executable-ISA approach and lead to Why Sail.
2. Choose an ISA module.
3. See the purpose and maturity of each available module.
4. Reach repository setup and contribution information.

### Why Sail

1. Establish the educational thesis: Sail preserves necessary ISA complexity while reducing notation- and implementation-specific noise.
2. Demonstrate the thesis with two concrete code paths: Hack `AM=D` old-state semantics and RISC-V `ADDI` encoding, sign extension, XLEN, and `x0` behavior.
3. Compare prose/pseudocode, C/C++, Verilog/SystemVerilog, ad hoc models, and proof assistants by the extra work each introduces when used as the ISA source of truth.
4. Explain why Sail fits this workspace through typed bitvectors, executable semantics, code generation, and reusable formal-tool paths.
5. State limitations explicitly: Sail is not RTL, a cycle-accurate simulator, or a proof by itself.
6. Assign assemblers, drivers, generated C, hardware, and prose to their correct neighboring layers.

### Hack overview

1. Run the first program.
2. Choose a document by learning goal.
3. See the end-to-end source-to-execution model.
4. Reach the package reference for exact syntax.

### Tutorial

1. Explain Hack, nand2tetris, NandGame, and Sail in the local learning context, while linking global tool-choice rationale to Why Sail.
2. Run and inspect one program.
3. Introduce the executable-model pipeline.
4. Offer exercises and external resources.

### ISA

1. Define the software-visible machine contract.
2. Explain instruction encodings and state transitions.
3. Separate standard Hack from assembler conveniences.
4. Map the contract to Sail.

### Evolve Hack

1. Show real `[i/n]` Hack+ expansion artifacts.
2. Separate tooling, platform, ISA, and implementation changes.
3. Offer a graduated project ladder and creative prompts.
4. Require a small experiment contract, compatibility decision, and tests.

### Assembler internals

1. Follow parser and IR stages.
2. Explain Hack+ lowering and two-pass assembly.
3. Explain source mapping and metadata.
4. Connect implementation to tests and exercises.

### Execution and tests

1. Follow machine code into a generated Sail driver.
2. Explain completion, bounds, assertions, and output.
3. Explain Sail-to-C compilation.
4. Explain workflow and regression-test layers.

### Hack package reference

1. Provide commands and module paths beside source.
2. Specify program directives and assertion behavior.
3. Summarize extension points and pseudoinstructions.
4. Link to long-form explanations rather than duplicating them.

## User Flows

### Evaluate the modeling approach

1. Reader lands on the workspace home and opens Why Sail.
2. Reader identifies the question they need to answer: architectural meaning, human explanation, hardware implementation, optimized simulation, or formal proof.
3. Reader compares each representation at the correct abstraction layer rather than treating all languages as direct substitutes.
4. Reader continues to Hack when the goal is to inspect and execute ISA semantics.

### First successful run

1. Reader lands on the workspace or Hack overview.
2. Reader installs dependencies with Pixi.
3. Reader runs `pixi run just hack run multiply`.
4. Reader sees `ASSERT PASS` and continues to the tutorial.

### Learn the Hack machine

1. Reader starts with the tutorial for context.
2. Reader opens the ISA guide for the machine contract.
3. Reader follows assembler lowering into real A/C instructions.
4. Reader follows execution into Sail assertions and tests.

### Inspect generated annotated artifacts

1. Learner runs `pixi run just hack assemble multiply` to correlate source lines and Hack+ expansion positions with ROM addresses.
2. Learner runs `pixi run just hack run multiply full` to generate and execute the complete annotated artifact set.
3. Learner compares each annotated machine word in `.hack` with the matching raw `ROM[index] = word` load line in `.driver.sail`.
4. Learner follows the Toolchain internals section when ready to understand how those comments cross the file boundary.

### Evolve the machine

1. Learner completes the tutorial and ISA guide.
2. Learner opens Evolve Hack and classifies an idea as tooling, platform, ISA, or implementation work.
3. Learner writes an experiment contract and identifies the required model/tool/test changes.
4. Learner implements one small extension while keeping standard regressions passing unless incompatibility is explicit.

### Debug or extend the toolchain

1. Contributor starts from `isa/hack/README` or a source file.
2. Contributor uses the module map to select assembler or executor documentation.
3. Contributor changes code and runs focused tests.
4. Contributor runs `pixi run just hack test` for the complete module.

### Add another ISA

1. Maintainer reads the root [`AGENTS.md`](../../AGENTS.md) and shared [Sail modeling conventions](../sail/MODELING.md).
2. Maintainer creates `isa/<name>/` with its own workflow.
3. Maintainer adds matching `/<name>/` and `/zh/<name>/` documentation.
4. Maintainer adds the module to site navigation and aggregate commands.

## Documentation Naming Conventions

| Concept | Label | Notes |
| --- | --- | --- |
| Instruction-set module | ISA module | Use for `isa/<name>/` as a unit |
| Published prose | Documentation | Avoid “documentation library” when “documentation” is enough |
| Global technology rationale | Why Sail | Cross-ISA comparison belongs at Workspace level, not inside one ISA tutorial |
| Introductory sequence | Tutorial | Hands-on, ordered learning |
| Exact local syntax | Package reference | Lives beside code in `isa/<isa>/README*` |
| Python coordinator | workflow | Preserve the implementation's term |
| Creative extension article | Evolve Hack | Encourages modification while requiring precise layer boundaries |
| Advanced implementation section | Toolchain internals | Groups assembler and execution without mixing them into the beginner path |
| Machine-code runner | executor | Preserve the implementation's term |
| Extended assembly syntax | Hack+ pseudoinstruction | Never call it part of the Hack ISA |

## Sail Modeling Conventions

Repository-wide Sail naming, typed-field, explicit decode/encode, and illegal-encoding rules live in [`.design/sail/MODELING.md`](../sail/MODELING.md). ISA documentation should link or summarize architecture-specific consequences without copying the full maintenance contract into every subtree.

## Component Reuse Map

| Component | Used on | Behavior differences |
| --- | --- | --- |
| Rspress locale shell | All site pages | English and Chinese labels and routes |
| ISA sidebar group | Every ISA section | Page labels are localized; order is shared |
| Article opening | Why Sail, tutorial, ISA, evolution, assembler, execution | States the question answered and links to neighboring context |
| Cross-layer comparison table | Why Sail | Uses the same criteria and ordering in both locales |
| Package-reference link | ISA articles | Points to exact commands and directives beside source |
| Previous/next path | Ordered Hack articles | Moves through tutorial → ISA → evolution → assembler → execution |

## Content Growth Plan

- Cross-ISA concepts and workspace-wide technology choices live directly under `site/docs/<locale>/`; they must not be duplicated into every ISA subtree. Internal model-maintenance rules remain canonical in `.design/sail/MODELING.md`.
- Each new ISA receives one parallel `site/docs/<locale>/<isa>/` subtree.
- Start with overview, tutorial, and ISA; add tool-specific pages only when that ISA has those tools.
- Keep article depth flat beneath each ISA. Split an article only when it has an independent reader task and stable navigation label.
- Search is supplied by Rspress; no manually maintained global topic index is needed at the current scale.
- Package README files remain short lookup pages and should not absorb long-form articles as the site grows.

## URL Strategy

- Global English concepts use `/<concept>`, such as `/why-sail`; global Chinese concepts use `/zh/<concept>`.
- Default English ISA pattern: `/<isa>/<article>`.
- Chinese ISA pattern: `/zh/<isa>/<article>`.
- Rspress omits the default `en` locale from published URLs; `zh` remains explicit.
- ISA segments use lowercase stable module names such as `hack`.
- Overview routes come from `index.mdx`, for example `/hack/` and `/zh/hack/`.
- Article slugs: lowercase durable concepts (`tutorial`, `isa`, `evolution`, `assembler`, `execution`).
- Avoid file-format or implementation-version terms in URLs.
- Do not use query parameters for primary navigation.
