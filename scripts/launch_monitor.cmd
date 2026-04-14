@echo off
setlocal

set "ROOT_DIR=%~dp0.."
set "TARGET_SCRIPT=%ROOT_DIR%\codex_token_widget.py"

if defined CODEX_SCOPE_PYTHON (
  if exist "%CODEX_SCOPE_PYTHON%" (
    "%CODEX_SCOPE_PYTHON%" "%TARGET_SCRIPT%" %*
    goto :eof
  )
)

py -3.13 "%TARGET_SCRIPT%" %* >nul 2>nul && goto :eof
py -3 "%TARGET_SCRIPT%" %* >nul 2>nul && goto :eof
python "%TARGET_SCRIPT%" %* >nul 2>nul && goto :eof
python3 "%TARGET_SCRIPT%" %* >nul 2>nul && goto :eof

echo Could not find a usable Python runtime for Codex Scope.
echo Install Python 3.11+ with Tk support, or set CODEX_SCOPE_PYTHON.
exit /b 1
