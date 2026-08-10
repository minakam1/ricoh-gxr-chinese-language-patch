#!/usr/bin/env python3
"""Build a config-layer GXR 1.51 English-slot -> Simplified Chinese candidate.

This is intentionally not a flash package. It patches only `ilaunch3` at the
two points that copy persistent language configuration into the runtime camera
settings object:

* persistent 0 (Japanese) -> runtime 0
* persistent 1 (English)  -> runtime 6 (Simplified Chinese)
* all other valid IDs      -> unchanged

The persistent setting remains 1, so the Japan-region two-item language menu
can continue to represent the choice as `English`. All resource containers
remain byte-identical to the official firmware.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "GXR Update" / "Firmware rel 1.51" / "ilaunch3"
OUTPUT_DIR = ROOT / "analysis" / "gxr151_english_runtime_id6_candidate"
OUTPUT = OUTPUT_DIR / "ilaunch3"
REPORT = OUTPUT_DIR / "report.json"

HEADER_SIZE = 0x200
CHECKSUM_OFFSET = 0x16C

BOOT_PATCH_VA = 0x20067148
BOOT_PATCH_OFFSET = 0x1C348
BOOT_ORIGINAL = bytes.fromhex(
    "d0 c0 20 0c "  # seth r0,#0x200c
    "80 e0 0d 9c "  # or3 r0,r0,#0x0d9c
    "20 c0 "        # ld r0,@r0
    "f0 00 "        # nop
    "a0 90 00 17"   # ldub r0,@(23,r0)
)
BOOT_REPLACEMENT = bytes.fromhex(
    "61 01 "        # ldi r1,#1
    "f0 00 "        # nop (alignment)
    "b0 11 00 03 "  # bne r0,r1,0x20067158
    "60 06 "        # ldi r0,#6
    "f0 00 "        # nop
    "80 e0 00 00"   # aligned 32-bit no-op: or3 r0,r0,#0
)

SYNC_INVALID_BRANCH_VA = 0x20067574
SYNC_INVALID_BRANCH_OFFSET = 0x1C774
SYNC_INVALID_BRANCH_ORIGINAL = bytes.fromhex("7f 02")
SYNC_INVALID_BRANCH_REPLACEMENT = bytes.fromhex(
    "7f 04"  # invalid ID: branch directly to runtime store at 0x20067584
)

SYNC_PATCH_VA = 0x20067578
SYNC_PATCH_OFFSET = 0x1C778
SYNC_ORIGINAL = bytes.fromhex(
    "a2 91 00 17 "  # ldub r2,@(23,r1)
    "d0 c0 20 0c "  # seth r0,#0x200c
    "80 e0 0d ac "  # or3 r0,r0,#0x0dac
    "21 c0 "        # ld r1,@r0
    "f0 00 "        # nop
    "a2 01 03 97"   # stb r2,@(919,r1)
)
SYNC_REPLACEMENT = bytes.fromhex(
    "12 80 "        # mv r2,r0 (validated persistent language ID)
    "61 01 "        # ldi r1,#1
    "b2 11 00 02 "  # bne r2,r1,0x20067584
    "62 06 "        # ldi r2,#6
    "f0 00 "        # nop
    "a2 03 03 97 "  # stb r2,@(919,r3), r3 is runtime settings object
    "80 e0 00 00"   # aligned 32-bit no-op
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
    # Multi-section `launch3` containers use phase zero.
    return (
        sum(
            byte * ((index % 6) + 2)
            for index, byte in enumerate(data[HEADER_SIZE:])
        )
        & 0xFFFFFFFF
    )


def assert_original(data: bytes, offset: int, expected: bytes, name: str) -> None:
    actual = data[offset : offset + len(expected)]
    if actual != expected:
        raise ValueError(f"official ilaunch3 {name} patch site does not match")


def changed_offsets(before: bytes, after: bytes | bytearray) -> list[int]:
    return [
        index
        for index, (old, new) in enumerate(zip(before, after))
        if old != new
    ]


def main() -> None:
    original = SOURCE.read_bytes()
    stored_original = be32(original, CHECKSUM_OFFSET)
    calculated_original = firmware_checksum(original)
    if stored_original != calculated_original:
        raise ValueError("official ilaunch3 checksum mismatch")

    assert_original(original, BOOT_PATCH_OFFSET, BOOT_ORIGINAL, "boot")
    assert_original(
        original,
        SYNC_INVALID_BRANCH_OFFSET,
        SYNC_INVALID_BRANCH_ORIGINAL,
        "sync-invalid-branch",
    )
    assert_original(original, SYNC_PATCH_OFFSET, SYNC_ORIGINAL, "sync")
    if len(BOOT_REPLACEMENT) != len(BOOT_ORIGINAL):
        raise AssertionError("boot replacement length changed")
    if len(SYNC_REPLACEMENT) != len(SYNC_ORIGINAL):
        raise AssertionError("sync replacement length changed")

    patched = bytearray(original)
    patched[
        BOOT_PATCH_OFFSET : BOOT_PATCH_OFFSET + len(BOOT_REPLACEMENT)
    ] = BOOT_REPLACEMENT
    patched[
        SYNC_INVALID_BRANCH_OFFSET : SYNC_INVALID_BRANCH_OFFSET + 2
    ] = SYNC_INVALID_BRANCH_REPLACEMENT
    patched[
        SYNC_PATCH_OFFSET : SYNC_PATCH_OFFSET + len(SYNC_REPLACEMENT)
    ] = SYNC_REPLACEMENT

    new_checksum = firmware_checksum(patched)
    set_be32(patched, CHECKSUM_OFFSET, new_checksum)
    if be32(patched, CHECKSUM_OFFSET) != firmware_checksum(patched):
        raise AssertionError("candidate checksum verification failed")

    differences = changed_offsets(original, patched)
    allowed = set(range(CHECKSUM_OFFSET, CHECKSUM_OFFSET + 4))
    allowed.update(
        range(BOOT_PATCH_OFFSET, BOOT_PATCH_OFFSET + len(BOOT_REPLACEMENT))
    )
    allowed.update(
        range(
            SYNC_INVALID_BRANCH_OFFSET,
            SYNC_INVALID_BRANCH_OFFSET
            + len(SYNC_INVALID_BRANCH_REPLACEMENT),
        )
    )
    allowed.update(
        range(SYNC_PATCH_OFFSET, SYNC_PATCH_OFFSET + len(SYNC_REPLACEMENT))
    )
    if any(offset not in allowed for offset in differences):
        raise AssertionError("candidate changed bytes outside approved ranges")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(patched)
    report = {
        "status": "STATIC_CANDIDATE_NOT_A_FLASH_PACKAGE",
        "purpose": (
            "Map persistent English language ID 1 to runtime Simplified "
            "Chinese ID 6 while preserving Japanese ID 0"
        ),
        "source": str(SOURCE),
        "output": str(OUTPUT),
        "file_size": len(original),
        "sha256_before": sha256(original),
        "sha256_after": sha256(patched),
        "checksum_before": f"0x{stored_original:08X}",
        "checksum_after": f"0x{new_checksum:08X}",
        "patches": [
            {
                "name": "boot_config_copy",
                "va": f"0x{BOOT_PATCH_VA:08X}",
                "file_offset": f"0x{BOOT_PATCH_OFFSET:X}",
                "length": len(BOOT_REPLACEMENT),
            },
            {
                "name": "runtime_setting_sync_invalid_branch",
                "va": f"0x{SYNC_INVALID_BRANCH_VA:08X}",
                "file_offset": f"0x{SYNC_INVALID_BRANCH_OFFSET:X}",
                "length": 2,
            },
            {
                "name": "runtime_setting_sync",
                "va": f"0x{SYNC_PATCH_VA:08X}",
                "file_offset": f"0x{SYNC_PATCH_OFFSET:X}",
                "length": len(SYNC_REPLACEMENT),
            },
        ],
        "changed_byte_count": len(differences),
        "changed_offsets": differences,
        "resource_files_modified": [],
        "mapping": {
            "persistent_0": "runtime_0_japanese",
            "persistent_1": "runtime_6_simplified_chinese",
            "persistent_2_to_10": "unchanged",
        },
        "important_limit": (
            "Static control-flow and checksum validation only. The camera's "
            "language menu behavior with persistent ID 1 and runtime ID 6 "
            "still requires real-hardware verification."
        ),
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
