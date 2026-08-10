#!/usr/bin/env python3
"""Build a one-shot, body-specific GXR 1.51 region/language unlock package.

The package imports the exact BADJROM image previously exported from this body,
with only BADJ byte 23 changed from 0 to 6.  Firmware code shows that byte zero
limits the language menu to two entries, while any non-zero value enables all
eleven entries; value 6 is also the factory default language ID for Simplified
Chinese.

The import is performed by the stock BADJROM import/validate/persist functions.
It is triggered only when a language selection is confirmed.  The stock
fallback from a missing ATA1 file to IROM is disabled.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
from pathlib import Path

import build_gxr151_bkizram_export_experiment as common


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_DIR = ROOT / "GXR Update" / "Firmware rel 1.51"
SOURCE_FIRMWARE = OFFICIAL_DIR / "ilaunch3"
SOURCE_BADJ = ROOT / "analysis" / "body_dump_japan_20260801" / "BADJROM.DAT"
OUTPUT_ROOT = ROOT / "GXR_1.51_地区解锁_一次性"
SD_ROOT = OUTPUT_ROOT / "SD_ROOT"
REPORT = OUTPUT_ROOT / "静态验证报告.json"
README = OUTPUT_ROOT / "README_刷写前必读.md"

BADJ_SIZE = 0x4000
BADJ_REGION_OFFSET = 0x17
BADJ_CHECKSUM_OFFSET = 0x3FFC
BADJ_JAPAN_VALUE = 0
BADJ_UNLOCK_VALUE = 6

WRAPPER_VA = 0x20077FC8
WRAPPER_OFFSET = 0x2D1C8
STOCK_BADJ_IMPORT_VA = 0x20078240
STOCK_LANGUAGE_INIT_VA = 0x201C0F50
ORIGINAL_WRAPPER_SITE = bytes.fromhex(
    "4f ec 28 7f 29 7f 2e 7f "
    "d0 c0 20 0c 85 e0 a4 d3 "
    "d0 c0 20 0b 84 af 00 0c "
    "80 e0 bd 04"
)

IMPORT_FALLBACK_VA = 0x20078280
IMPORT_FALLBACK_OFFSET = 0x2D480
ORIGINAL_IMPORT_FALLBACK = bytes.fromhex("66 06 f0 00 d5 c0 20 0c")
SAFE_IMPORT_FAILURE = bytes.fromhex(
    "69 ff "  # ldi r9,#-1
    "f0 00 "  # nop
    "7f 13 "  # bra 0x200782D0
    "f0 00"   # nop
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


def badj_checksum(data: bytes | bytearray) -> int:
    if len(data) != BADJ_SIZE:
        raise ValueError(f"BADJ size must be 0x{BADJ_SIZE:X}")
    return sum(
        struct.unpack_from(">H", data, offset)[0]
        for offset in range(0, BADJ_CHECKSUM_OFFSET, 2)
    ) & 0xFFFFFFFF


def make_badj() -> tuple[bytes, dict]:
    original = SOURCE_BADJ.read_bytes()
    if len(original) != BADJ_SIZE:
        raise ValueError("body-specific BADJROM.DAT has an unexpected size")
    stored_before = common.be32(original, BADJ_CHECKSUM_OFFSET)
    calculated_before = badj_checksum(original)
    if stored_before != calculated_before:
        raise ValueError("body-specific BADJ checksum mismatch")
    if original[BADJ_REGION_OFFSET] != BADJ_JAPAN_VALUE:
        raise ValueError("body-specific BADJ is not in the expected Japan-locked state")

    patched = bytearray(original)
    patched[BADJ_REGION_OFFSET] = BADJ_UNLOCK_VALUE
    checksum_after = badj_checksum(patched)
    common.set_be32(patched, BADJ_CHECKSUM_OFFSET, checksum_after)
    if common.be32(patched, BADJ_CHECKSUM_OFFSET) != badj_checksum(patched):
        raise AssertionError("patched BADJ checksum mismatch")

    changed = [
        offset
        for offset, (before, after) in enumerate(zip(original, patched))
        if before != after
    ]
    allowed = {BADJ_REGION_OFFSET}
    allowed.update(range(BADJ_CHECKSUM_OFFSET, BADJ_CHECKSUM_OFFSET + 4))
    if any(offset not in allowed for offset in changed):
        raise AssertionError("BADJ changed outside region/checksum fields")

    return bytes(patched), {
        "source": str(SOURCE_BADJ),
        "sha256_before": sha256(original),
        "sha256_after": sha256(patched),
        "region_offset": f"0x{BADJ_REGION_OFFSET:X}",
        "region_before": original[BADJ_REGION_OFFSET],
        "region_after": patched[BADJ_REGION_OFFSET],
        "checksum_before": f"0x{stored_before:08X}",
        "checksum_after": f"0x{checksum_after:08X}",
        "changed_offsets": changed,
    }


def make_wrapper() -> bytes:
    block = (
        bytes.fromhex(
            "28 7f "  # push r8
            "2e 7f "  # push r14
            "18 84 "  # mv r8,r4
            "f0 00"   # alignment nop
        )
        + common.encode_bl(0x20077FD0, STOCK_BADJ_IMPORT_VA)
        + bytes.fromhex(
            "14 88 "  # mv r4,r8
            "f0 00"   # alignment nop
        )
        + common.encode_bl(0x20077FD8, STOCK_LANGUAGE_INIT_VA)
        + bytes.fromhex(
            "2e ef "  # pop r14
            "28 ef "  # pop r8
            "1f ce "  # ret
            "f0 00"   # nop
        )
    )
    if len(block) != len(ORIGINAL_WRAPPER_SITE):
        raise AssertionError("wrapper length does not match replaced prefix")
    if common.decode_bl(0x20077FD0, block[8:12]) != STOCK_BADJ_IMPORT_VA:
        raise AssertionError("wrapper import call target mismatch")
    if common.decode_bl(0x20077FD8, block[16:20]) != STOCK_LANGUAGE_INIT_VA:
        raise AssertionError("wrapper language call target mismatch")
    return block


def make_firmware() -> tuple[bytes, dict]:
    original = SOURCE_FIRMWARE.read_bytes()
    stored_before = common.be32(original, common.CHECKSUM_OFFSET)
    if stored_before != common.firmware_checksum(original):
        raise ValueError("official ilaunch3 checksum mismatch")
    if original[WRAPPER_OFFSET : WRAPPER_OFFSET + len(ORIGINAL_WRAPPER_SITE)] != ORIGINAL_WRAPPER_SITE:
        raise ValueError("official wrapper code-cave site mismatch")
    if original[IMPORT_FALLBACK_OFFSET : IMPORT_FALLBACK_OFFSET + len(ORIGINAL_IMPORT_FALLBACK)] != ORIGINAL_IMPORT_FALLBACK:
        raise ValueError("official BADJ importer fallback site mismatch")
    for hook in LANGUAGE_HOOKS:
        offset = hook["offset"]
        if original[offset : offset + 8] != ORIGINAL_LANGUAGE_CALL_TARGET:
            raise ValueError(f"official language hook mismatch: {hook['name']}")

    wrapper = make_wrapper()
    patched = bytearray(original)
    patched[WRAPPER_OFFSET : WRAPPER_OFFSET + len(wrapper)] = wrapper
    patched[
        IMPORT_FALLBACK_OFFSET : IMPORT_FALLBACK_OFFSET + len(SAFE_IMPORT_FAILURE)
    ] = SAFE_IMPORT_FAILURE
    for hook in LANGUAGE_HOOKS:
        offset = hook["offset"]
        patched[offset : offset + 8] = WRAPPER_LANGUAGE_CALL_TARGET

    checksum_after = common.firmware_checksum(patched)
    common.set_be32(patched, common.CHECKSUM_OFFSET, checksum_after)
    if common.be32(patched, common.CHECKSUM_OFFSET) != common.firmware_checksum(patched):
        raise AssertionError("patched firmware checksum mismatch")

    changed = [
        offset
        for offset, (before, after) in enumerate(zip(original, patched))
        if before != after
    ]
    allowed = set(range(common.CHECKSUM_OFFSET, common.CHECKSUM_OFFSET + 4))
    allowed.update(range(WRAPPER_OFFSET, WRAPPER_OFFSET + len(wrapper)))
    allowed.update(
        range(IMPORT_FALLBACK_OFFSET, IMPORT_FALLBACK_OFFSET + len(SAFE_IMPORT_FAILURE))
    )
    for hook in LANGUAGE_HOOKS:
        allowed.update(range(hook["offset"], hook["offset"] + 8))
    unexpected = [offset for offset in changed if offset not in allowed]
    if unexpected:
        raise AssertionError(f"firmware changed unexpected offsets: {unexpected}")

    fallback_branch_target = (0x20078284 & ~3) + 0x13 * 4
    if fallback_branch_target != 0x200782D0:
        raise AssertionError("safe importer failure branch target mismatch")

    return bytes(patched), {
        "source": str(SOURCE_FIRMWARE),
        "sha256_before": sha256(original),
        "sha256_after": sha256(patched),
        "checksum_before": f"0x{stored_before:08X}",
        "checksum_after": f"0x{checksum_after:08X}",
        "changed_byte_count": len(changed),
        "changed_offsets": changed,
        "wrapper": {
            "va": f"0x{WRAPPER_VA:08X}",
            "file_offset": f"0x{WRAPPER_OFFSET:X}",
            "calls": [
                f"0x{STOCK_BADJ_IMPORT_VA:08X}",
                f"0x{STOCK_LANGUAGE_INIT_VA:08X}",
            ],
        },
        "import_failure_branch": {
            "va": f"0x{IMPORT_FALLBACK_VA:08X}",
            "target": "0x200782D0",
            "effect": "return -1 instead of reading /IROM/BADJROM.DAT",
        },
        "language_hooks": LANGUAGE_HOOKS,
    }


def readme(report: dict) -> str:
    return f"""# GXR 1.51 真正地区语言解锁（本机专用、一次性）

## 这次修改的是什么

这是基于本机实际导出的 `BADJROM.DAT` 制作的专用包。调整区偏移 `0x17`
是固件代码确认的语言地区门控：

- `0`：语言菜单只建立 2 项（日语、英语）
- 非 `0`：语言菜单建立全部 11 项
- `6`：同时表示简体中文的工厂默认语言编号

本包只把该字节从 `0` 改为 `6`，并更新调整区校验。序列号、校准数据、
坏点、白平衡、对焦、计数器等内容全部来自这台机身自己的导出，未被替换。

## 操作

1. 电池充满。把 `SD_ROOT` 中全部 30 个文件复制到已格式化 SD 卡根目录。
2. 执行一次强制固件更新，期间不得断电、拔卡或拆模块。
3. 正常开机，进入语言菜单，对当前语言按一次确认。这一步才会调用原厂
   `BADJROM` 导入、校验和持久写入流程。
4. 等待界面恢复及 SD 读写灯完全停止，再等 20 秒，正常关机。
5. 重新开机并进入语言菜单。预期应显示全部 11 种语言。
6. 立即用理光官方原始 1.51 的 29 个文件恢复官方固件。
7. 恢复后再次检查：若 11 种语言仍在，才算真正地区解锁完成。

只需确认一次语言。不要在本实验固件下反复切换；完成第 5 步后就恢复官方固件。

## 静态安全边界

- `BADJROM.DAT` 来源 SHA-256：`{report['badj']['sha256_before']}`
- 修改后 `BADJROM.DAT` SHA-256：`{report['badj']['sha256_after']}`
- 只允许调整区 `0x17` 和末尾校验字段发生变化。
- 写入调用原厂 `0x20078240 -> 0x2007785C` 路径。
- SD 文件读取失败时直接返回，不再回退读取机身 `/IROM/`。
- 28 个其他官方升级文件逐字节不变；`ilaunch3` 长度不变且校验已重算。

这是代码级静态验证通过、尚未由真机验证写入结果的实验包。
"""


def main() -> None:
    official_files = sorted(path for path in OFFICIAL_DIR.iterdir() if path.is_file())
    if len(official_files) != 29:
        raise ValueError(f"expected 29 official files, found {len(official_files)}")
    if OUTPUT_ROOT.exists():
        raise FileExistsError(f"output already exists: {OUTPUT_ROOT}")

    badj, badj_report = make_badj()
    firmware, firmware_report = make_firmware()

    SD_ROOT.mkdir(parents=True)
    unchanged_hashes = {}
    for source in official_files:
        destination = SD_ROOT / source.name
        if source.name == "ilaunch3":
            destination.write_bytes(firmware)
        else:
            shutil.copyfile(source, destination)
            if sha256(destination.read_bytes()) != sha256(source.read_bytes()):
                raise AssertionError(f"copied official file changed: {source.name}")
            unchanged_hashes[source.name] = sha256(source.read_bytes())
    (SD_ROOT / "BADJROM.DAT").write_bytes(badj)

    report = {
        "status": "STATICALLY_VERIFIED_NOT_HARDWARE_TESTED",
        "purpose": "Set this body's BADJ+23 from Japan lock 0 to Simplified-Chinese/full-language value 6",
        "package": str(OUTPUT_ROOT),
        "sd_root_file_count": len(list(SD_ROOT.iterdir())),
        "modified_or_added_files": ["ilaunch3", "BADJROM.DAT"],
        "badj": badj_report,
        "firmware": firmware_report,
        "official_unchanged_files": unchanged_hashes,
        "success_criterion": "After restoring official 1.51, language menu still contains all 11 languages",
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    README.write_text(readme(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
