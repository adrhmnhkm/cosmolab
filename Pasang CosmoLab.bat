@echo off
setlocal
cd /d "%~dp0"
title Pasang CosmoLab

echo === Pasang CosmoLab ===
echo.

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python belum terpasang.
  echo Unduh dari https://www.python.org/downloads/ lalu centang "Add python.exe to PATH" saat memasang.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Membuat lingkungan Python khusus CosmoLab...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

echo Memasang komponen yang dibutuhkan. Ini bisa makan beberapa menit...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto :fail

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo File .env dibuat. Buka file itu dengan Notepad dan isi LLM_API_KEY, LLM_MODEL,
  echo dan COSMOLAB_EMAIL. Minta nilainya ke admin tim.
  notepad ".env"
)

echo.
echo Selesai. Jalankan CosmoLab dengan klik dua kali "Jalankan CosmoLab.bat".
pause
exit /b 0

:fail
echo.
echo Pemasangan gagal. Kirim tangkapan layar jendela ini ke admin tim.
pause
exit /b 1
