#!/usr/bin/env python3
"""Create a local WiiCompiled project manifest for SPM EU0."""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

from inspect_dol import Dol, inspect


MEMORY_BASE = 0x80000000


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def parse_int(text: str) -> int:
    return int(text, 0)


def rel_footprint(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 0x4C:
        raise ValueError("REL is too small")

    num_sections = struct.unpack_from(">I", data, 0x0C)[0]
    section_info = struct.unpack_from(">I", data, 0x10)[0]
    bss_size = struct.unpack_from(">I", data, 0x20)[0]

    if not 0 < num_sections < 4096:
        raise ValueError(f"implausible REL section count: {num_sections}")
    if section_info + num_sections * 8 > len(data):
        raise ValueError("REL section table extends past EOF")

    max_file_end = 0
    for i in range(num_sections):
        off_flags, size = struct.unpack_from(">II", data, section_info + i * 8)
        file_off = off_flags & ~3
        if file_off:
            max_file_end = max(max_file_end, file_off + size)

    return max(len(data), max_file_end), bss_size


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    port = root / "pc-port"

    parser = argparse.ArgumentParser()
    parser.add_argument("--dol", type=Path, default=port / "game" / "main.dol")
    parser.add_argument("--rel", type=Path, default=port / "game" / "relF.rel")
    parser.add_argument("--function-map", type=Path, default=port / "generated" / "SPM.map")
    parser.add_argument("--output", type=Path, default=port / "generated" / "spm-eu0.yml")
    parser.add_argument("--entry", type=parse_int)
    parser.add_argument("--sda-base", type=parse_int)
    parser.add_argument("--sda2-base", type=parse_int)
    parser.add_argument("--rel-load", type=parse_int)
    args = parser.parse_args()

    if not args.dol.is_file():
        raise SystemExit(f"missing DOL: {args.dol}")
    if not args.rel.is_file():
        raise SystemExit(f"missing decompressed REL: {args.rel}")
    if not args.function_map.is_file():
        raise SystemExit(
            f"missing function map: {args.function_map}\n"
            "Run scripts/make_function_map.py first."
        )

    info = inspect(args.dol)
    entry = args.entry if args.entry is not None else info["entry_point"]
    sda = args.sda_base if args.sda_base is not None else info["sda_base"]
    sda2 = args.sda2_base if args.sda2_base is not None else info["sda2_base"]

    if sda is None or sda2 is None:
        raise SystemExit(
            "Could not derive r13/r2 SDA bases. Inspect __init_registers and rerun "
            "with --sda-base and --sda2-base. Do not guess."
        )

    dol = Dol(args.dol.read_bytes())
    rel_file_size, rel_bss_size = rel_footprint(args.rel)

    # Translation-only deterministic placement. Runtime work must reserve this range
    # and bypass/replace the original dynamic OSLink path.
    rel_load = args.rel_load
    if rel_load is None:
        rel_load = align_up(dol.static_end + 0x10000, 0x10000)

    rel_end = rel_load + rel_file_size + rel_bss_size
    memory_end = max(dol.static_end, rel_end) + 0x100000
    memory_size = max(0x01800000, align_up(memory_end - MEMORY_BASE, 0x100000))

    if rel_load < MEMORY_BASE:
        raise SystemExit("REL load address is below guest memory base")
    if rel_end > MEMORY_BASE + memory_size:
        raise SystemExit("REL does not fit in configured guest memory")

    # Paths below are relative to pc-port/vendor/Wiicompiled (workspace_root).
    manifest = f"""schema_version: 1
workspace_root: ../vendor/Wiicompiled

project:
  id: spm-eu0-pc-port
  display_name: Super Paper Mario EU0 PC Port

memory:
  base: 0x{MEMORY_BASE:08X}
  size: 0x{memory_size:08X}
  sda_base: 0x{sda:08X}
  sda2_base: 0x{sda2:08X}

inputs:
  dol:
    path: ../../game/main.dol
  rel:
    path: ../../game/relF.rel
    load_address: 0x{rel_load:08X}

translation:
  entry_points:
    - 0x{entry:08X}
  function_map:
    path: ../../generated/SPM.map
  allow_unsupported_instructions: false

runtime:
  native_registration_root: runtime/src
  native_abi_directories:
    - runtime/src/hle/gx

output:
  root: ../../build/generated
  functions: functions
  runtime_config: RuntimeConfig.h
  data_initializer: data_sections_init.cpp
  base_manifest: ../../build/base/spm_base_manifest.json
"""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(manifest, encoding="utf-8", newline="\n")

    print(f"Wrote {args.output}")
    print(f"entry      = 0x{entry:08X}")
    print(f"SDA r13    = 0x{sda:08X}")
    print(f"SDA2 r2    = 0x{sda2:08X}")
    print(f"REL base   = 0x{rel_load:08X} (translation placement)")
    print(f"memory     = 0x{MEMORY_BASE:08X}+0x{memory_size:X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
