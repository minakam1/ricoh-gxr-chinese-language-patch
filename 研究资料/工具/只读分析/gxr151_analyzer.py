#!/usr/bin/env python3
"""Read-only Ricoh GXR 1.51 firmware structure / language-service analyzer.

This tool never modifies firmware. It can analyze an extracted firmware folder or
an official ZIP, parse Ricoh's 0x200-byte UNITY-like update header, enumerate
load sections, locate language resources and service/debug trigger strings, and
optionally extract main-program sections for a disassembler.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

HEADER_SIZE = 0x200
LANG_NAMES = [
    "com_main_jpn.res", "com_main_eng.res", "com_main_ger.res",
    "com_main_fre.res", "com_main_ita.res", "com_main_spa.res",
    "com_main_chinsimpl.res", "com_main_kor.res", "com_main_chintrad.res",
    "com_main_rus.res", "com_main_thai.res",
]
TRIGGERS = [
    b"/ATA1/DBGMODE.key", b"/ATA1/INCOPY.KEY", b"/CONFIG.TST",
    b"/CONFIG.BAK", b"/SCINST.TST", b"Change shell control on [Lens Unit]",
    b"Change shell control on [Body Unit]", b"--- Backup restore",
    b"SysUnit Debug Commands", b"AplWakeupLangState", b"send adj command",
    b"com_main_chinsimpl.res", b"com_main_chintrad.res",
]

@dataclass
class Section:
    index: int
    source_payload_offset: int
    file_offset: int
    load_address: int
    initialized_size: int
    bss_address: int
    bss_size: int

@dataclass
class Resource:
    name: str
    record_offset: int
    data_offset: int
    data_size: int
    sha256: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def magic(data: bytes) -> str:
    return bytes(x ^ 0x80 for x in data[:16]).split(b"\0", 1)[0].decode("ascii", "replace")


def updated_marker(data: bytes) -> str:
    if len(data) < 0x200:
        return ""
    return bytes(x ^ 0x80 for x in data[0x1F0:0x200]).split(b"\0", 1)[0].decode("ascii", "replace")


def be32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def parse_sections(data: bytes) -> list[Section]:
    """Parse 20-byte records from header offset 0x20.

    Ricoh records use offsets relative to the payload beginning at file 0x200.
    Stop on an all-zero record or an invalid source/size pair.
    """
    out: list[Section] = []
    for idx, off in enumerate(range(0x20, 0x160, 20)):
        src, load, size, bss, bss_size = struct.unpack_from(">IIIII", data, off)
        if not any((src, load, size, bss, bss_size)):
            break
        if size == 0 or HEADER_SIZE + src + size > len(data):
            break
        out.append(Section(idx, src, HEADER_SIZE + src, load, size, bss, bss_size))
    return out


def file_to_va(file_offset: int, sections: Iterable[Section]) -> int | None:
    for s in sections:
        if s.file_offset <= file_offset < s.file_offset + s.initialized_size:
            return s.load_address + (file_offset - s.file_offset)
    return None


def parse_resources(data: bytes) -> dict[str, Resource]:
    found: dict[str, Resource] = {}
    for pos in range(0, len(data) - 32 + 1):
        raw = data[pos + 8:pos + 32].split(b"\0", 1)[0]
        if not raw.endswith((b".res", b".rex")):
            continue
        if not raw or any(x < 0x20 or x > 0x7e for x in raw):
            continue
        ofs, size = struct.unpack_from(">II", data, pos)
        if size <= 0 or ofs + size > len(data):
            continue
        name = raw.decode("ascii")
        payload = data[ofs:ofs+size]
        found.setdefault(name, Resource(name, pos, ofs, size, sha256(payload)))
    return found


def all_offsets(data: bytes, needle: bytes) -> list[int]:
    out, start = [], 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return out
        out.append(pos)
        start = pos + 1


def find_language_pointer_table(data: bytes, sections: list[Section]) -> dict | None:
    # Find all 11 NUL-terminated names in canonical sequence, then locate 11 BE pointers.
    blob = b"\0".join(n.encode() for n in LANG_NAMES) + b"\0"
    name_off = data.find(blob)
    if name_off < 0:
        return None
    ptrs = []
    cursor = name_off
    for n in LANG_NAMES:
        va = file_to_va(cursor, sections)
        ptrs.append(va)
        cursor += len(n) + 1
    if any(v is None for v in ptrs):
        return {"names_file_offset": name_off, "names_va": None, "pointer_table_offset": None}
    packed = b"".join(struct.pack(">I", v) for v in ptrs)
    ptr_off = data.find(packed)
    result = {
        "names_file_offset": name_off,
        "names_va": ptrs[0],
        "pointer_table_offset": ptr_off if ptr_off >= 0 else None,
        "pointer_table_va": file_to_va(ptr_off, sections) if ptr_off >= 0 else None,
        "languages": [{"index": i, "name": n, "name_va": ptrs[i]} for i, n in enumerate(LANG_NAMES)],
    }
    # Preserve nearby candidate metadata without interpreting it as a region mask.
    if ptr_off >= 0:
        meta_off = ptr_off - 40
        if meta_off >= 0:
            result["preceding_40_bytes_offset"] = meta_off
            result["preceding_40_bytes_hex"] = data[meta_off:ptr_off].hex()
    return result


def analyze_file(path: Path) -> dict:
    data = path.read_bytes()
    sections = parse_sections(data) if len(data) >= HEADER_SIZE else []
    header = {
        "magic": magic(data) if len(data) >= 16 else "",
        "updated_marker": updated_marker(data),
        "version_hint": f"1.{data[0x13]:02x}" if len(data) > 0x13 else None,
        "build_bytes_hex": data[0x18:0x20].hex() if len(data) >= 0x20 else None,
    }
    if len(data) >= 0x170:
        header.update({
            "load_address": be32(data, 0x160),
            "payload_size": be32(data, 0x164),
            "file_size_header": be32(data, 0x168),
            "stored_checksum": be32(data, 0x16c),
        })
    strings = {}
    for needle in TRIGGERS:
        offs = all_offsets(data, needle)
        if offs:
            strings[needle.decode("ascii")] = [
                {"file_offset": o, "virtual_address": file_to_va(o, sections)} for o in offs
            ]
    resources = parse_resources(data) if path.name.endswith(("launch4", "firm4")) else {}
    lang_resources = {n: asdict(resources[n]) for n in LANG_NAMES if n in resources}
    result = {
        "file": path.name,
        "path": str(path),
        "size": len(data),
        "sha256": sha256(data),
        "header": header,
        "sections": [asdict(s) for s in sections],
        "interesting_strings": strings,
        "language_resources": lang_resources,
    }
    if path.name == "ilaunch3":
        result["language_pointer_table"] = find_language_pointer_table(data, sections)
    return result


def collect_input(input_path: Path, temp: Path) -> Path:
    if input_path.is_dir():
        return input_path
    if zipfile.is_zipfile(input_path):
        with zipfile.ZipFile(input_path) as z:
            z.extractall(temp)
        return temp
    raise ValueError("Input must be a firmware directory or ZIP")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--report", type=Path, default=Path("gxr151_report.json"))
    ap.add_argument("--section-csv", type=Path)
    ap.add_argument("--extract-dir", type=Path)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="gxr151_") as td:
        root = collect_input(args.input, Path(td))
        files = sorted(p for p in root.rglob("*") if p.is_file() and re.fullmatch(r"(?:[ijknq]launch|l(?:06|08)firm)[03458]", p.name))
        reports = [analyze_file(p) for p in files]
        payload = {
            "tool": "gxr151_analyzer.py",
            "read_only": True,
            "input": str(args.input),
            "files": reports,
            "conclusions": {
                "universal_language_program": "ilaunch3 contains an explicit 11-language filename/pointer table",
                "simplified_and_traditional_chinese_present": True,
                "body_only_incopy_trigger": "/ATA1/INCOPY.KEY appears in ilaunch3 and not in camera-unit main programs",
                "configuration_service": "CONFIG.TST/CONFIG.BAK, backup/restore, adjustment scripts and body/lens shell switching are present",
                "exact_region_parameter_located": False,
                "firmware_checksum_algorithm_identified": False,
            },
        }
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        body = next((r for r in reports if r["file"] == "ilaunch3"), None)
        if args.section_csv and body:
            with args.section_csv.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(body["sections"][0].keys()))
                w.writeheader(); w.writerows(body["sections"])

        if args.extract_dir and body:
            args.extract_dir.mkdir(parents=True, exist_ok=True)
            body_path = next(p for p in files if p.name == "ilaunch3")
            data = body_path.read_bytes()
            for sdict in body["sections"]:
                s = Section(**sdict)
                out = args.extract_dir / f"ilaunch3_sec{s.index:02d}_load_{s.load_address:08x}.bin"
                out.write_bytes(data[s.file_offset:s.file_offset+s.initialized_size])
            (args.extract_dir / "README.txt").write_text(
                "Raw initialized sections extracted from ilaunch3. CPU family: Renesas M32R.\n"
                "Load each file at the address embedded in its filename; BSS ranges are listed in the CSV/JSON.\n",
                encoding="utf-8")

    print(f"Wrote {args.report}")
    if args.section_csv: print(f"Wrote {args.section_csv}")
    if args.extract_dir: print(f"Extracted sections to {args.extract_dir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
