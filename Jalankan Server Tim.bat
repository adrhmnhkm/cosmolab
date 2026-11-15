@echo off
setlocal
cd /d "%~dp0"
title CosmoLab - Server Tim

if not exist ".venv\Scripts\python.exe" goto :no_install
if not exist ".env" goto :no_env

set "PYX=.venv\Scripts\python.exe"

echo === CosmoLab: Server Tim (lewat Tailscale) ===
echo.
echo Tim cukup membuka alamat lobi di bawah, lalu memilih atau membuat proyek di browser.
echo Biarkan jendela ini terbuka selama tim bekerja. Tutup jendela untuk mematikan server.
echo.
"%PYX%" -m cosmolab.cli tim
goto :end

:no_install
echo CosmoLab belum dipasang. Klik dua kali "Pasang CosmoLab.bat" dulu.
goto :end

:no_env
echo File .env belum ada. Jalankan "Pasang CosmoLab.bat" dulu.
goto :end

:end
pause
