@echo off
setlocal EnableExtensions

if defined CODEX_SCOPE_BUILD_PYTHON if exist "%CODEX_SCOPE_BUILD_PYTHON%" (
  call "%CODEX_SCOPE_BUILD_PYTHON%" "%~dp0build_windows_exe.py"
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  call python "%~dp0build_windows_exe.py"
  exit /b %ERRORLEVEL%
)

py -3 "%~dp0build_windows_exe.py"
exit /b %ERRORLEVEL%
