from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

webview_datas, webview_binaries, webview_hidden = collect_all('webview')
pyside_datas, pyside_binaries, pyside_hidden = collect_all('PySide6')
shiboken_datas, shiboken_binaries, shiboken_hidden = collect_all('shiboken6')
qtpy_datas, qtpy_binaries, qtpy_hidden = collect_all('qtpy')
uvicorn_hidden = collect_submodules('uvicorn')
watchdog_hidden = collect_submodules('watchdog')

hiddenimports = sorted(set(
    webview_hidden
    + pyside_hidden
    + shiboken_hidden
    + qtpy_hidden
    + uvicorn_hidden
    + watchdog_hidden
    + collect_submodules('webview.platforms')
    + [
        'webview.platforms.qt',
        'qtpy',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtPrintSupport',
    ]
))

datas = [
    (str(ROOT / 'frontend'), 'frontend'),
    (str(ROOT / 'config.json'), '.'),
] + webview_datas + pyside_datas + shiboken_datas + qtpy_datas

binaries = webview_binaries + pyside_binaries + shiboken_binaries + qtpy_binaries


a = Analysis(
    [str(ROOT / 'desktop.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='conduit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='conduit',
)
