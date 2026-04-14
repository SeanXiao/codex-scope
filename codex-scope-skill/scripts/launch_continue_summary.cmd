@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "TARGET_SCRIPT=%SCRIPT_DIR%codex_continue_summary.py"

if defined CODEX_SCOPE_PYTHON if exist "%CODEX_SCOPE_PYTHON%" (
  set "PYTHON_BIN=%CODEX_SCOPE_PYTHON%"
  goto run
)

if exist "%SCRIPT_DIR%..\..\.venv\Scripts\python.exe" (
  set "PYTHON_BIN=%SCRIPT_DIR%..\..\.venv\Scripts\python.exe"
  goto run
)

if exist "%SCRIPT_DIR%..\Scripts\python.exe" (
  set "PYTHON_BIN=%SCRIPT_DIR%..\Scripts\python.exe"
  goto run
)

where python >nul 2>nul && (
  for /f "delims=" %%I in ('where python') do (
    set "PYTHON_BIN=%%I"
    goto run
  )
)

echo Could not find a usable Python runtime for Codex Scope.
echo Install Python 3.11+ with Tk support, or set CODEX_SCOPE_PYTHON.
exit /b 1

:run
"%PYTHON_BIN%" "%TARGET_SCRIPT%" %*
