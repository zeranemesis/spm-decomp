#!/usr/bin/env python3
"""Convert dtk-style symbols.txt entries into WiiCompiled's 'address name' map."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SYMBOL_RE = re.compile(
    r"^\s*([A-Za-z_.$][A-Za-z0-9_.$@]*)\s*=\s*"
    r"(?:(?:\.[A-Za-z0-9_.$]+):)?"
    r"(0x[0-9A-Fa-f]+)"
)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        type=Path,
        default=root / "config" / "EU0" / "symbols.txt",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "pc-port" / "generated" / "SPM.map",
    )
    args = parser.parse_args()

    if not args.symbols.is_file():
        raise SystemExit(f"symbols file not found: {args.symbols}")

    functions: dict[int, str] = {}
    for raw in args.symbols.read_text(encoding="utf-8", errors="replace").splitlines():
        # Do not feed data/object symbols to the function-boundary oracle.
        lowered = raw.lower()
        if "type:function" not in lowered and "type:func" not in lowered:
            continue
        match = SYMBOL_RE.match(raw)
        if not match:
            continue
        name, addr_text = match.groups()
        address = int(addr_text, 16)
        functions.setdefault(address, name)

    if not functions:
        raise SystemExit(
            "No function symbols were parsed. The symbols.txt format may have changed; "
            "inspect a few function entries before changing the parser."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        for address, name in sorted(functions.items()):
            f.write(f"{address:08X} {name}\n")

    print(f"Wrote {len(functions):,} function boundaries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
