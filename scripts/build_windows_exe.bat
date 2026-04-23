@echo off
setlocal EnableExtensions

for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
set "PYTHON_BIN="
set "VENV_DIR=%ROOT_DIR%\.venv-win-build"
set "ICON_SRC=%ROOT_DIR%\assets\app-icon.png"
set "ICO_PATH=%ROOT_DIR%\assets\CodexScope.ico"
set "APP_NAME=Codex-Scope"
set "APP_VERSION=%CODEX_SCOPE_VERSION%"
set "EXE_PATH=%ROOT_DIR%\dist\%APP_NAME%.exe"
set "ZIP_PATH=%ROOT_DIR%\dist\Codex-Scope-windows.zip"
set "VERSION_FILE=%TEMP%\codex_scope_version_info.txt"

if not defined APP_VERSION if exist "%ROOT_DIR%\VERSION" set /p APP_VERSION=<"%ROOT_DIR%\VERSION"
if not defined APP_VERSION set "APP_VERSION=26.4.23.1"
set "VERSION_FILE=%TEMP%\codex_scope_version_info.txt"

if defined CODEX_SCOPE_BUILD_PYTHON if exist "%CODEX_SCOPE_BUILD_PYTHON%" set "PYTHON_BIN="%CODEX_SCOPE_BUILD_PYTHON%""

if not defined PYTHON_BIN call :find_python
if not defined PYTHON_BIN (
  echo Could not find a usable Python runtime for Codex Scope.
  echo Install Python 3.11+ with Tk support, or set CODEX_SCOPE_BUILD_PYTHON.
  exit /b 1
)

if not exist "%ICON_SRC%" (
  echo Missing icon source: %ICON_SRC%
  exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
  call %PYTHON_BIN% -m venv "%VENV_DIR%" || exit /b 1
)

call "%VENV_DIR%\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyinstaller pillow || exit /b 1

call "%VENV_DIR%\Scripts\python.exe" -c "from pathlib import Path; from PIL import Image; img = Image.open(Path(r'%ICON_SRC%')).convert('RGBA'); img.save(Path(r'%ICO_PATH%'), format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])" || exit /b 1

call "%VENV_DIR%\Scripts\python.exe" -c "import os, pathlib; version = os.environ['APP_VERSION']; parts = [int(part) for part in version.split('.') if part.strip()]; parts = (parts + [0, 0, 0, 0])[:4]; nums = ', '.join(map(str, parts)); text = f'''VSVersionInfo(\n  ffi=FixedFileInfo(\n    filevers=({nums}),\n    prodvers=({nums}),\n    mask=0x3f,\n    flags=0x0,\n    OS=0x40004,\n    fileType=0x1,\n    subtype=0x0,\n    date=(0, 0)\n  ),\n  kids=[\n    StringFileInfo([\n      StringTable(\n        u\"040904B0\",\n        [\n          StringStruct(u\"CompanyName\", u\"xiaobin\"),\n          StringStruct(u\"FileDescription\", u\"Codex Scope\"),\n          StringStruct(u\"FileVersion\", u\"{version}\"),\n          StringStruct(u\"InternalName\", u\"Codex-Scope\"),\n          StringStruct(u\"OriginalFilename\", u\"Codex-Scope.exe\"),\n          StringStruct(u\"ProductName\", u\"Codex Scope\"),\n          StringStruct(u\"ProductVersion\", u\"{version}\"),\n          StringStruct(u\"LegalCopyright\", u\"xiaobin | happyyou2009@gmail.com\")\n        ]\n      )\n    ]),\n    VarFileInfo([VarStruct(u\"Translation\", [1033, 1200])])\n  ]\n)\n'''; pathlib.Path(os.environ['VERSION_FILE']).write_text(text, encoding='utf-8')" || exit /b 1

set "PYINSTALLER_CONFIG_DIR=%TEMP%\pyinstaller"
call "%VENV_DIR%\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "%APP_NAME%" ^
  --icon "%ICO_PATH%" ^
  --version-file "%VERSION_FILE%" ^
  --hidden-import codex_continue_summary ^
  --hidden-import codex_context_inspector ^
  --hidden-import codex_i18n ^
  "%ROOT_DIR%\codex_token_widget.py" || exit /b 1

if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"
powershell -NoProfile -Command "Compress-Archive -Path '%EXE_PATH%' -DestinationPath '%ZIP_PATH%' -Force" || exit /b 1

echo Built exe: %EXE_PATH%
echo Release zip: %ZIP_PATH%
echo App version: %APP_VERSION%
exit /b 0

:find_python
if defined CODEX_SCOPE_BUILD_PYTHON if exist "%CODEX_SCOPE_BUILD_PYTHON%" (
  set "PYTHON_BIN="%CODEX_SCOPE_BUILD_PYTHON%""
  goto :eof
)

py -3.13 -c "import sys" >nul 2>nul && set "PYTHON_BIN=py -3.13" && goto :eof
py -3 -c "import sys" >nul 2>nul && set "PYTHON_BIN=py -3" && goto :eof
python -c "import sys" >nul 2>nul && set "PYTHON_BIN=python" && goto :eof
python3 -c "import sys" >nul 2>nul && set "PYTHON_BIN=python3" && goto :eof
goto :eof
