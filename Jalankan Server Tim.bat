@echo off
setlocal
cd /d "%~dp0"
title CosmoLab - Server Tim

if not exist ".venv\Scripts\python.exe" goto :no_install
if not exist ".env" goto :no_env

set "PYX=.venv\Scripts\python.exe"

echo === CosmoLab: Server Tim (lewat Tailscale) ===
echo.
"%PYX%" -m cosmolab.cli project list
echo.
set "PROYEK="
set /p "PROYEK=Proyek yang dibuka untuk tim (kosong = data utama): "
set "PORT="
set /p "PORT=Port (Enter untuk 8501; pakai 8502, 8503, dst. untuk proyek lain): "
if "%PORT%"=="" set "PORT=8501"

echo.
echo Biarkan jendela ini terbuka selama tim bekerja. Tutup jendela untuk mematikan server.
if "%PROYEK%"=="" goto :run_main
"%PYX%" -m cosmolab.cli -P "%PROYEK%" ui --team --port %PORT%
goto :end

:run_main
"%PYX%" -m cosmolab.cli ui --team --port %PORT%
goto :end

:no_install
echo CosmoLab belum dipasang. Klik dua kali "Pasang CosmoLab.bat" dulu.
goto :end

:no_env
echo File .env belum ada. Jalankan "Pasang CosmoLab.bat" dulu.
goto :end

:end
pause
