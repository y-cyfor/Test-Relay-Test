@echo off
chcp 65001 >nul
echo ========================================
echo API Mock Server 打包脚本
echo ========================================
echo.

echo [1/2] 安装依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo 依赖安装失败！
    pause
    exit /b 1
)
echo 依赖安装完成。
echo.

echo [2/2] 打包为 exe (v4.0)...
pyinstaller --onefile --name "API-Mock-Server" ^
    --hidden-import fastapi ^
    --hidden-import uvicorn ^
    --hidden-import nicegui ^
    --hidden-import urllib ^
    --clean main.py

if %errorlevel% neq 0 (
    echo 打包失败！
    pause
    exit /b 1
)
echo 打包完成。
echo.

echo ========================================
echo 打包成功！可执行文件: dist\API-Mock-Server.exe
echo ========================================
pause
