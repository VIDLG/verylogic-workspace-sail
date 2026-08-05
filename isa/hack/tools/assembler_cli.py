from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
ROOT = PACKAGE_ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from isa.hack.tools.artifact import apply_runtime_overrides, write_hack
from isa.hack.tools.assembler import AssemblyError, assemble
from tools.isa_support.cli import COMMENT_LEVELS, positive_int_arg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assemble a Hack .asm program into an annotated .hack machine image"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument(
        "--max-steps",
        type=positive_int_arg,
        help="override source .max_steps metadata",
    )

    parser.add_argument(
        "--comments",
        choices=COMMENT_LEVELS,
        default="summary",
        help="explanatory artifact comments: none, summary (default), or full",
    )
    args = parser.parse_args()

    try:
        source = Path(args.source)
        output = Path(args.output)
        assembly = apply_runtime_overrides(
            assemble(source),
            max_steps=args.max_steps,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        write_hack(assembly, output, args.comments)
    except (AssemblyError, OSError, ValueError) as error:
        parser.error(str(error))

    print(f"ASSEMBLED {source} -> {output} ({len(assembly.records)} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
