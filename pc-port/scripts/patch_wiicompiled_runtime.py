#!/usr/bin/env python3
"""Apply the minimal SPM bootstrap adaptations to the pinned WiiCompiled runtime.

The vendored WiiCompiled checkout is local/ignored. These edits are deterministic and
idempotent; they do not modify upstream or publish any generated Nintendo code.
"""

from __future__ import annotations

import argparse
from pathlib import Path


HLE_OLD = r'''#define PPC_NATIVE_OVERRIDE(addr_hex, name, ret_type, arg_list, call_list) \
    extern "C" ret_type func_##addr_hex arg_list { return name call_list; } \
    REGISTER_NATIVE_FUNCTION(0x##addr_hex, name)

#define PPC_NATIVE_OVERRIDE_VOID(addr_hex, name, arg_list, call_list) \
    extern "C" void func_##addr_hex arg_list { name call_list; } \
    REGISTER_NATIVE_FUNCTION(0x##addr_hex, name)
'''

HLE_NEW = r'''// SPM PC-port bootstrap:
// WiiCompiled's address-native table is authored for Mario Kart Wii. Reusing those
// raw addresses for another title can replace an unrelated SPM function that merely
// happens to occupy the same address. Keep the HLE implementation bodies compiled,
// but do not emit the MKW func_XXXXXXXX wrappers/registrations. SPM-specific HLE will
// be reintroduced only after matching symbols/ABI against the SPM map.
#define PPC_NATIVE_OVERRIDE(addr_hex, name, ret_type, arg_list, call_list)
#define PPC_NATIVE_OVERRIDE_VOID(addr_hex, name, arg_list, call_list)
'''

ENTRY_OLD = '''// Mario Kart Wii's translated entry point. The products always boot here, so
// this is applied as the default while parsing the command line; there is no
// flag to override it.
inline constexpr uint32_t kDefaultEntryAddress = 0x800060A4u;
'''

ENTRY_NEW = '''// Super Paper Mario EU0 translated entry point.
// pc-port/scripts/inspect_dol.py derives this directly from the user's main.dol.
inline constexpr uint32_t kDefaultEntryAddress = 0x80006124u;
'''


def replace_once(path: Path, old: str, new: str, marker: str) -> str:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return "already patched"
    if old not in text:
        raise RuntimeError(
            f"{path} no longer matches the pinned WiiCompiled source; refusing to guess a patch."
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    return "patched"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiicompiled", type=Path)
    args = parser.parse_args()

    root = args.wiicompiled.resolve()
    hle = root / "runtime" / "include" / "hle_stubs.h"
    bridge = root / "runtime" / "include" / "system_bridge.h"

    if not hle.is_file() or not bridge.is_file():
        raise SystemExit(f"Invalid WiiCompiled checkout: {root}")

    hle_status = replace_once(
        hle,
        HLE_OLD,
        HLE_NEW,
        "SPM PC-port bootstrap:",
    )
    entry_status = replace_once(
        bridge,
        ENTRY_OLD,
        ENTRY_NEW,
        "Super Paper Mario EU0 translated entry point.",
    )

    print(f"hle_stubs.h:   {hle_status}")
    print(f"system_bridge.h: {entry_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
