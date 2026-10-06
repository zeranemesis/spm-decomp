#!/usr/bin/env python3
"""Apply SPM bootstrap adaptations to the pinned WiiCompiled runtime.

The vendored WiiCompiled checkout is local/ignored. These edits are deterministic
and idempotent. They intentionally disable Mario Kart Wii address bindings until
SPM-specific HLE addresses/ABIs are verified.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_required(path: Path, old: str, new: str, marker: str) -> str:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return "already patched"
    if old not in text:
        raise RuntimeError(
            f"{path} no longer matches the pinned WiiCompiled source; refusing to guess."
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    return "patched"


def replace_all_optional(path: Path, old: str, new: str) -> int:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count:
        path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    return count


def patch_hle_macros(root: Path) -> str:
    path = root / "runtime" / "include" / "hle_stubs.h"
    old = r'''#define PPC_NATIVE_OVERRIDE(addr_hex, name, ret_type, arg_list, call_list) \
    extern "C" ret_type func_##addr_hex arg_list { return name call_list; } \
    REGISTER_NATIVE_FUNCTION(0x##addr_hex, name)

#define PPC_NATIVE_OVERRIDE_VOID(addr_hex, name, arg_list, call_list) \
    extern "C" void func_##addr_hex arg_list { name call_list; } \
    REGISTER_NATIVE_FUNCTION(0x##addr_hex, name)
'''
    new = r'''// SPM PC-port bootstrap:
// WiiCompiled's address-native table is authored for Mario Kart Wii. Reusing those
// raw addresses for another title can replace an unrelated SPM function that merely
// happens to occupy the same address. Keep HLE implementation bodies compiled, but
// do not emit MKW func_XXXXXXXX wrappers/registrations.
#define PPC_NATIVE_OVERRIDE(addr_hex, name, ret_type, arg_list, call_list)
#define PPC_NATIVE_OVERRIDE_VOID(addr_hex, name, arg_list, call_list)
'''
    return replace_required(path, old, new, "SPM PC-port bootstrap:")


def patch_native_registration_macros(root: Path) -> str:
    path = root / "runtime" / "include" / "abi_bridge.h"
    old = r'''#define REGISTER_NATIVE_FUNCTION(address, fn) \
    static AbiTrampoline<decltype(fn)> MKW_DETAIL_MAKE_UNIQUE(_abi_native_trampoline_, __COUNTER__)(address, #fn, fn, FunctionKind::Native, false, kPpcAllNonvolatileFprMask, 0, 0, &AbiRawCpuThunk<&fn>::Invoke)

#define REGISTER_NATIVE_FUNCTION_AS(address, fn, pretty_name) \
    static AbiTrampoline<decltype(fn)> MKW_DETAIL_MAKE_UNIQUE(_abi_native_trampoline_named_, __COUNTER__)(address, pretty_name, fn, FunctionKind::Native, false, kPpcAllNonvolatileFprMask, 0, 0, &AbiRawCpuThunk<&fn>::Invoke)
'''
    new = r'''// SPM PC-port bootstrap:
// Native registrations below are keyed by Mario Kart Wii guest addresses.
// Leave translated-function registration intact, but suppress native MKW address
// registrations until each HLE is remapped against SPM symbols/ABI.
#define REGISTER_NATIVE_FUNCTION(address, fn)
#define REGISTER_NATIVE_FUNCTION_AS(address, fn, pretty_name)
'''
    return replace_required(
        path, old, new, "Native registrations below are keyed by Mario Kart Wii guest addresses."
    )


def patch_entry(root: Path) -> str:
    path = root / "runtime" / "include" / "system_bridge.h"
    old = '''// Mario Kart Wii's translated entry point. The products always boot here, so
// this is applied as the default while parsing the command line; there is no
// flag to override it.
inline constexpr uint32_t kDefaultEntryAddress = 0x800060A4u;
'''
    new = '''// Super Paper Mario EU0 translated entry point.
// pc-port/scripts/inspect_dol.py derives this directly from the user's main.dol.
inline constexpr uint32_t kDefaultEntryAddress = 0x80006124u;
'''
    return replace_required(
        path, old, new, "Super Paper Mario EU0 translated entry point."
    )


def patch_mkw_direct_guest_calls(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}

    # These are direct calls from the host runtime into specific MKW translated
    # addresses. They cannot be retained in another title just because the same
    # numerical address happens to exist there.
    alarm = root / "runtime" / "src" / "hle" / "os" / "os_alarm.cpp"
    counts["os_alarm declarations"] = replace_all_optional(
        alarm,
        'extern "C" void func_801AADE0(CpuContext* ctx);\nextern "C" void func_801A0620(CpuContext* ctx);\n',
        '// SPM bootstrap: MKW direct guest-call declarations removed.\n',
    )
    counts["os_alarm InsertAlarm"] = replace_all_optional(
        alarm,
        'func_801A0620(cpu);',
        '/* SPM bootstrap: MKW InsertAlarm address disabled; SPM mapping pending. */',
    )
    counts["os_alarm TimeToSystemTime"] = replace_all_optional(
        alarm,
        'func_801AADE0(cpu);',
        '/* SPM bootstrap: preserve r3/r4 start time; SPM TimeToSystemTime mapping pending. */',
    )

    init = root / "runtime" / "src" / "hle" / "os" / "os_init.cpp"
    counts["os_init declarations"] = replace_all_optional(
        init,
        'extern "C" void func_801A961C(CpuContext* ctx);\nextern "C" void func_8055531C(CpuContext* ctx);\n',
        '// SPM bootstrap: MKW late-init/prolog direct guest calls removed.\n',
    )
    counts["os_init OSInitAlarm"] = replace_all_optional(
        init,
        'func_801A961C(ctx);',
        '(void)ctx; /* SPM bootstrap: MKW OSInitAlarm target disabled. */',
    )
    counts["os_init StaticR"] = replace_all_optional(
        init,
        'func_8055531C(ctx);',
        '(void)ctx; /* SPM bootstrap: MKW StaticR prolog target disabled. */',
    )

    # PPCMfhid2 is explicitly registered as a translated function at the MKW-only
    # guest address 0x8012E630. In SPM, that address is a basic block inside an
    # unrelated translated function, so keeping this registration corrupts the
    # generated indirect-dispatch registry and aborts before boot.
    counts["os_init PPCMfhid2 registration"] = replace_all_optional(
        init,
        'REGISTER_TRANSLATED_FUNCTION(0x8012e630, PPCMfhid2_HLE_8012e630);',
        '// SPM bootstrap: MKW PPCMfhid2 address registration disabled.',
    )

    scheduler = root / "runtime" / "src" / "hle" / "os" / "os_scheduler.cpp"
    counts["scheduler declaration"] = replace_all_optional(
        scheduler,
        'extern "C" void func_801A1ED8(CpuContext* ctx);\n',
        '// SPM bootstrap: MKW OSSaveContext direct guest call removed.\n',
    )
    counts["scheduler OSSaveContext"] = replace_all_optional(
        scheduler,
        'func_801A1ED8(cpu);',
        'cpu->gpr[3] = 0; /* SPM bootstrap: emulate initial OSSaveContext return. */',
    )

    audio = root / "runtime" / "src" / "hle" / "audio" / "ax_effects.cpp"
    counts["audio declaration"] = replace_all_optional(
        audio,
        'extern "C" void func_8012B830(CpuContext* ctx);\n',
        '// SPM bootstrap: MKW AX fallback direct guest call removed.\n',
    )
    counts["audio AX fallback"] = replace_all_optional(
        audio,
        'func_8012B830(ctx);',
        'return; /* SPM bootstrap: MKW AX fallback target disabled. */',
    )

    network = root / "runtime" / "src" / "hle" / "net" / "network_config.cpp"
    counts["network declarations"] = replace_all_optional(
        network,
        'extern "C" void func_801D8D30(CpuContext* ctx);\nextern "C" void func_801D9E94(CpuContext* ctx);\n',
        '// SPM bootstrap: MKW NHTTP direct guest calls removed.\n',
    )
    counts["network system info"] = replace_all_optional(
        network,
        'func_801D9E94(ctx);',
        'ctx->gpr[3] = 0; /* SPM bootstrap: no MKW NHTTP system-info target. */',
    )
    counts["network startup"] = replace_all_optional(
        network,
        'func_801D8D30(ctx);',
        'ctx->gpr[3] = 0; /* SPM bootstrap: no MKW NHTTP startup target. */',
    )

    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiicompiled", type=Path)
    args = parser.parse_args()

    root = args.wiicompiled.resolve()
    if not (root / "runtime" / "CMakeLists.txt").is_file():
        raise SystemExit(f"Invalid WiiCompiled checkout: {root}")

    print(f"hle_stubs.h:      {patch_hle_macros(root)}")
    print(f"abi_bridge.h:     {patch_native_registration_macros(root)}")
    print(f"system_bridge.h:  {patch_entry(root)}")

    counts = patch_mkw_direct_guest_calls(root)
    for name, count in counts.items():
        print(f"{name:28s}: {count} replacement(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
