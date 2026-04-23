@echo off
setlocal EnableExtensions

pushd "%~dp0.." || exit /b 1

if defined CODEX_SCOPE_BUILD_PYTHON if exist "%CODEX_SCOPE_BUILD_PYTHON%" (
  call "%CODEX_SCOPE_BUILD_PYTHON%" "scripts\build_windows_exe.py"
  set "EXIT_CODE=%ERRORLEVEL%"
  popd
  exit /b %EXIT_CODE%
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  call python "scripts\build_windows_exe.py"
  set "EXIT_CODE=%ERRORLEVEL%"
  popd
  exit /b %EXIT_CODE%
)

py -3 "scripts\build_windows_exe.py"
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
