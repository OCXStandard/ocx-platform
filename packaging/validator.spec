# PyInstaller spec for the standalone ocx-validator executable.
#
# Build from the repo root:
#
#     uv run pyinstaller packaging/validator.spec --noconfirm
#
# The versioned OCX data-binding modules (ocx.ocx_310.ocx_310, ...) are
# imported dynamically at runtime by DynamicLoader, so PyInstaller cannot
# discover them statically — collect_submodules('ocx') bundles them all.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("ocx")

# When the build Python is conda-based, stdlib extension modules depend on
# DLLs living in <base>/Library/bin (ffi, lzma, ssl, ...) that PyInstaller's
# dependency walk does not find. Bundle them explicitly.
binaries = []
_conda_bin = Path(sys.base_prefix) / "Library" / "bin"
if _conda_bin.is_dir():
    for pattern in ("ffi*.dll", "liblzma*.dll", "libbz2*.dll", "libssl*.dll",
                    "libcrypto*.dll", "sqlite3*.dll", "zlib*.dll",
                    "libexpat*.dll"):
        binaries.extend((str(p), ".") for p in _conda_bin.glob(pattern))

a = Analysis(
    ["validator_entry.py"],
    pathex=[".."],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["ocx_model_validator.mcp"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ocx-validator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
