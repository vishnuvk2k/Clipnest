# PyInstaller build file. Build with:  pyinstaller fetchly.spec
# Produces dist/Fetchly.exe (Windows) or dist/Fetchly (macOS/Linux): one file,
# no console window. yt-dlp and FFmpeg are downloaded on first launch.

import sys

# Qt modules Fetchly never uses; leaving them out keeps the .exe much smaller.
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
    datas=[("assets/fetchly.svg", "assets")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Fetchly",
    icon="assets/fetchly.ico",
    console=False,
    upx=False,
    version="tools/version_info.txt" if sys.platform == "win32" else None,
)
