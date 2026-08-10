#!/usr/bin/env python3
"""Build a generic one-shot GXR 1.51 full-language unlock firmware.

Unlike the earlier body-specific experiment, this version does not import a
BADJROM.DAT from SD. It changes only BADJ byte 23 in the current body's RAM
working copy, then calls the stock checksum-and-persist routine. All per-body
calibration data therefore remains the current body's own data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import build_gxr151_bkizram_export_experiment as common


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_DIR = ROOT / "GXR Update" / "Firmware rel 1.51"
SOURCE = OFFICIAL_DIR / "ilaunch3"
OUTPUT_DIR = ROOT / "analysis" / "gxr151_generic_full_language_unlock"
OUTPUT = OUTPUT_DIR / "ilaunch3"
REPORT = OUTPUT_DIR / "report.json"

WRAPPER_VA = 0x20077FC8
WRAPPER_OFFSET = 0x2D1C8
STOCK_BADJ_PERSIST_VA = 0x2007785C
STOCK_LANGUAGE_INIT_VA = 0x201C0F50
BADJ_POINTER_ADDRESS = 0x200C0D9C
BADJ_REGION_OFFSET = 0x17
UNLOCK_VALUE = 6

ORIGINAL_WRAPPER_PREFIX = bytes.fromhex(
    "4f ec 28 7f 29 7f 2e 7f "
    "d0 c0 20 0c 85 e0 a4 d3 "
    "d0 c0 20 0b 84 af 00 0c "
    "80 e0 bd 04 66 12 1e c0 "
    "d0 c0 20 0c 80 e0 0d 9c "
    "24 c0 f0 00"
)

LANGUAGE_HOOKS = (
    {
        "name": "normal_language_commit",
        "va": 0x2035ABC8,
        "offset": 0x30FDC8,
    },
    {
        "name": "alternate_language_commit",
        "va": 0x20371F40,
        "offset": 0x327140,
    },
)
ORIGINAL_LANGUAGE_CALL_TARGET = bytes.fromhex("d0 c0 20 1c 80 e0 0f 50")
WRAPPER_LANGUAGE_CALL_TARGET = bytes.fromhex("d0 c0 20 07 80 e0 7f c8")


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def make_wrapper() -> bytes:
    block = (
        bytes.fromhex(
            "28 7f "          # push r8
            "2e 7f "          # push r14
            "18 84 "          # mv r8,r4
            "f0 00 "          # alignment nop
            "d1 c0 20 0c "    # seth r1,#0x200c
            "81 e1 0d 9c "    # or3 r1,r1,#0x0d9c
            "21 c1 "          # ld r1,@r1
            "60 06 "          # ldi r0,#6
            "a0 01 00 17"     # stb r0,@(23,r1)
        )
        + common.encode_bl(0x20077FE0, STOCK_BADJ_PERSIST_VA)
        + bytes.fromhex(
            "14 88 "          # mv r4,r8
            "f0 00"           # alignment nop
        )
        + common.encode_bl(0x20077FE8, STOCK_LANGUAGE_INIT_VA)
        + bytes.fromhex(
            "2e ef "          # pop r14
            "28 ef "          # pop r8
            "1f ce "          # ret
            "f0 00"           # nop
        )
    )
    if len(block) != len(ORIGINAL_WRAPPER_PREFIX):
        raise AssertionError("wrapper length does not match replaced prefix")
    if common.decode_bl(0x20077FE0, block[24:28]) != STOCK_BADJ_PERSIST_VA:
        raise AssertionError("BADJ persist call target mismatch")
    if common.decode_bl(0x20077FE8, block[32:36]) != STOCK_LANGUAGE_INIT_VA:
        raise AssertionError("language init call target mismatch")
    return block


def main() -> None:
    original = SOURCE.read_bytes()
    stored_before = common.be32(original, common.CHECKSUM_OFFSET)
    if stored_before != common.firmware_checksum(original):
        raise ValueError("official ilaunch3 checksum mismatch")
    if (
        original[WRAPPER_OFFSET : WRAPPER_OFFSET + len(ORIGINAL_WRAPPER_PREFIX)]
        != ORIGINAL_WRAPPER_PREFIX
    ):
        raise ValueError("official wrapper code-cave site mismatch")
    for hook in LANGUAGE_HOOKS:
        offset = hook["offset"]
        if original[offset : offset + 8] != ORIGINAL_LANGUAGE_CALL_TARGET:
            raise ValueError(f"official language hook mismatch: {hook['name']}")

    wrapper = make_wrapper()
    patched = bytearray(original)
    patched[WRAPPER_OFFSET : WRAPPER_OFFSET + len(wrapper)] = wrapper
    for hook in LANGUAGE_HOOKS:
        offset = hook["offset"]
        patched[offset : offset + 8] = WRAPPER_LANGUAGE_CALL_TARGET

    checksum_after = common.firmware_checksum(patched)
    common.set_be32(patched, common.CHECKSUM_OFFSET, checksum_after)
    if common.be32(patched, common.CHECKSUM_OFFSET) != common.firmware_checksum(
        patched
    ):
        raise AssertionError("patched firmware checksum mismatch")

    changed = [
        offset
        for offset, (before, after) in enumerate(zip(original, patched))
        if before != after
    ]
    allowed = set(range(common.CHECKSUM_OFFSET, common.CHECKSUM_OFFSET + 4))
    allowed.update(range(WRAPPER_OFFSET, WRAPPER_OFFSET + len(wrapper)))
    for hook in LANGUAGE_HOOKS:
        allowed.update(range(hook["offset"], hook["offset"] + 8))
    unexpected = [offset for offset in changed if offset not in allowed]
    if unexpected:
        raise AssertionError(f"firmware changed unexpected offsets: {unexpected}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(patched)
    report = {
        "status": "STATICALLY_VERIFIED_GENERIC_FULL_LANGUAGE_UNLOCK",
        "hardware_evidence": "User reports successful persistent full unlock",
        "source": str(SOURCE),
        "output": str(OUTPUT),
        "sha256_before": sha256(original),
        "sha256_after": sha256(patched),
        "checksum_before": f"0x{stored_before:08X}",
        "checksum_after": f"0x{checksum_after:08X}",
        "changed_byte_count": len(changed),
        "changed_offsets": changed,
        "wrapper": {
            "va": f"0x{WRAPPER_VA:08X}",
            "file_offset": f"0x{WRAPPER_OFFSET:X}",
            "badj_pointer_address": f"0x{BADJ_POINTER_ADDRESS:08X}",
            "badj_region_offset": f"0x{BADJ_REGION_OFFSET:X}",
            "unlock_value": UNLOCK_VALUE,
            "calls": [
                f"0x{STOCK_BADJ_PERSIST_VA:08X}",
                f"0x{STOCK_LANGUAGE_INIT_VA:08X}",
            ],
        },
        "language_hooks": LANGUAGE_HOOKS,
        "included_badjrom": False,
        "preserves_current_body_calibration": True,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
