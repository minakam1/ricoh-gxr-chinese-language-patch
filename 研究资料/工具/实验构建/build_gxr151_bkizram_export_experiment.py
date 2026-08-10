#!/usr/bin/env python3
"""Build a temporary GXR 1.51 BKIZRAM export experiment.

Only the body program ``ilaunch3`` is changed.  On each invocation of the
normal common-language initializer it first invokes the existing UEE54
BKIZRAM exporter, then executes the three original language initialization
calls unchanged.

The stock UEE54 callback falls back from ``/ATA1/BKIZRAM.DAT`` to ``/IROM/``
when the SD write fails.  This experiment explicitly removes that fallback:
failure sets the return value to -1 and exits without an internal write.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_DIR = ROOT / "GXR Update" / "Firmware rel 1.51"
SOURCE = OFFICIAL_DIR / "ilaunch3"
OUTPUT_ROOT = ROOT / "GXR_1.51_BKIZRAM导出实验"
SD_ROOT = OUTPUT_ROOT / "SD_ROOT"
REPORT = OUTPUT_ROOT / "manifest.json"
README = OUTPUT_ROOT / "README_刷写前必读.md"

HEADER_SIZE = 0x200
CHECKSUM_OFFSET = 0x16C

LANGUAGE_INIT_VA = 0x201C0F50
LANGUAGE_INIT_OFFSET = 0x176150
UEE54_VA = 0x200782DC
UEE54_FALLBACK_OFFSET = 0x2D51C

ORIGINAL_LANGUAGE_INIT = bytes.fromhex(
    "28 7f 2e 7f 18 84 f0 00 "
    "d0 c0 20 1d 80 e0 1e fc 14 88 1e c0 "
    "d0 c0 20 1d 80 e0 4f 24 14 88 1e c0 "
    "d0 c0 20 1d 80 e0 83 ec 14 88 1e c0"
)
ORIGINAL_FALLBACK_PREFIX = bytes.fromhex("66 06 f0 00")
SAFE_FAILURE_RETURN = bytes.fromhex(
    "68 ff "  # ldi r8,#-1
    "7f 0f"   # bra 0x20078358 (the existing UEE54 epilogue)
)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def be32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def set_be32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into(">I", data, offset, value)


def firmware_checksum(data: bytes | bytearray) -> int:
    payload_size = be32(data, 0x164)
    if payload_size != len(data) - HEADER_SIZE:
        raise ValueError("payload length does not match firmware header")
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


def decode_bl(pc: int, instruction: bytes) -> int:
    if len(instruction) != 4 or instruction[0] != 0xFE:
        raise ValueError("not a direct M32R BL instruction")
    displacement = int.from_bytes(instruction[1:], "big")
    if displacement & (1 << 23):
        displacement -= 1 << 24
    return (pc & ~3) + displacement * 4


def replacement_language_init() -> bytes:
    # r8 retains the language ID while UEE54 and the three original callees run.
    block = (
        bytes.fromhex(
            "28 7f "  # push r8
            "2e 7f "  # push r14
            "18 84 "  # mv r8,r4
            "f0 00"   # nop
        )
        + encode_bl(0x201C0F58, UEE54_VA)
        + bytes.fromhex("14 88 f0 00")
        + encode_bl(0x201C0F60, 0x201D1EFC)
        + bytes.fromhex("14 88 f0 00")
        + encode_bl(0x201C0F68, 0x201D4F24)
        + bytes.fromhex("14 88 f0 00")
        + encode_bl(0x201C0F70, 0x201D83EC)
        + bytes.fromhex(
            "80 e0 00 00 "  # or3 r0,r0,#0 (aligned 32-bit no-op)
            "80 e0 00 00"    # or3 r0,r0,#0 (aligned 32-bit no-op)
        )
    )
    if len(block) != len(ORIGINAL_LANGUAGE_INIT):
        raise AssertionError("language initializer replacement length changed")

    expected_calls = {
        0x201C0F58: UEE54_VA,
        0x201C0F60: 0x201D1EFC,
        0x201C0F68: 0x201D4F24,
        0x201C0F70: 0x201D83EC,
    }
    for pc, target in expected_calls.items():
        offset = pc - LANGUAGE_INIT_VA
        actual = decode_bl(pc, block[offset : offset + 4])
        if actual != target:
            raise AssertionError(
                f"BL at 0x{pc:08X} targets 0x{actual:08X}, "
                f"expected 0x{target:08X}"
            )
    return block


def readme(manifest: dict) -> str:
    return f"""# GXR 1.51 BKIZRAM 导出实验

## 目的

临时刷入后，在正常语言初始化过程中调用固件已有的 `UEE54` 导出函数，
把机身运行时 BKIZ 缓冲区写到 SD 卡根目录：

```text
BKIZRAM.DAT（固定 0x20000 / 131072 字节）
```

拿到该文件后应立即刷回理光官方 1.51。这个实验只用于读取并分析地区、
语言和校验结构，不会自动修改语言字段。

## 关键安全修改

官方 `UEE54` 在 `/ATA1/BKIZRAM.DAT` 写出失败时会尝试回退到 `/IROM/`。
本实验把该失败分支改成直接返回 `-1`，因此没有 SD 卡、SD 尚未挂载或
写入失败时，不会向机身 IROM 回退写入。

## 修改范围

- 29 个升级文件齐全。
- 只有机身程序 `ilaunch3` 与官方原版不同。
- 文件长度不变。
- 只改两个代码区域及头部校验字段。
- 所有资源文件和相机模块固件均为官方原版。
- 加权校验已重新计算并复核。

候选 `ilaunch3` SHA-256：

```text
{manifest['ilaunch3_sha256_after']}
```

## 操作边界

1. 使用相机格式化且无重要数据的 SD 卡，并保证电池满电。
2. 只把 `SD_ROOT` 内 29 个文件复制到 SD 卡根目录。
3. 强制执行固件更新，过程中不得断电、拔卡或拆模块。
4. 更新后让相机正常启动并等待约 20 秒，然后正常关机。
5. 取出 SD 卡接电脑，确认根目录出现 `BKIZRAM.DAT` 且大小为 131072 字节。
6. 保存该文件后，用理光官方 1.51 完整包恢复机身程序。

这是临时实验固件。即使静态校验全部通过，真机执行路径仍未验证；出现异常
应停止操作并使用官方 1.51 恢复。
"""


def main() -> None:
    official_files = sorted(path for path in OFFICIAL_DIR.iterdir() if path.is_file())
    if len(official_files) != 29:
        raise ValueError(f"expected 29 official files, found {len(official_files)}")

    original = SOURCE.read_bytes()
    stored_checksum = be32(original, CHECKSUM_OFFSET)
    calculated_checksum = firmware_checksum(original)
    if stored_checksum != calculated_checksum:
        raise ValueError("official ilaunch3 checksum mismatch")

    actual_language_init = original[
        LANGUAGE_INIT_OFFSET : LANGUAGE_INIT_OFFSET + len(ORIGINAL_LANGUAGE_INIT)
    ]
    if actual_language_init != ORIGINAL_LANGUAGE_INIT:
        raise ValueError("official common-language initializer does not match")
    actual_fallback = original[
        UEE54_FALLBACK_OFFSET : UEE54_FALLBACK_OFFSET + len(ORIGINAL_FALLBACK_PREFIX)
    ]
    if actual_fallback != ORIGINAL_FALLBACK_PREFIX:
        raise ValueError("official UEE54 fallback branch does not match")

    replacement = replacement_language_init()
    patched = bytearray(original)
    patched[
        LANGUAGE_INIT_OFFSET : LANGUAGE_INIT_OFFSET + len(replacement)
    ] = replacement
    patched[
        UEE54_FALLBACK_OFFSET : UEE54_FALLBACK_OFFSET + len(SAFE_FAILURE_RETURN)
    ] = SAFE_FAILURE_RETURN

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
        range(LANGUAGE_INIT_OFFSET, LANGUAGE_INIT_OFFSET + len(replacement))
    )
    allowed.update(
        range(UEE54_FALLBACK_OFFSET, UEE54_FALLBACK_OFFSET + len(SAFE_FAILURE_RETURN))
    )
    unexpected = [offset for offset in differences if offset not in allowed]
    if unexpected:
        raise AssertionError(f"candidate changed unexpected offsets: {unexpected}")

    if OUTPUT_ROOT.exists():
        raise FileExistsError(f"output already exists: {OUTPUT_ROOT}")
    SD_ROOT.mkdir(parents=True)
    for path in official_files:
        destination = SD_ROOT / path.name
        if path.name == "ilaunch3":
            destination.write_bytes(patched)
        else:
            shutil.copyfile(path, destination)

    manifest = {
        "status": "STATICALLY_VERIFIED_NOT_HARDWARE_TESTED",
        "purpose": "Export the 0x20000-byte runtime BKIZ buffer to /ATA1/BKIZRAM.DAT",
        "file_count": len(official_files),
        "modified_files": ["ilaunch3"],
        "ilaunch3_size": len(original),
        "ilaunch3_sha256_before": sha256(original),
        "ilaunch3_sha256_after": sha256(patched),
        "checksum_before": f"0x{stored_checksum:08X}",
        "checksum_after": f"0x{new_checksum:08X}",
        "patches": [
            {
                "name": "common_language_initializer_calls_UEE54",
                "va": f"0x{LANGUAGE_INIT_VA:08X}",
                "file_offset": f"0x{LANGUAGE_INIT_OFFSET:X}",
                "length": len(replacement),
                "calls": [
                    "0x200782DC UEE54 export",
                    "0x201D1EFC original",
                    "0x201D4F24 original",
                    "0x201D83EC original",
                ],
            },
            {
                "name": "UEE54_disable_IROM_fallback",
                "va": "0x2007831C",
                "file_offset": f"0x{UEE54_FALLBACK_OFFSET:X}",
                "before": ORIGINAL_FALLBACK_PREFIX.hex(),
                "after": SAFE_FAILURE_RETURN.hex(),
                "failure_target": "0x20078358 existing epilogue",
            },
        ],
        "changed_byte_count": len(differences),
        "changed_offsets": differences,
        "expected_output": {
            "path": "/ATA1/BKIZRAM.DAT",
            "size": 0x20000,
        },
        "explicitly_disabled_behavior": "UEE54 fallback write to /IROM/",
    }
    REPORT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    README.write_text(readme(manifest), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
