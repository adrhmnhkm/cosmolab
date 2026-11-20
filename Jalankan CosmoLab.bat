@echo off
setlocal
cd /d "%~dp0"
title CosmoLab

if not exist ".venv\Scripts\python.exe" goto :no_install
if not exist ".env" goto :no_env

set "PYX=.venv\Scripts\python.exe"

echo === CosmoLab ===
echo.
"%PYX%" -m cosmolab.cli project list
echo.
echo Ketik nama proyek klien yang mau dibuka.
echo Cukup tekan Enter untuk langsung membuka dashboard di browser.
echo (Membuat atau mengelola proyek klien kini bisa langsung dilakukan di dalam web).
set "PROYEK="
set /p "PROYEK=Proyek [tekan Enter untuk langsung buka]: "

if /i "%PROYEK%"=="baru" goto :new_project
goto :launch

:new_project
set "NAMA="
set "KLIEN="
set /p "NAMA=Nama proyek, contoh 2026-11-klien-a: "
set /p "KLIEN=Nama klien: "
"%PYX%" -m cosmolab.cli project new "%NAMA%" --client "%KLIEN%"
if errorlevel 1 goto :end
set "PROYEK=%NAMA%"

:launch
echo.
echo Membuka dashboard di browser. Tutup jendela ini untuk mematikan CosmoLab.
if "%PROYEK%"=="" goto :launch_main
"%PYX%" -m cosmolab.cli -P "%PROYEK%" ui
goto :end

:launch_main
"%PYX%" -m cosmolab.cli ui
goto :end

:no_install
echo CosmoLab belum dipasang. Klik dua kali "Pasang CosmoLab.bat" dulu.
goto :end

:no_env
echo File .env belum ada. Jalankan "Pasang CosmoLab.bat" dulu.
goto :end

:end
pause
