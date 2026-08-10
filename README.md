# Ricoh GXR 1.51 水水固件修改器

项目仓库：<https://github.com/minakam1/ricoh-gxr-chinese-language-patch>

## 下载

从 [最新 Release](https://github.com/minakam1/ricoh-gxr-chinese-language-patch/releases/latest)
下载修改器：

- Windows：`GXR固件修改器-Windows.zip`
- Apple 芯片 Mac：`GXR固件修改器-macOS-arm64.zip`

修改器会在本地检查用户选择的官方 GXR 1.51 固件，并在原文件旁边生成修改包。

## Windows

1. 解压 `GXR固件修改器-Windows.zip`。
2. 保持 `.bat` 和 `.ps1` 在同一个文件夹。
3. 把官方 GXR 1.51 固件 ZIP 或文件夹拖到 `GXR固件修改器.bat` 上。
4. 程序自动检查固件。
5. 输入 `1` 生成英文替换版，输入 `2` 生成完全解锁版。
6. 修改包会自动输出到原固件旁边。
7. 文件不对时程序不会关闭，重新拖入下一个文件即可。

Windows 使用系统自带的 PowerShell，不需要安装 Python，也不需要 EXE。

## macOS

1. 解压 `GXR固件修改器-macOS-*.zip`。
2. 把官方固件 ZIP 或文件夹拖到 `运行_GXR固件修改器.command` 上。
3. 输入 `1` 或 `2`。
4. 修改包会自动输出到原固件旁边。
5. 文件不对时程序会继续等待下一个文件。

## 输出名称

```text
Ricoh_GXR_1.51_水水固件_英文替换版.zip
Ricoh_GXR_1.51_水水固件_完全解锁版.zip
```

如果同名文件已经存在，会自动使用 `_2`、`_3` 等新名称。

## 刷写

1. 解压生成的修改包。
2. 把 `SD_ROOT` 里面的 29 个文件复制到相机格式化的 SD 卡根目录。
3. 使用满电电池，关机后按住 `+`，同时按住回放按钮 2–3 秒。
4. 用 Fn2 选择“是”，按 MENU/OK，等待更新完成并自动重启。
5. 英文替换版进入语言设置并选择 `English`。
6. 完全解锁版进入语言菜单确认一次；出现 11 种语言后，建议恢复官方 GXR 1.51。

刷写前请备份照片并保留官方 GXR 1.51 恢复包。更新过程中不要断电、拔卡或拆卸
相机模块。

本项目是非官方工具，与 Ricoh 无关。固件修改和刷写存在设备损坏风险，请自行承担。

源码入口：`gxr_modifier_cli.py`。打包说明见 [命令行打包说明](命令行打包说明.md)。
