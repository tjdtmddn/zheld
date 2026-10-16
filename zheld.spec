# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH)

a = Analysis(
    [str(project / "darcy_weisbach_gui.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[
        (str(project / "csv"), "csv"),
        (str(project / "README.md"), "."),
        (str(project / "MANUAL.md"), "."),
    ],
    hiddenimports=["matplotlib.backends.backend_tkagg", "matplotlib.backends.backend_pdf"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DarcyWeisbachAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
