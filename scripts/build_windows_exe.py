from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


APP_NAME = "Codex-Scope"
DEFAULT_VERSION = "26.4.23.1"
COMPANY_NAME = "xiaobin"
COPYRIGHT = "xiaobin | happyyou2009@gmail.com"


def main() -> int:
    root_dir = Path(__file__).resolve().parents[1]
    version = resolve_version(root_dir)
    venv_dir = root_dir / ".venv-win-build"
    venv_python = venv_dir / "Scripts" / "python.exe"
    icon_src = root_dir / "assets" / "app-icon.png"
    ico_path = root_dir / "assets" / "CodexScope.ico"
    exe_path = root_dir / "dist" / f"{APP_NAME}.exe"
    zip_path = root_dir / "dist" / "Codex-Scope-windows.zip"
    version_file = Path(tempfile.gettempdir()) / "codex_scope_version_info.txt"

    if not icon_src.exists():
        raise FileNotFoundError(f"Missing icon source: {icon_src}")

    if not venv_python.exists():
        run([sys.executable, "-m", "venv", str(venv_dir)], cwd=root_dir)

    run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-q",
            "pyinstaller",
            "pillow",
        ],
        cwd=root_dir,
    )

    generate_ico(venv_python, icon_src, ico_path, root_dir)
    write_version_file(version_file, version)

    pyinstaller_env = os.environ.copy()
    pyinstaller_env["PYINSTALLER_CONFIG_DIR"] = str(Path(tempfile.gettempdir()) / "pyinstaller")

    run(
        [
            str(venv_python),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            APP_NAME,
            "--icon",
            str(ico_path),
            "--version-file",
            str(version_file),
            "--hidden-import",
            "codex_continue_summary",
            "--hidden-import",
            "codex_context_inspector",
            "--hidden-import",
            "codex_i18n",
            str(root_dir / "codex_token_widget.py"),
        ],
        cwd=root_dir,
        env=pyinstaller_env,
    )

    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe_path, exe_path.name)

    print(f"Built exe: {exe_path}")
    print(f"Release zip: {zip_path}")
    print(f"App version: {version}")
    return 0


def resolve_version(root_dir: Path) -> str:
    version = os.environ.get("CODEX_SCOPE_VERSION", "").strip()
    if version:
        return version

    version_path = root_dir / "VERSION"
    if version_path.exists():
        text = version_path.read_text(encoding="utf-8").strip()
        if text:
            return text

    return DEFAULT_VERSION


def generate_ico(venv_python: Path, icon_src: Path, ico_path: Path, cwd: Path) -> None:
    code = (
        "from pathlib import Path; "
        "from PIL import Image; "
        "img = Image.open(Path(r'%s')).convert('RGBA'); "
        "img.save(Path(r'%s'), format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
        % (icon_src, ico_path)
    )
    run([str(venv_python), "-c", code], cwd=cwd)


def write_version_file(version_file: Path, version: str) -> None:
    parts = [int(part) for part in version.split(".") if part.strip()]
    parts = (parts + [0, 0, 0, 0])[:4]
    nums = ", ".join(map(str, parts))
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({nums}),
    prodvers=({nums}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u"040904B0",
        [
          StringStruct(u"CompanyName", u"{COMPANY_NAME}"),
          StringStruct(u"FileDescription", u"Codex Scope"),
          StringStruct(u"FileVersion", u"{version}"),
          StringStruct(u"InternalName", u"{APP_NAME}"),
          StringStruct(u"OriginalFilename", u"{APP_NAME}.exe"),
          StringStruct(u"ProductName", u"Codex Scope"),
          StringStruct(u"ProductVersion", u"{version}"),
          StringStruct(u"LegalCopyright", u"{COPYRIGHT}")
        ]
      )
    ]),
    VarFileInfo([VarStruct(u"Translation", [1033, 1200])])
  ]
)
"""
    version_file.write_text(text, encoding="utf-8")


def run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=cwd, env=env, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
