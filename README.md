# verylogic-workspace-sail

[中文文档](README.zh-CN.md)

Pixi-managed executable Sail ISA packages. Each ISA is self-contained under `isa/<name>/`. The pinned Sail 0.20.2 binary supports Windows AMD64, Linux x86_64, and Linux aarch64. macOS is not supported because that release has no official macOS binary asset.

## Prerequisites and installation

1. Install [Pixi](https://pixi.sh/latest/installation/).
2. Install the project's pinned Sail binary into `.pixi/sail/`:

   ```sh
   pixi run just install
   pixi run sail --version
   ```

`just install` selects the official pinned Sail asset for Windows AMD64, Linux x86_64, or Linux aarch64 from [Sail Releases](https://github.com/rems-project/sail/releases), verifies its SHA-256 digest, and safely extracts it into the Git-ignored `.pixi/sail/` directory. Archive paths plus symbolic and hard links are rejected. Unsupported operating systems and architectures fail with an explicit error; macOS has no official binary asset for this release. `check`, `run`, and `test` also install Sail automatically when the selected local asset, executable, or asset-specific marker is missing.

If the release download needs a proxy, set the standard proxy environment variable only for the current shell; do not put it in project configuration. For example, in PowerShell:

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
pixi run just install
```

Sail is deliberately project-local: no system `PATH`, `SAIL_HOME`, or fixed machine-specific directory is required. Pixi activates `.pixi/sail/bin` using platform-appropriate syntax, while the Hack workflow invokes the selected absolute path (`.pixi/sail/bin/sail.exe` on Windows or `.pixi/sail/bin/sail` on Linux) after validating the asset-specific marker; an arbitrary system Sail is never used as a fallback. Pixi provides Python, Pytest, Just, GMP, MinGW GCC on Windows, and GCC on Linux. After verification, a previous manual Sail installation can be removed.

## Commands

```sh
pixi run just                         # List top-level commands and ISA modules
pixi run just install
pixi run just hack                    # List Hack commands
pixi run just hack list               # List bundled Hack programs
pixi run just hack check
pixi run just hack asm fibonacci
pixi run just hack run fibonacci
pixi run just hack run gcd
pixi run just hack test             # Hack-only tests
pixi run just test                  # Global tools plus all ISA modules
pixi run just hack clean
pixi run just clean-all
```

`asm` writes an annotated `.hack` machine-code file under `isa/<isa>/.build/` and the assembler prints the output path. `run` executes one cataloged program. `test` first runs the ISA's Pytest suite and then executes every cataloged program in integration mode, which requires assembly assertions. Hack's suite includes direct Sail-level ISA conformance checks in addition to example programs.

## Programs and execution metadata

`isa/<name>/programs.toml` is only a package-local program catalog. Each `[[programs]]` entry contains `name`, `source`, and `description`; it does not own output paths, cycle limits, or expected register values. Each ISA exposes its own commands as a Just module and owns its toolchain details. Hack's `tools/workflow.py` maps catalog entries to its assembler and executor and writes `isa/hack/.build/<program-name>.hack`.

The root `justfile` only imports ISA modules and provides global commands such as `install`, `test`, and `clean-all`. Adding another ISA does not require a generic Python dispatcher: add its module `justfile`, register one root `mod`, and include the module in the aggregate `test` and `clean-all` recipes.

Assertions live beside the code as `.assert` directives in assembly source. The assembler preserves directives and source context in annotated `.hack` output. A normal `run` accepts programs without assertions, while integration `test` passes `--require-assertions` so cataloged regression programs cannot silently test nothing. An optional `.hook hooks/name.sail` directive selects a package-local Sail hook that runs in the same generated C program.

Execution stops at `HALT` or when the program counter leaves the loaded ROM. Terminating programs therefore need no cycle count. A source-level `.max_steps` directive is optional: with `HALT` it is a failure limit, while a program without `HALT` may use it with assertions for an intentional bounded snapshot. The executor obtains it from source or annotated `.hack` metadata, never from `programs.toml`.

Pytest covers assembler/executor behavior directly in `isa/<name>/tests`; the package workflow verifies the catalog and end-to-end programs against their embedded `.assert` directives.

## Layout

```text
isa/
  hack/                   # Hack ISA package
    README.md             # English Hack documentation
    README.zh-CN.md       # Chinese Hack documentation
    hack.sail             # formal ISA semantics
    justfile              # Hack command module
    hooks.sail            # default Sail execution hooks
    hooks/                # optional program-selected hook implementations
    programs.toml         # package-local program catalog
    programs/             # assembly programs with directives
    tools/
      assembler.py        # assembler and annotated .hack writer
      executor.py         # executor and Sail C-backend driver
      workflow.py         # catalog, test, and clean orchestration
    tests/                # Hack Pytest unit and component tests
support/                  # shared C-runtime compatibility (Windows-specific code is guarded)
tests/                    # tests for global project tools
justfile                  # root module aggregation and global commands
tools/install_sail.py     # pinned project-local Sail installer
```

Pixi manages project-local Sail, Python, Pytest, Just, GCC, and GMP across the supported Windows and Linux targets. Hack documentation and its pseudocode rules are in [`isa/hack/README.md`](isa/hack/README.md).

Sail reference: <https://alasdair.github.io/manual.html>
