#!/usr/bin/env python3
"""Archived exploratory wrapper-only GXR 1.51 language-ID candidate.

This is intentionally not a flash package. It patches only the body program
`ilaunch3` so the common language initializer translates runtime language ID 1
(English) to ID 6 (Simplified Chinese).  All resource containers remain stock.
This approach is superseded because other code reads the runtime language
field directly and would still see English ID 1.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "GXR Update" / "Firmware rel 1.51" / "ilaunch3"
OUTPUT_DIR = ROOT / "analysis" / "gxr151_wrapper_exploratory_candidate"
OUTPUT = OUTPUT_DIR / "ilaunch3"
REPORT = OUTPUT_DIR / "report.json"

HEADER_SIZE = 0x200
CHECKSUM_OFFSET = 0x16C
PATCH_VA = 0x201C0F50
PATCH_FILE_OFFSET = 0x176150

ORIGINAL_BLOCK = bytes.fromhex(
    "28 7f 2e 7f 18 84 f0 00 "
    "d0 c0 20 1d 80 e0 1e fc 14 88 1e c0 "
    "d0 c0 20 1d 80 e0 4f 24 14 88 1e c0 "
    "d0 c0 20 1d 80 e0 83 ec 14 88 1e c0"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def be32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def set_be32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into(">I", data, offset, value)


def firmware_checksum(data: bytes | bytearray) -> int:
    payload_size = be32(data, 0x164)
    if payload_size != len(data) - HEADER_SIZE:
        raise ValueError("payload length does not match firmware header")
    # The multi-section `launch3` program containers use phase zero even
    # though header field 0x160 contains the first section load address.
    total = 0
    for index, byte in enumerate(data[HEADER_SIZE:]):
        total += byte * ((index % 6) + 2)
    return total & 0xFFFFFFFF


def encode_bl(pc: int, target: int) -> bytes:
    delta = target - (pc & ~3)
    if delta % 4:
        raise ValueError("BL target is not word aligned")
    displacement = delta // 4
    if not -(1 << 23) <= displacement < (1 << 23):
        raise ValueError("BL target is out of range")
    return b"\xFE" + (displacement & 0xFFFFFF).to_bytes(3, "big")


def candidate_block() -> bytes:
    # r8 keeps the effective language ID across all three calls.
    #
    #   r8 = r4
    #   if r8 == 1: r8 = 6
    #   call language_resource_init(r8)
    #   call language_font_init(r8)
    #   call language_ui_init(r8)
    #
    # Direct BL instructions replace the longer SETH/OR3/JL call sequences,
    # leaving enough room for the conditional mapping without a code cave.
    block = (
        bytes.fromhex(
            "28 7f "          # push r8
            "2e 7f "          # push r14
            "18 84 "          # mv r8,r4
            "60 01 "          # ldi r0,#1
            "b8 10 00 02 "    # bne r8,r0,0x201c0f60
            "68 06 "          # ldi r8,#6
            "14 88 "          # mv r4,r8
        )
        + encode_bl(0x201C0F60, 0x201D1EFC)
        + bytes.fromhex("14 88 f0 00")  # mv r4,r8; nop
        + encode_bl(0x201C0F68, 0x201D4F24)
        + bytes.fromhex(
            "80 e0 00 00 "    # or3 r0,r0,#0 (aligned 32-bit no-op)
            "14 88 "          # mv r4,r8
            "f0 00 "          # nop
        )
        + encode_bl(0x201C0F74, 0x201D83EC)
        + bytes.fromhex("80 e0 00 00")
    )
    if len(block) != len(ORIGINAL_BLOCK):
        raise AssertionError("replacement block length changed")
    return block


def main() -> None:
    original = SOURCE.read_bytes()
    stored_original = be32(original, CHECKSUM_OFFSET)
    calculated_original = firmware_checksum(original)
    if stored_original != calculated_original:
        raise ValueError("official ilaunch3 checksum mismatch")

    actual_block = original[
        PATCH_FILE_OFFSET : PATCH_FILE_OFFSET + len(ORIGINAL_BLOCK)
    ]
    if actual_block != ORIGINAL_BLOCK:
        raise ValueError("official ilaunch3 patch site does not match")

    replacement = candidate_block()
    patched = bytearray(original)
    patched[
        PATCH_FILE_OFFSET : PATCH_FILE_OFFSET + len(replacement)
    ] = replacement
    new_checksum = firmware_checksum(patched)
    set_be32(patched, CHECKSUM_OFFSET, new_checksum)
    if be32(patched, CHECKSUM_OFFSET) != firmware_checksum(patched):
        raise AssertionError("candidate checksum verification failed")

    differences = [
        index
        for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    ]
    allowed = set(range(CHECKSUM_OFFSET, CHECKSUM_OFFSET + 4))
    allowed.update(
        range(PATCH_FILE_OFFSET, PATCH_FILE_OFFSET + len(replacement))
    )
    if any(index not in allowed for index in differences):
        raise AssertionError("candidate changed bytes outside approved ranges")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(patched)
    report = {
        "status": "SUPERSEDED_EXPLORATORY_NOT_A_FLASH_PACKAGE",
        "purpose": "Map runtime language ID 1 (English) to ID 6 (Simplified Chinese)",
        "source": str(SOURCE),
        "output": str(OUTPUT),
        "file_size": len(original),
        "sha256_before": sha256(original),
        "sha256_after": sha256(patched),
        "checksum_before": f"0x{stored_original:08X}",
        "checksum_after": f"0x{new_checksum:08X}",
        "patch_va": f"0x{PATCH_VA:08X}",
        "patch_file_offset": f"0x{PATCH_FILE_OFFSET:X}",
        "patch_length": len(replacement),
        "changed_byte_count": len(differences),
        "changed_offsets": differences,
        "resource_files_modified": [],
        "calls": [
            "0x201D1EFC",
            "0x201D4F24",
            "0x201D83EC",
        ],
        "important_limit": (
            "Only the common initialization path receives ID 6; persistent "
            "configuration still stores ID 1, so non-initialization code may "
            "continue to apply English locale behavior."
        ),
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
