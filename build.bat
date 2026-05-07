@echo off
chcp 65001 >nul 2>&1
echo ═══════════════════════════════════════════
echo   Spiderette Strategy Lab — 打包工具
echo ═══════════════════════════════════════════
echo.

:: 检查 PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [安装] PyInstaller...
    pip install pyinstaller
)

:: 清理旧构建
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

:: 打包（单文件模式）
echo [打包] 开始构建（单文件模式）...
pyinstaller spiderette.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

:: 完成
echo.
echo ═══════════════════════════════════════════
echo   打包完成！
echo   产物: dist\SpideretteStrategyLab_v*.exe（单文件，含版本号）
echo.
echo   运行后产生的数据存储在 exe 同级的 spiderette_data\ 目录
echo   可通过界面导出所需数据
echo ═══════════════════════════════════════════
echo.
pause
