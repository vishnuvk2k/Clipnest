# PyInstaller build file.
#
#   pyinstaller fetchly.spec                     -> dist/Fetchly/ (folder, used by the installer)
#   set FETCHLY_ONEFILE=1 & pyinstaller fetchly.spec -> dist/Fetchly.exe (one portable file)
#
# No console window. yt-dlp, FFmpeg and Deno are downloaded on first launch.

import os
import sys

ONEFILE = os.environ.get("FETCHLY_ONEFILE") == "1"

# Qt modules Fetchly never uses; leaving them out keeps the build much smaller.
EXCLUDES = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtXml", "PySide6.QtConcurrent", "tkinter",
    "yt_dlp", "pytest", "PIL",
]

a = Analysis(
    ["Fetchly.py"],
    pathex=["."],
    datas=[("assets/fetchly.svg", "assets"), ("assets/fetchly.ico", "assets")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe_options = dict(
    name="Fetchly",
    icon="assets/fetchly.ico",
    console=False,
    upx=False,
    version="tools/version_info.txt" if sys.platform == "win32" else None,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, **exe_options)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, **exe_options)
    coll = COLLECT(exe, a.binaries, a.datas, name="Fetchly", upx=False)
