@echo off
setlocal
chcp 65001 >nul
title Ricoh GXR 1.51 水水固件修改器
set "GXR_SCRIPT=%~dp0gxr_modifier.ps1"

if not exist "%GXR_SCRIPT%" (
    echo.
    echo [错误] 找不到 gxr_modifier.ps1
    echo 请先完整解压 ZIP，并保持 BAT 和 PS1 在同一文件夹。
    echo.
    pause
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%GXR_SCRIPT%" -Source "%~1"
set "GXR_EXIT=%ERRORLEVEL%"

if not "%GXR_EXIT%"=="0" (
    echo.
    echo [错误] 修改器异常退出，错误代码：%GXR_EXIT%
    echo 请保留上面的错误信息，不要直接关闭窗口。
    echo.
    pause
)

endlocal
exit /b %GXR_EXIT%
