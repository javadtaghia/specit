# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SPECiT standalone desktop releases (Windows .exe & macOS .app/.dmg)."""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from engine.version import APP_NAME, APP_VERSION  # noqa: E402

IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform.startswith('win')

icon_file = None
if IS_MAC and (ROOT / 'packaging' / 'icons' / 'specit.icns').exists():
    icon_file = str(ROOT / 'packaging' / 'icons' / 'specit.icns')
elif IS_WIN and (ROOT / 'packaging' / 'icons' / 'specit.ico').exists():
    icon_file = str(ROOT / 'packaging' / 'icons' / 'specit.ico')

datas = [
    (str(ROOT / 'web'), 'web'),
    (str(ROOT / 'prompts'), 'prompts'),
    (str(ROOT / 'examples'), 'examples'),
]

hiddenimports = (
    collect_submodules('engine')
    + collect_submodules('uvicorn')
    + [
        'app',
        'fastapi',
        'starlette',
        'pydantic',
        'multipart',
        'python_multipart',
        'pdfplumber',
        'pdfminer',
        'pdfminer.high_level',
        'pypdf',
        'docx',
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
        'yaml',
        'httpx',
        'requests',
        'anyio',
        'anyio._backends._asyncio',
        'h11',
        'tkinter',
    ]
)

a = Analysis(
    [str(ROOT / 'launcher.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['playwright', 'pytest', 'IPython', 'jupyter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

if IS_MAC:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        icon=icon_file,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=APP_NAME,
    )
    app_bundle = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=icon_file,
        bundle_identifier='com.specit.studio',
        info_plist={
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleVersion': APP_VERSION,
            'NSHighResolutionCapable': True,
        },
    )
else:
    # Windows single-file standalone .exe (windowed) or Linux single binary
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=not IS_WIN,
        icon=icon_file,
    )
