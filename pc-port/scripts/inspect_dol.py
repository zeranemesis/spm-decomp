#!/usr/bin/env python3
"""Inspect a GameCube/Wii DOL and derive the values needed by WiiCompiled."""

from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass
from pathlib import Path


def u32be(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


@dataclass(frozen=True)
class Section:
    kind: str
    index: int
    file_offset: int
    address: int
    size: int

    @property
    def end(self) -> int:
        return self.address + self.size


class Dol:
    def __init__(self, data: bytes):
        if len(data) < 0x100:
            raise ValueError("File is too small to be a DOL")
        self.data = data

        text_offs = struct.unpack_from(">7I", data, 0x00)
        data_offs = struct.unpack_from(">11I", data, 0x1C)
        text_addrs = struct.unpack_from(">7I", data, 0x48)
        data_addrs = struct.unpack_from(">11I", data, 0x64)
        text_sizes = struct.unpack_from(">7I", data, 0x90)
        data_sizes = struct.unpack_from(">11I", data, 0xAC)

        self.sections: list[Section] = []
        for i, (off, addr, size) in enumerate(zip(text_offs, text_addrs, text_sizes)):
            if size:
                self.sections.append(Section("text", i, off, addr, size))
        for i, (off, addr, size) in enumerate(zip(data_offs, data_addrs, data_sizes)):
            if size:
                self.sections.append(Section("data", i, off, addr, size))

        self.bss_address = u32be(data, 0xD8)
        self.bss_size = u32be(data, 0xDC)
        self.entry_point = u32be(data, 0xE0)

        for s in self.sections:
            if s.file_offset + s.size > len(data):
                raise ValueError(
                    f"{s.kind}{s.index} extends past EOF: "
                    f"0x{s.file_offset:X}+0x{s.size:X}"
                )

    def guest_to_file(self, address: int) -> int | None:
        for s in self.sections:
            if s.address <= address < s.end:
                return s.file_offset + (address - s.address)
        return None

    def read_insn(self, address: int) -> int | None:
        off = self.guest_to_file(address)
        if off is None or off + 4 > len(self.data):
            return None
        return u32be(self.data, off)

    @property
    def static_end(self) -> int:
        ends = [s.end for s in self.sections]
        if self.bss_size:
            ends.append(self.bss_address + self.bss_size)
        return max(ends)


def branch_target(pc: int, insn: int) -> int | None:
    if (insn >> 26) != 18:  # b / bl
        return None
    li = insn & 0x03FFFFFC
    li = sign_extend(li, 26)
    aa = (insn >> 1) & 1
    return (li if aa else (pc + li)) & 0xFFFFFFFF


def find_init_registers(dol: Dol) -> int | None:
    # Typical Nintendo CRT __start calls __init_registers very early.
    for i in range(24):
        pc = dol.entry_point + i * 4
        insn = dol.read_insn(pc)
        if insn is None:
            break
        if (insn & 1) == 0:
            continue
        target = branch_target(pc, insn)
        if target is not None and dol.guest_to_file(target) is not None:
            return target
    return None


def derive_sda_bases(dol: Dol, start: int) -> tuple[int | None, int | None]:
    highs: dict[int, int] = {}
    values: dict[int, int] = {}

    for i in range(40):
        insn = dol.read_insn(start + i * 4)
        if insn is None:
            break

        opcode = insn >> 26
        rd = (insn >> 21) & 0x1F
        ra = (insn >> 16) & 0x1F
        imm = insn & 0xFFFF

        # lis rD, imm == addis rD, r0, imm
        if opcode == 15 and ra == 0:
            highs[rd] = (sign_extend(imm, 16) << 16) & 0xFFFFFFFF
            continue

        # ori rA, rS, imm
        if opcode == 24:
            rs = rd
            dest = ra
            if rs == dest and dest in highs:
                values[dest] = (highs[dest] | imm) & 0xFFFFFFFF
            continue

        # addi rD, rA, imm (often paired with lis @ha)
        if opcode == 14 and rd == ra and rd in highs:
            values[rd] = (highs[rd] + sign_extend(imm, 16)) & 0xFFFFFFFF

    return values.get(13), values.get(2)


def inspect(path: Path) -> dict:
    dol = Dol(path.read_bytes())
    init_regs = find_init_registers(dol)
    sda = sda2 = None
    if init_regs is not None:
        sda, sda2 = derive_sda_bases(dol, init_regs)

    return {
        "path": str(path),
        "entry_point": dol.entry_point,
        "entry_point_hex": f"0x{dol.entry_point:08X}",
        "init_registers": init_regs,
        "init_registers_hex": None if init_regs is None else f"0x{init_regs:08X}",
        "sda_base": sda,
        "sda_base_hex": None if sda is None else f"0x{sda:08X}",
        "sda2_base": sda2,
        "sda2_base_hex": None if sda2 is None else f"0x{sda2:08X}",
        "bss_address": dol.bss_address,
        "bss_size": dol.bss_size,
        "static_end": dol.static_end,
        "static_end_hex": f"0x{dol.static_end:08X}",
        "sections": [
            {
                "kind": s.kind,
                "index": s.index,
                "file_offset": s.file_offset,
                "address": s.address,
                "size": s.size,
            }
            for s in dol.sections
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dol", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    info = inspect(args.dol)
    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    print(f"DOL:              {info['path']}")
    print(f"Entry point:      {info['entry_point_hex']}")
    print(f"__init_registers: {info['init_registers_hex'] or 'not found'}")
    print(f"_SDA_BASE_ r13:   {info['sda_base_hex'] or 'not derived'}")
    print(f"_SDA2_BASE_ r2:   {info['sda2_base_hex'] or 'not derived'}")
    print(f"Static end:       {info['static_end_hex']}")
    print(f"Sections:         {len(info['sections'])}")

    if info["sda_base"] is None or info["sda2_base"] is None:
        print("\nSDA auto-detection was incomplete. Do not guess these values;")
        print("inspect __init_registers in the DOL and pass explicit overrides later.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
