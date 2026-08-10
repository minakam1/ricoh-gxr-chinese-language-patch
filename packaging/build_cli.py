#!/usr/bin/env python3
"""打包 Windows BAT 和 macOS command 命令行版本。"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_NAME = "GXR-Firmware-Modifier"
REPO_URL = "https://github.com/minakam1/ricoh-gxr-chinese-language-patch"
ZIP_COMMENT = (
    "Ricoh GXR 1.51 水水固件修改器｜本地生成语言修改固件\n"
    f"仓库：{REPO_URL}"
).encode("utf-8")


def write_sha256(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum = path.with_suffix(path.suffix + ".sha256")
    checksum.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return checksum


def add_manual(package: Path) -> None:
    shutil.copy2(ROOT / "修改器使用说明.md", package / "使用说明.md")


def make_zip(output: Path, root: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.comment = ZIP_COMMENT
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, f"{root.name}/{path.relative_to(root)}")


def build_windows() -> Path:
    package = DIST / "GXR固件修改器-Windows"
    package.mkdir(parents=True)
    launcher = (ROOT / "windows" / "GXR固件修改器.bat").read_text(encoding="utf-8")
    (package / "GXR固件修改器.bat").write_text(launcher, encoding="utf-8", newline="\r\n")
    script = (ROOT / "windows" / "GXR固件修改器.ps1").read_text(encoding="utf-8")
    (package / "gxr_modifier.ps1").write_text(script, encoding="utf-8-sig", newline="\r\n")
    add_manual(package)
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
    add_manual(package)
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
