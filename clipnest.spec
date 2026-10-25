# PyInstaller build file.
#
#   pyinstaller clipnest.spec                     -> dist/Clipnest/ (folder, used by the installer)
#   set CLIPNEST_ONEFILE=1 & pyinstaller clipnest.spec -> dist/Clipnest.exe (one portable file)
#   on macOS: pyinstaller clipnest.spec           -> dist/Clipnest.app
#
# No console window. yt-dlp, FFmpeg and Deno are downloaded on first launch.

import os
import sys

sys.path.insert(0, os.path.abspath("."))
from clipnest import __version__

IS_MAC = sys.platform == "darwin"

ONEFILE = os.environ.get("CLIPNEST_ONEFILE") == "1"

# Qt modules Clipnest never uses; leaving them out keeps the build much smaller.
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
    ["Clipnest.py"],
    pathex=["."],
    datas=[("assets/clipnest.svg", "assets"), ("assets/clipnest.ico", "assets")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe_options = dict(
    name="Clipnest",
    icon="assets/clipnest.icns" if IS_MAC else "assets/clipnest.ico",
    console=False,
    upx=False,
    version="tools/version_info.txt" if sys.platform == "win32" else None,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, **exe_options)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, **exe_options)
    coll = COLLECT(exe, a.binaries, a.datas, name="Clipnest", upx=False)
    if IS_MAC:
        app = BUNDLE(
            coll,
            name="Clipnest.app",
            icon="assets/clipnest.icns",
            bundle_identifier="com.vishnuvk.clipnest",
            version=__version__,
            info_plist={
                "CFBundleDisplayName": "Clipnest",
                "CFBundleShortVersionString": __version__,
                "CFBundleVersion": __version__,
                "NSHighResolutionCapable": True,
                "NSRequiresAquaSystemAppearance": False,   # follow dark mode
                "LSMinimumSystemVersion": "12.0",
                "NSHumanReadableCopyright": "Copyright (c) 2026 Vishnu VK. MIT License.",
            },
        )
