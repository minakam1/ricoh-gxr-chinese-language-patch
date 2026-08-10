#!/usr/bin/env python3
"""Scan the GXR body firmware for plausible USB configuration descriptors."""

from pathlib import Path


FIRMWARE = Path(__file__).parents[1] / "GXR Update/Firmware rel 1.51/ilaunch3"
DATA = FIRMWARE.read_bytes()


def describe_config(offset: int) -> list[str] | None:
    if offset + 9 > len(DATA):
        return None
    total = int.from_bytes(DATA[offset + 2 : offset + 4], "little")
    if not (9 <= total <= 4096) or offset + total > len(DATA):
        return None

    lines = [
        (
            f"config file_off=0x{offset:08x} total={total} "
            f"interfaces={DATA[offset + 4]} value={DATA[offset + 5]} "
            f"attributes=0x{DATA[offset + 7]:02x} max_power={DATA[offset + 8] * 2}mA"
        )
    ]
    cursor = offset
    end = offset + total
    descriptor_count = 0
    while cursor + 2 <= end:
        length = DATA[cursor]
        kind = DATA[cursor + 1]
        if length < 2 or cursor + length > end:
            return None
        raw = DATA[cursor : cursor + length]
        if kind == 4 and length >= 9:
            lines.append(
                (
                    f"  interface #{raw[2]} alt={raw[3]} endpoints={raw[4]} "
                    f"class=0x{raw[5]:02x} subclass=0x{raw[6]:02x} "
                    f"protocol=0x{raw[7]:02x}"
                )
            )
        elif kind == 5 and length >= 7:
            packet = int.from_bytes(raw[4:6], "little")
            lines.append(
                (
                    f"    endpoint 0x{raw[2]:02x} attributes=0x{raw[3]:02x} "
                    f"max_packet={packet} interval={raw[6]}"
                )
            )
        descriptor_count += 1
        cursor += length
    if cursor != end or descriptor_count < 2:
        return None
    return lines


for candidate in range(len(DATA) - 9):
    if DATA[candidate : candidate + 2] != b"\x09\x02":
        continue
    result = describe_config(candidate)
    if result:
        print("\n".join(result))

print("\nDEVICE DESCRIPTORS")
for candidate in range(len(DATA) - 18):
    if DATA[candidate : candidate + 2] != b"\x12\x01":
        continue
    raw = DATA[candidate : candidate + 18]
    usb_version = int.from_bytes(raw[2:4], "little")
    max_packet = raw[7]
    configurations = raw[17]
    if usb_version not in (0x0100, 0x0110, 0x0200, 0x0210, 0x0300):
        continue
    if max_packet not in (8, 16, 32, 64):
        continue
    vendor = int.from_bytes(raw[8:10], "little")
    product = int.from_bytes(raw[10:12], "little")
    print(
        (
            f"device file_off=0x{candidate:08x} usb=0x{usb_version:04x} "
            f"class=0x{raw[4]:02x} subclass=0x{raw[5]:02x} "
            f"protocol=0x{raw[6]:02x} packet0={max_packet} "
            f"vendor=0x{vendor:04x} product=0x{product:04x} "
            f"configurations={configurations}"
        )
    )
