# Design Brief: verylogic Sail ISA Documentation

## Purpose

Build a bilingual documentation site for an educational Sail workspace. The site should help readers run an ISA model, learn the modeled ISA, and understand the supporting assembler and execution workflow without mixing repository-maintenance decisions into reader-facing content.

## Audiences

1. Learners studying Hack, nand2tetris, or executable ISA specifications.
2. Contributors reading or changing the Hack Sail model and Python toolchain.
3. Maintainers adding future ISA modules to the workspace.

## Core jobs

1. Run a working example quickly.
2. Understand the Hack ISA before reading implementation code.
3. Follow assembly source through machine code and native execution.
4. Find exact module commands and source directives.
5. Add or maintain an ISA module without coupling it to Hack internals.

## Constraints

- Root and package README files must remain useful on GitHub.
- Long-form documentation has one published home under `site/docs/`.
- English and Simplified Chinese pages use matching routes and structure.
- Node is supplied by Pixi; Rspress dependencies remain inside `site/`.
- Public documentation contains durable product and technical facts, not migration history or documentation-policy rationale.
