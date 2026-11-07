@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Outfit

if not exist ".venv\Scripts\python.exe" goto setup
if not exist "outfit\web\static\index.html" goto nobuild
goto run

:setup
echo 第一次运行，正在创建环境并安装依赖，大约 2-3 分钟……
python -m venv .venv
if errorlevel 1 goto nopython
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if not exist ".venv\Scripts\python.exe" goto nopython
goto run

:nopython
echo.
echo 没找到 python。请先装 Python 3.10 或更新版本，安装时勾上 Add to PATH。
pause
exit /b 1

:nobuild
echo.
echo 前端还没构建。在 web 目录里跑一次 npm install 和 npm run build。
pause
exit /b 1

:run
".venv\Scripts\python.exe" -m outfit
echo.
echo 服务已停止，退出码 %errorlevel%。
pause
