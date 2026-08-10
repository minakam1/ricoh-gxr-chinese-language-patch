#!/usr/bin/env python3
"""Read-only scanner for GXR BKIZRAM.DAT exports."""

from __future__ import annotations

from pathlib import Path
import sys


KIZ_SIZE = 0x4000
CHECKSUM_OFFSET = 0x3FFC


def checksum(block: bytes) -> tuple[int, int]:
    end = CHECKSUM_OFFSET
    declared_end = int.from_bytes(block[0xF8:0xFA], "big")
    if 0x2AAB <= declared_end < KIZ_SIZE:
        end = declared_end
    total = 0
    for offset in range(0, end & ~1, 2):
        total = (total + int.from_bytes(block[offset : offset + 2], "big")) & 0xFFFFFFFF
    return total, end


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("BKIZRAM.DAT")
    data = path.read_bytes()
    if len(data) != 0x20000:
        raise SystemExit(f"FAIL: expected 0x20000 bytes, got 0x{len(data):x}")

    matches = []
    candidates = 0
    for offset in range(0, len(data) - KIZ_SIZE + 1, 2):
        if data[offset] not in (0xAA, 0x55):
            continue
        candidates += 1
        block = data[offset : offset + KIZ_SIZE]
        calculated, end = checksum(block)
        stored = int.from_bytes(
            block[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 4], "big"
        )
        if calculated == stored:
            matches.append((offset, block, end, stored))

    print(f"file={path}")
    print(f"size=0x{len(data):x}")
    print(f"AA/55 candidates={candidates}")
    print(f"valid KIZ blocks={len(matches)}")
    for offset, block, end, stored in matches:
        print(
            f"offset=0x{offset:05x} header=0x{block[0]:02x} "
            f"kiz_plus_23_resource=0x{block[23]:02x} "
            f"kiz_plus_22_ui_enum=0x{block[22]:02x} "
            f"kiz_plus_24_destination=0x{block[24]:02x} "
            f"checksum_end=0x{end:04x} checksum=0x{stored:08x}"
        )


if __name__ == "__main__":
    main()
