@echo off
chcp 65001 >nul
title Ricoh GXR 1.51 水水固件修改器
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GXR固件修改器.ps1" -Source "%~1"
