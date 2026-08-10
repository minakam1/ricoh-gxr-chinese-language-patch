#!/usr/bin/env python3
"""打包 Windows BAT 和 macOS command 命令行版本。"""

from __future__ import annotations

import hashlib
import argparse
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_NAME = "GXR-Firmware-Modifier"


def write_sha256(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum = path.with_suffix(path.suffix + ".sha256")
    checksum.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return checksum


def make_zip(output: Path, root: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, f"{root.name}/{path.relative_to(root)}")


def build_windows() -> Path:
    package = DIST / "GXR固件修改器-Windows"
    package.mkdir(parents=True)
    shutil.copy2(ROOT / "windows" / "GXR固件修改器.bat", package)
    shutil.copy2(ROOT / "windows" / "GXR固件修改器.ps1", package)
    output = DIST / "GXR固件修改器-Windows.zip"
    make_zip(output, package)
    return output


def build_macos() -> Path:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--console",
            "--onefile",
            "--name",
            APP_NAME,
            "--distpath",
            str(DIST),
            "--workpath",
            str(ROOT / "build"),
            "--specpath",
            str(ROOT / "build"),
            str(ROOT / "gxr_modifier_cli.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    machine = platform.machine().lower() or "unknown"
    package = DIST / f"GXR固件修改器-macOS-{machine}"
    package.mkdir(parents=True)
    shutil.move(str(DIST / APP_NAME), package / APP_NAME)
    launcher = package / "运行_GXR固件修改器.command"
    launcher.write_text(
        "#!/bin/zsh\n"
        "launcher_dir=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
        "\"$launcher_dir/GXR-Firmware-Modifier\" \"$@\"\n"
        "exit $?\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    output = DIST / f"GXR固件修改器-macOS-{machine}.zip"
    make_zip(output, package)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("auto", "windows", "macos", "all"), default="auto")
    args = parser.parse_args(argv)
    for target in (ROOT / "build", DIST):
        if target.exists():
            shutil.rmtree(target)
    DIST.mkdir()

    target = args.target
    if target == "auto":
        target = "windows" if sys.platform == "win32" else "all" if sys.platform == "darwin" else ""
    if target in ("macos", "all") and sys.platform != "darwin":
        raise RuntimeError("macOS 程序必须在 macOS 上打包")
    if not target:
        raise RuntimeError("打包脚本只支持 Windows 和 macOS")

    outputs = []
    if target in ("windows", "all"):
        outputs.append(build_windows())
    if target in ("macos", "all"):
        outputs.append(build_macos())
    for output in outputs:
        checksum = write_sha256(output)
        print(f"分发包：{output}")
        print(f"SHA-256：{checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
