# Design Brief: verylogic Sail ISA Documentation

## Purpose

Build a bilingual documentation site for an educational Sail workspace. The site should help readers understand why Sail is used for ISA semantics, run an ISA model, learn the modeled ISA, and understand the supporting assembler and execution workflow without mixing repository-maintenance decisions into reader-facing content.

## Audiences

1. Learners studying Hack, nand2tetris, or executable ISA specifications.
2. Contributors reading or changing the Hack Sail model and Python toolchain.
3. Maintainers adding future ISA modules to the workspace.

## Core jobs

1. Understand why Sail is the workspace's ISA-level source of truth and where other representations still fit.
2. Run a working example quickly.
3. Understand the Hack ISA before reading implementation code.
4. Follow assembly source through machine code and native execution.
5. Find exact module commands and source directives.
6. Add or maintain an ISA module using the shared [Sail modeling conventions](../sail/MODELING.md), without coupling it to Hack internals.

## Constraints

- Root and package README files must remain useful on GitHub.
- Long-form documentation has one published home under `site/docs/`.
- English and Simplified Chinese pages use matching routes and structure.
- Node is supplied by Pixi; Rspress dependencies remain inside `site/`.
- Public documentation contains durable product and technical facts, not migration history or documentation-policy rationale.
