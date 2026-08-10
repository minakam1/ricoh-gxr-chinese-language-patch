#!/usr/bin/env python3
"""在本地把用户提供的官方 Ricoh GXR 1.51 固件制作成语言修改包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


HEADER_SIZE = 0x200
CHECKSUM_OFFSET = 0x16C

OFFICIAL_SHA256 = {
    "ilaunch0": "b896f40d9f330c4235d99bd6e32963876f9701293530a927672fd6fab7281e65",
    "ilaunch3": "da1980e9d6f3996ede4953b8311cf0ce2abeb4bb300b6ee60a38f38e29a3cdf7",
    "ilaunch4": "c9271288f8d395296623a3fe5358b2d83dec8730a89ed138a48ff8a2e8f14a5a",
    "ilaunch8": "071d207858c5863f72fda37274372ab881d86f6ecd2b1a826ad825f90047e478",
    "jlaunch0": "0606a54c673e6db2b7708598f4ad7f1bebb93ade534087b1d0e28f7aff8e2de9",
    "jlaunch3": "951be1c659c85af58ae3e4ce98707c52f0b4514fc2075256854d59f822671673",
    "jlaunch4": "377e980401d98ba303246f00b4633468ef5affa54ffbc22d24659cc4b1c5e8ca",
    "jlaunch8": "92554edf413e0090550f192973d0555ee13770cee0764802be209f491f2c424f",
    "klaunch0": "4b8c1fd4c24cc7112d49290e94f8d9d75523df395aec7c8fff7ad6ac881b0bf6",
    "klaunch3": "491f39a619e7d85eeb28ba5c55494ccaa274872b63b2a98169ee14e8f4757bee",
    "klaunch4": "2dd87ee852b4cea2aff881da9903871a57910da71b27402b1dd29c8dc77fdfe2",
    "klaunch8": "8fc3ff589088b90a8922a200a077aa3f9daed1dbb5d37992c0642c0b63f69f1a",
    "l06firm0": "d7b74b86ec829e90dd4b5c1092abc892b90422fd975942f3d4a6b99ea24e24ef",
    "l06firm3": "6538b919848ee979c3e92ac14a19a29fb8439a1297147c7e0e601afcd135ae8d",
    "l06firm4": "c0aa8256c682a41ad96277eea075e2c58dca5335dc9bc824e09e78fe69ab10d0",
    "l06firm5": "1ddd60028a33aa021169014f07abe263099404522097ad3a267d3fe0387a9c69",
    "l06firm8": "61aae4cfb39ee599eb9647fb72da7b4fd186edcbda298dcb6551fe1fd78d718d",
    "l08firm0": "05cc3f648f84dc1123dc8207a0edbd796a70bec9a01c36fa43199a5959b78e9f",
    "l08firm3": "0a4dff6d3be9b9a9b56dfcbd98a2df59efcb31f7d4eaca6b0c3fbdb1641fde44",
    "l08firm4": "0f787a6fa51893d98bcc778c9e91b2a46ce4fef139828332f418142aa4f36060",
    "l08firm8": "59a75b3ea1cb7dc71d79349e20d49e809eb1678731111678a7b0ef4c8df0db4d",
    "nlaunch0": "480c5b195c983100a80ca3e3128cd2a0686de0f7b482c025ec23db3f8a78f527",
    "nlaunch3": "f96c5b84b8fb442706dd694828f51bea4f5f38ea11a7c6881d050d479df9aabf",
    "nlaunch4": "f2bbc71463d9272adc0da8801bc2997a2c147b0ce33c10aaeac01a506e4c678d",
    "nlaunch8": "52921ca9311de0f093d5dea1531e2c83876f2bf91d7032cf45f60a50328b26be",
    "qlaunch0": "3bbc37c6c12c6fedaa190927cdc0594d059919cffee29309ef211122734c6dc5",
    "qlaunch3": "e487d00b5539aa1e3ca9373829456e00676b37310dc717f0a5bcb5235bac6690",
    "qlaunch4": "eb2533fdb26ee61cc2135c40fa73a2d6f618bd6f1872f594b256ce4b586aa90b",
    "qlaunch8": "9d81ca7c1e33df4cd9f0c5532b22ad55b1c11a492707839705ab4e69f9019e45",
}

ENGLISH_EXPECTED_SHA256 = "e543f5866bbc99ad4697c6dddb931c5a0fa0526fed34c421541ae32fb7f0c785"
UNLOCK_EXPECTED_SHA256 = "1a383ab94db6bcc4b00583ca3d61339b7f39917aeaf8ec3be9c8809b222c9439"


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def be32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def set_be32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into(">I", data, offset, value)


def firmware_checksum(data: bytes | bytearray) -> int:
    if len(data) < HEADER_SIZE:
        raise ValueError("ilaunch3 文件过短")
    if be32(data, 0x164) != len(data) - HEADER_SIZE:
        raise ValueError("ilaunch3 头部记录的载荷长度不匹配")
    return sum(
        byte * ((index % 6) + 2)
        for index, byte in enumerate(data[HEADER_SIZE:])
    ) & 0xFFFFFFFF


def replace_exact(
    data: bytearray,
    offset: int,
    expected: bytes,
    replacement: bytes,
    name: str,
) -> range:
    if len(expected) != len(replacement):
        raise AssertionError(f"{name} 补丁长度发生变化")
    actual = bytes(data[offset : offset + len(expected)])
    if actual != expected:
        raise ValueError(f"ilaunch3 的 {name} 补丁位置与官方 1.51 不匹配")
    data[offset : offset + len(replacement)] = replacement
    return range(offset, offset + len(replacement))


def encode_bl(pc: int, target: int) -> bytes:
    delta = target - (pc & ~3)
    if delta % 4:
        raise ValueError("BL 目标未按 4 字节对齐")
    displacement = delta // 4
    if not -(1 << 23) <= displacement < (1 << 23):
        raise ValueError("BL 目标超出范围")
    return b"\xFE" + (displacement & 0xFFFFFF).to_bytes(3, "big")


ENGLISH_BOOT_ORIGINAL = bytes.fromhex(
    "d0 c0 20 0c 80 e0 0d 9c 20 c0 f0 00 a0 90 00 17"
)
ENGLISH_BOOT_REPLACEMENT = bytes.fromhex(
    "61 01 f0 00 b0 11 00 03 60 06 f0 00 80 e0 00 00"
)
ENGLISH_SYNC_BRANCH_ORIGINAL = bytes.fromhex("7f 02")
ENGLISH_SYNC_BRANCH_REPLACEMENT = bytes.fromhex("7f 04")
ENGLISH_SYNC_ORIGINAL = bytes.fromhex(
    "a2 91 00 17 d0 c0 20 0c 80 e0 0d ac 21 c0 f0 00 a2 01 03 97"
)
ENGLISH_SYNC_REPLACEMENT = bytes.fromhex(
    "12 80 61 01 b2 11 00 02 62 06 f0 00 a2 03 03 97 80 e0 00 00"
)
LANGUAGE_INIT_ORIGINAL = bytes.fromhex(
    "28 7f 2e 7f 18 84 f0 00 "
    "d0 c0 20 1d 80 e0 1e fc 14 88 1e c0 "
    "d0 c0 20 1d 80 e0 4f 24 14 88 1e c0 "
    "d0 c0 20 1d 80 e0 83 ec 14 88 1e c0"
)


def english_language_init() -> bytes:
    return (
        bytes.fromhex(
            "28 7f 2e 7f 18 84 60 01 b8 10 00 02 68 06 14 88"
        )
        + encode_bl(0x201C0F60, 0x201D1EFC)
        + bytes.fromhex("14 88 f0 00")
        + encode_bl(0x201C0F68, 0x201D4F24)
        + bytes.fromhex("80 e0 00 00 14 88 f0 00")
        + encode_bl(0x201C0F74, 0x201D83EC)
        + bytes.fromhex("80 e0 00 00")
    )


def patch_english(original: bytes) -> tuple[bytes, list[dict[str, object]]]:
    patched = bytearray(original)
    patches = [
        (0x1C348, ENGLISH_BOOT_ORIGINAL, ENGLISH_BOOT_REPLACEMENT, "开机语言配置映射"),
        (0x1C774, ENGLISH_SYNC_BRANCH_ORIGINAL, ENGLISH_SYNC_BRANCH_REPLACEMENT, "语言同步分支"),
        (0x1C778, ENGLISH_SYNC_ORIGINAL, ENGLISH_SYNC_REPLACEMENT, "运行时语言同步"),
        (0x176150, LANGUAGE_INIT_ORIGINAL, english_language_init(), "统一语言初始化"),
    ]
    report = []
    for offset, expected, replacement, name in patches:
        replace_exact(patched, offset, expected, replacement, name)
        report.append({"name": name, "offset": f"0x{offset:X}", "length": len(replacement)})
    return finish_patch(original, patched, ENGLISH_EXPECTED_SHA256), report


UNLOCK_WRAPPER_ORIGINAL = bytes.fromhex(
    "4f ec 28 7f 29 7f 2e 7f d0 c0 20 0c 85 e0 a4 d3 "
    "d0 c0 20 0b 84 af 00 0c 80 e0 bd 04 66 12 1e c0 "
    "d0 c0 20 0c 80 e0 0d 9c 24 c0 f0 00"
)
LANGUAGE_CALL_ORIGINAL = bytes.fromhex("d0 c0 20 1c 80 e0 0f 50")
LANGUAGE_CALL_UNLOCK = bytes.fromhex("d0 c0 20 07 80 e0 7f c8")


def unlock_wrapper() -> bytes:
    return (
        bytes.fromhex(
            "28 7f 2e 7f 18 84 f0 00 "
            "d1 c0 20 0c 81 e1 0d 9c 21 c1 60 06 a0 01 00 17"
        )
        + encode_bl(0x20077FE0, 0x2007785C)
        + bytes.fromhex("14 88 f0 00")
        + encode_bl(0x20077FE8, 0x201C0F50)
        + bytes.fromhex("2e ef 28 ef 1f ce f0 00")
    )


def patch_unlock(original: bytes) -> tuple[bytes, list[dict[str, object]]]:
    patched = bytearray(original)
    patches = [
        (0x2D1C8, UNLOCK_WRAPPER_ORIGINAL, unlock_wrapper(), "当前机身地区字段持久化"),
        (0x30FDC8, LANGUAGE_CALL_ORIGINAL, LANGUAGE_CALL_UNLOCK, "普通语言确认入口"),
        (0x327140, LANGUAGE_CALL_ORIGINAL, LANGUAGE_CALL_UNLOCK, "备用语言确认入口"),
    ]
    report = []
    for offset, expected, replacement, name in patches:
        replace_exact(patched, offset, expected, replacement, name)
        report.append({"name": name, "offset": f"0x{offset:X}", "length": len(replacement)})
    return finish_patch(original, patched, UNLOCK_EXPECTED_SHA256), report


def finish_patch(original: bytes, patched: bytearray, expected_sha256: str) -> bytes:
    stored = be32(original, CHECKSUM_OFFSET)
    calculated = firmware_checksum(original)
    if stored != calculated:
        raise ValueError("官方 ilaunch3 的内部校验不匹配")
    set_be32(patched, CHECKSUM_OFFSET, firmware_checksum(patched))
    if be32(patched, CHECKSUM_OFFSET) != firmware_checksum(patched):
        raise AssertionError("修改后 ilaunch3 的内部校验失败")
    result = bytes(patched)
    if sha256(result) != expected_sha256:
        raise AssertionError("修改结果与已验证构建不一致")
    return result


def find_firmware_directory(root: Path) -> Path:
    names = set(OFFICIAL_SHA256)
    candidates = []
    possible = [root] if root.is_dir() else []
    if root.is_dir():
        possible.extend(path.parent for path in root.rglob("ilaunch3"))
    for directory in possible:
        if directory in candidates:
            continue
        if all((directory / name).is_file() for name in names):
            candidates.append(directory)
    if len(candidates) != 1:
        raise ValueError(f"需要且只能找到一套完整的 29 文件官方固件，实际找到 {len(candidates)} 套")
    return candidates[0]


def read_firmware(source: Path) -> dict[str, bytes]:
    if source.is_dir():
        directory = find_firmware_directory(source)
        files = {name: (directory / name).read_bytes() for name in OFFICIAL_SHA256}
    elif source.is_file() and zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            groups: dict[str, dict[str, zipfile.ZipInfo]] = {}
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if not info.is_dir() and path.name in OFFICIAL_SHA256:
                    groups.setdefault(str(path.parent), {})[path.name] = info
            matches = [group for group in groups.values() if set(group) == set(OFFICIAL_SHA256)]
            if len(matches) != 1:
                raise ValueError(f"ZIP 中需要且只能找到一套完整的 29 文件官方固件，实际找到 {len(matches)} 套")
            files = {name: archive.read(matches[0][name]) for name in OFFICIAL_SHA256}
    else:
        raise ValueError("输入必须是官方固件解压目录或 ZIP 文件")

    mismatches = [
        name for name, expected in OFFICIAL_SHA256.items()
        if sha256(files[name]) != expected
    ]
    if mismatches:
        raise ValueError("输入不是已知的官方 GXR 1.51 固件，校验失败：" + ", ".join(mismatches))
    return files


def make_readme(mode: str) -> str:
    if mode == "english":
        title = "Ricoh GXR 1.51 水水固件：英文替换版"
        steps = """1. 解压 ZIP。
2. 把 `SD_ROOT` 里面的 29 个文件复制到相机格式化的 SD 卡根目录。
3. 使用满电电池，关机后按住 `+`，同时按住回放按钮 2–3 秒。
4. 用 Fn2 选择“是”，按 MENU/OK，等待更新完成并自动重启。
5. 进入语言设置，选择 `English`。"""
    else:
        title = "Ricoh GXR 1.51 水水固件：完全解锁版"
        steps = """1. 解压 ZIP。
2. 把 `SD_ROOT` 里面的 29 个文件复制到相机格式化的 SD 卡根目录。
3. 使用满电电池，关机后按住 `+`，同时按住回放按钮 2–3 秒。
4. 用 Fn2 选择“是”，按 MENU/OK，等待更新完成并自动重启。
5. 进入语言菜单，对当前语言确认一次；等待读写结束后正常关机。
6. 重新开机，确认出现全部 11 种语言。
7. 建议随后用官方 GXR 1.51 的 29 个文件恢复官方固件。"""
    return f"""# {title}

项目仓库：<https://github.com/minakam1/ricoh-gxr-chinese-language-patch>

## 操作

{steps}

更新过程中不得断电、拔卡或拆卸相机模块。刷写前备份照片并保留官方恢复包。
"""


def build_manifest(
    mode: str,
    files: dict[str, bytes],
    patched: bytes,
    patches: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "tool": "GXR Firmware Modifier",
        "mode": mode,
        "target": "Ricoh GXR firmware 1.51",
        "input_verified": True,
        "file_count": 29,
        "modified_files": ["ilaunch3"],
        "ilaunch3_sha256_before": sha256(files["ilaunch3"]),
        "ilaunch3_sha256_after": sha256(patched),
        "ilaunch3_checksum_after": f"0x{be32(patched, CHECKSUM_OFFSET):08X}",
        "patches": patches,
    }


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def write_output(
    output: Path,
    mode: str,
    files: dict[str, bytes],
    patched: bytes,
    manifest: dict[str, object],
) -> None:
    if output.exists():
        raise FileExistsError(f"输出已存在，为避免覆盖已停止：{output}")
    payloads = dict(files)
    payloads["ilaunch3"] = patched
    readme = make_readme(mode).encode("utf-8")
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    if output.suffix.lower() == ".zip":
        root = (
            "Ricoh_GXR_1.51_水水固件_英文替换版"
            if mode == "english"
            else "Ricoh_GXR_1.51_水水固件_完全解锁版"
        )
        with zipfile.ZipFile(output, "x", compresslevel=9) as archive:
            archive.writestr(zip_info(f"{root}/README.md"), readme)
            archive.writestr(zip_info(f"{root}/manifest.json"), manifest_data)
            for name in sorted(payloads):
                archive.writestr(zip_info(f"{root}/SD_ROOT/{name}"), payloads[name])
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None:
                raise AssertionError("输出 ZIP 完整性检查失败")
    else:
        sd_root = output / "SD_ROOT"
        sd_root.mkdir(parents=True)
        (output / "README.md").write_bytes(readme)
        (output / "manifest.json").write_bytes(manifest_data)
        for name, data in payloads.items():
            (sd_root / name).write_bytes(data)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用用户自己的官方 GXR 1.51 固件，在本地生成语言修改包。"
    )
    parser.add_argument("input", type=Path, help="官方固件 ZIP 或解压目录")
    parser.add_argument("--mode", choices=("english", "unlock"), required=True,
                        help="english=英文入口改中文；unlock=一次性开放 11 种语言")
    parser.add_argument("--output", type=Path,
                        help="输出目录；以 .zip 结尾则直接生成 ZIP")
    parser.add_argument("--verify-only", action="store_true",
                        help="只校验输入和补丁位置，不写出任何文件")
    args = parser.parse_args(argv)
    if not args.verify_only and args.output is None:
        parser.error("生成修改包时必须提供 --output；只检查可使用 --verify-only")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    patcher: Callable[[bytes], tuple[bytes, list[dict[str, object]]]] = (
        patch_english if args.mode == "english" else patch_unlock
    )
    try:
        files = read_firmware(args.input.expanduser().resolve())
        patched, patches = patcher(files["ilaunch3"])
        manifest = build_manifest(args.mode, files, patched, patches)
        if not args.verify_only:
            write_output(args.output.expanduser().resolve(), args.mode, files, patched, manifest)
    except (OSError, ValueError, AssertionError, zipfile.BadZipFile) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    print("完成：官方 GXR 1.51 固件校验通过")
    print(f"模式：{args.mode}")
    if args.verify_only:
        print("只读检查：通过，未写出任何文件")
    else:
        print(f"输出：{args.output.expanduser().resolve()}")
    print(f"修改后 ilaunch3 SHA-256：{manifest['ilaunch3_sha256_after']}")
    print("修改文件：ilaunch3；其余 28 个文件保持官方原样")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
