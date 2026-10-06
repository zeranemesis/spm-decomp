from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "pc-port" / "scripts"


def put_u32be(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into(">I", buf, off, value & 0xFFFFFFFF)


def make_branch(pc: int, target: int, *, link: bool = True) -> int:
    delta = target - pc
    return (18 << 26) | (delta & 0x03FFFFFC) | (1 if link else 0)


def make_addis(rd: int, ra: int, imm: int) -> int:
    return (15 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def make_addi(rd: int, ra: int, imm: int) -> int:
    return (14 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def write_synthetic_dol(path: Path) -> None:
    data = bytearray(0x300)

    text_file_off = 0x100
    text_addr = 0x80006000
    text_size = 0x100
    entry = text_addr
    init_registers = text_addr + 0x40

    put_u32be(data, 0x00, text_file_off)
    put_u32be(data, 0x48, text_addr)
    put_u32be(data, 0x90, text_size)
    put_u32be(data, 0xD8, 0x80007000)
    put_u32be(data, 0xDC, 0x100)
    put_u32be(data, 0xE0, entry)

    put_u32be(data, text_file_off, make_branch(entry, init_registers, link=True))

    init_off = text_file_off + (init_registers - text_addr)
    put_u32be(data, init_off + 0x00, make_addis(13, 0, 0x8040))
    put_u32be(data, init_off + 0x04, make_addi(13, 13, 0x1234))
    put_u32be(data, init_off + 0x08, make_addis(2, 0, 0x8050))
    put_u32be(data, init_off + 0x0C, make_addi(2, 2, 0x5678))

    path.write_bytes(data)


def write_synthetic_rel(path: Path) -> None:
    data = bytearray(0x90)
    put_u32be(data, 0x0C, 2)
    put_u32be(data, 0x10, 0x4C)
    put_u32be(data, 0x20, 0x20)
    data[0x30] = 1
    put_u32be(data, 0x34, 4)

    put_u32be(data, 0x4C, 0)
    put_u32be(data, 0x50, 0)
    put_u32be(data, 0x54, 0x61)
    put_u32be(data, 0x58, 0x10)

    path.write_bytes(data)


class PcPortToolingTests(unittest.TestCase):
    def run_script(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            self.fail(
                f"{script} returned {result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def test_inspect_dol_derives_entry_and_sda_bases(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dol = Path(td) / "main.dol"
            write_synthetic_dol(dol)

            result = self.run_script("inspect_dol.py", str(dol), "--json")
            info = json.loads(result.stdout)

            self.assertEqual(info["entry_point"], 0x80006000)
            self.assertEqual(info["init_registers"], 0x80006040)
            self.assertEqual(info["sda_base"], 0x80401234)
            self.assertEqual(info["sda2_base"], 0x80505678)
            self.assertEqual(info["static_end"], 0x80007100)

    def test_make_function_map_filters_non_functions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            symbols = td / "symbols.txt"
            output = td / "SPM.map"
            symbols.write_text(
                "\n".join(
                    [
                        "foo = .text:0x80001000 // type:function",
                        "not_a_function = .data:0x80002000 // type:object",
                        "_baz = .text:0x80003000 // type:func",
                        "foo_alias = .text:0x80001000 // type:function",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            self.run_script(
                "make_function_map.py",
                "--symbols",
                str(symbols),
                "--output",
                str(output),
            )

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "80001000 foo\n80003000 _baz\n",
            )

    def test_make_manifest_uses_dol_and_rel_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            dol = td / "main.dol"
            rel = td / "relF.rel"
            function_map = td / "SPM.map"
            output = td / "spm-eu0.yml"

            write_synthetic_dol(dol)
            write_synthetic_rel(rel)
            function_map.write_text("80006000 start\n", encoding="utf-8")

            self.run_script(
                "make_manifest.py",
                "--dol",
                str(dol),
                "--rel",
                str(rel),
                "--function-map",
                str(function_map),
                "--output",
                str(output),
            )

            manifest = output.read_text(encoding="utf-8")
            self.assertIn("sda_base: 0x80401234", manifest)
            self.assertIn("sda2_base: 0x80505678", manifest)
            self.assertIn("load_address: 0x80020000", manifest)
            self.assertIn("    - 0x80006000", manifest)
            self.assertIn("    - 0x80020064", manifest)
            self.assertIn("size: 0x01800000", manifest)


if __name__ == "__main__":
    unittest.main()
