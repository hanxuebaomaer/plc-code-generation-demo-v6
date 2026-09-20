@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo Industrial Code Workspace Demo v8
echo.
py -3.12 -c "import struct; assert struct.calcsize('P') == 8" >nul 2>nul
if errorlevel 1 (
    echo [错误] 请先安装 Python 3.12 64位和 Python Launcher。
    pause
    exit /b 1
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" >nul 2>nul
    if errorlevel 1 (
        echo [错误] 当前 .venv 不是 Python 3.12 64位。请将该环境另存后再运行；不会自动删除。
        pause
        exit /b 1
    )
) else (
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
if not defined PORT set "PORT=8000"
echo 浏览器访问 http://127.0.0.1:%PORT%
echo 首次运行请在 .env 中配置服务器模型参数。没有配置时只能使用有限的离线示例。
echo 请保持本窗口开启，Ctrl+C 停止服务。
start "" /b ".venv\Scripts\python.exe" open_browser.py %PORT%
".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port %PORT%
pause
exit /b 0
:failed
echo 环境准备未完成，请查看上方提示。
pause
exit /b 1
