#!/usr/bin/env python3
"""Ricoh GXR 1.51 水水固件交互式修改器。"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Callable

import gxr_firmware_modifier as modifier


REPO_URL = "https://github.com/minakam1/ricoh-gxr-chinese-language-patch"
OUTPUT_NAMES = {
    "english": "Ricoh_GXR_1.51_水水固件_英文替换版",
    "unlock": "Ricoh_GXR_1.51_水水固件_完全解锁版",
}

GXR_ART = r"""
   GGGG   X   X  RRRR
  G        X X   R   R
  G  GGG    X    RRRR
  G    G   X X   R  R
   GGGG   X   X  R   R
"""

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
}


def styled(text: str, *styles: str) -> str:
    if not sys.stdout.isatty():
        return text
    prefix = "".join(ANSI[style] for style in styles)
    return f"{prefix}{text}{ANSI['reset']}"


def configure_windows_console() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except (AttributeError, OSError):
        pass


def choose_mode(input_fn: Callable[[str], str] = input) -> str:
    print()
    print(styled("请选择修改模式：", "bold", "yellow"))
    print(f"  {styled('1', 'bold', 'green')}. 英文替换版：选择 English 后显示简体中文")
    print(f"  {styled('2', 'bold', 'cyan')}. 完全解锁版：开放全部 11 种语言")
    while True:
        answer = input_fn("\n请输入 1 或 2：").strip()
        if answer == "1":
            return "english"
        if answer == "2":
            return "unlock"
        print(styled("输入无效，请输入 1 或 2。", "red"))


def unique_output(source: Path, mode: str) -> Path:
    parent = source.parent
    stem = OUTPUT_NAMES[mode]
    candidate = parent / f"{stem}.zip"
    number = 2
    while candidate.exists():
        candidate = parent / f"{stem}_{number}.zip"
        number += 1
    return candidate


def request_source(input_fn: Callable[[str], str] = input) -> Path:
    print(styled("请把官方 GXR 1.51 固件 ZIP 或文件夹拖到此窗口，然后按回车。", "yellow"))
    raw = input_fn("> ").strip()
    if not raw:
        raise ValueError("没有选择固件 ZIP 或文件夹")
    if sys.platform == "win32":
        raw = raw.strip('"').strip("'")
    else:
        parts = shlex.split(raw)
        if len(parts) != 1:
            raise ValueError("一次只能导入一个固件 ZIP 或文件夹")
        raw = parts[0]
    return Path(raw).expanduser()


def run(source: Path, input_fn: Callable[[str], str] = input) -> Path:
    source = source.expanduser().resolve()
    print(f"\n导入：{source}")
    print("正在检查官方 GXR 1.51 固件……")
    files = modifier.read_firmware(source)
    print(styled("检查通过：已识别全部 29 个官方升级文件。", "green"))

    mode = choose_mode(input_fn)
    patcher = modifier.patch_english if mode == "english" else modifier.patch_unlock
    print("\n正在生成……")
    patched, patches = patcher(files["ilaunch3"])
    manifest = modifier.build_manifest(mode, files, patched, patches)
    output = unique_output(source, mode)
    modifier.write_output(output, mode, files, patched, manifest)

    print(styled("\n生成完成。", "bold", "green"))
    print(styled(f"输出：{output}", "green"))
    print("\n刷写：把输出 ZIP 中 SD_ROOT 里面的 29 个文件复制到 SD 卡根目录，")
    print("使用满电电池，按住 + 和回放按钮启动更新。")
    if mode == "english":
        print("更新后进入语言设置，选择 English。")
    else:
        print("更新后进入语言菜单确认一次；出现 11 种语言后，建议恢复官方 GXR 1.51。")
    print("\n完整教程和项目仓库：")
    print(styled(REPO_URL, "cyan"))
    return output


def main(argv: list[str] | None = None, input_fn: Callable[[str], str] = input) -> int:
    configure_windows_console()
    args = sys.argv[1:] if argv is None else argv
    print(styled(GXR_ART, "bold", "cyan"))
    print("=" * 58)
    print(styled(" Ricoh GXR 1.51 水水固件修改器", "bold", "cyan"))
    print("=" * 58)
    print("把官方 GXR 1.51 ZIP 或文件夹拖到程序上，即可导入检查。")
    print("检查后输入 1 或 2，修改包会自动输出到原文件旁边。")
    print(styled("刷写前请备份照片、使用满电电池，并保留官方 GXR 1.51 恢复包。", "yellow"))
    pending_source = Path(args[0]) if args else None
    while True:
        try:
            source = pending_source if pending_source is not None else request_source(input_fn)
            pending_source = None
            run(source, input_fn)
            print("\n可以继续拖入下一个固件 ZIP 或文件夹。\n")
        except (OSError, ValueError, AssertionError) as error:
            pending_source = None
            print(styled(f"\n错误：{error}", "bold", "red"))
            print(styled("请重新拖入固件 ZIP 或文件夹。\n", "yellow"))
        except (EOFError, KeyboardInterrupt):
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
