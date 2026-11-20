# PyInstaller build spec for Train Planning Tools (single portable exe).
#
# Build:  pyinstaller --noconfirm packaging/TrainPlanningTools.spec
#
# Size optimisation without losing functionality:
#  * modules the app never uses are excluded (numpy, test frameworks, bz2/lzma
#    compression). SSL is kept: Options > Check for updates talks to GitHub over HTTPS;
#  * only the drag-and-drop (tkdnd) binary for this platform is bundled, not all 14;
#  * Tcl/Tk time-zone tables, translated message catalogues, demo images and East-Asian
#    text encodings are left out (the app's dialogs are English and it uses no time zones).
# UPX compression is deliberately NOT used: UPX-packed exes trigger antivirus warnings.
import os
import platform
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(ROOT, "packaging", "TrainPlanningTools.ico")
VERSION_FILE = os.path.join(ROOT, "version_info.txt")

EXCLUDES = [
    "bz2", "_bz2", "lzma", "_lzma",       # zipfile handles their absence
    "numpy", "pandas", "lxml",            # optional openpyxl extras, not used (Pillow is kept: PDF output)
    "cryptography",                       # pypdf extra for encrypted PDFs (train prints are not encrypted)
    "charset_normalizer",                 # reportlab: only its XML parser uses it (not used here)
    # Pillow: reportlab needs only PIL.Image; the image codecs and font engine are unused here
    # (the AVIF codec alone is ~8 MB on Windows)
    "PIL._avif", "PIL._webp", "PIL._imagingft", "PIL._imagingcms", "PIL._imagingmath", "PIL._imagingmorph",
    "PIL._imagingtk", "PIL.ImageFont", "PIL.ImageCms", "PIL.ImageTk", "PIL.ImageQt", "PIL.ImageShow",
    "PIL.ImageDraw", "PIL.ImageFilter", "PIL.ImageGrab", "PIL.ImageWin", "PIL.SpiderImagePlugin",
    # reportlab: charts / barcodes / bitmap renderer are not used (tables and text only)
    "reportlab.graphics", "reportlab.lib.pygments2xpre", "reportlab.lib.rparsexml",
    "unittest", "pytest", "doctest", "pdb", "pydoc_data",
    "sqlite3", "_sqlite3", "xmlrpc", "ftplib", "curses",
    "tkinter.test", "idlelib", "lib2to3", "setuptools", "pkg_resources",
]

if sys.platform.startswith("win"):
    machine = platform.machine().lower()
    DND_DIR = "win-arm64" if "arm" in machine else ("win-x64" if sys.maxsize > 2 ** 32 else "win-x86")
elif sys.platform == "darwin":
    DND_DIR = "osx-arm64" if platform.machine() == "arm64" else "osx-x64"
else:
    DND_DIR = "linux-arm64" if platform.machine() in ("aarch64", "arm64") else "linux-x64"


def _keep_dnd(dest):
    """Keep tkinterdnd2's Python files and only this platform's Tcl-8.6 tkdnd binaries."""
    parts = dest.replace("\\", "/").split("/")
    if "tkdnd" not in parts:
        return True
    i = parts.index("tkdnd")
    return len(parts) <= i + 1 or parts[i + 1] == DND_DIR


KEEP_ENCODINGS = {"ascii", "cp1250", "cp1252", "cp437", "cp850", "iso8859-1", "iso8859-15",
                  "symbol", "dingbats", "macRoman"}


def _keep_tcl(dest):
    d = dest.replace("\\", "/")
    if d.startswith(("_tcl_data/tzdata/", "_tk_data/images/", "_tk_data/demos/")):
        return False
    if d.startswith(("_tcl_data/msgs/", "_tk_data/msgs/")):
        return os.path.basename(d).startswith("en")
    if d.startswith("_tcl_data/encoding/"):
        return os.path.splitext(os.path.basename(d))[0] in KEEP_ENCODINGS
    return True


def _app_data():
    """Every data file the app ships with (logos, layouts, default tables, the TT Comparison template)."""
    out = []
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "rstools")):
        for name in files:
            if not name.endswith((".py", ".pyc")) and "__pycache__" not in folder:
                out.append((os.path.join(folder, name), os.path.relpath(folder, ROOT)))
    return out


APP_DATA = _app_data()
dnd_datas = [(s, d) for s, d in collect_data_files("tkinterdnd2") if _keep_dnd(d)]
dnd_bins = [(s, d) for s, d in collect_dynamic_libs("tkinterdnd2") if _keep_dnd(d)]

a = Analysis(
    [os.path.join(ROOT, "TrainPlanningTools.py")],
    pathex=[ROOT],
    binaries=dnd_bins + collect_dynamic_libs("pypdfium2_raw"),                # PDFium: the fast PDF reader
    datas=dnd_datas + [(ICON, "packaging")] + APP_DATA + collect_data_files("pypdfium2_raw")
          + collect_data_files("pypdfium2"),      # reportlab's fonts are not needed (core Helvetica)
    hiddenimports=(collect_submodules("openpyxl") + collect_submodules("rstools")
                   + collect_submodules("reportlab.pdfbase", lambda m: "_fontdata" in m)   # loaded by name
                   + ["reportlab.rl_settings", "reportlab.platypus", "reportlab.lib.styles", "reportlab.pdfgen.canvas"]
                   + collect_submodules("pypdf", lambda m: "crypt" not in m)
                   + collect_submodules("pypdfium2") + collect_submodules("pypdfium2_raw")
                   + ["xlrd", "pyxlsb", "tkinterdnd2"]),
    excludes=EXCLUDES,
    noarchive=False,
)

# drop excluded Tcl/Tk data and any tkdnd binaries for other platforms picked up by hooks
a.datas = [t for t in a.datas if _keep_tcl(t[0]) and _keep_dnd(t[0])]
DROP_BINARIES = ("_avif", "_webp", "_imagingft", "_imagingcms", "_imagingmath", "_imagingmorph", "_imagingtk")
a.binaries = [t for t in a.binaries if _keep_dnd(t[0]) and not any(x in os.path.basename(t[0]) for x in DROP_BINARIES)]
a.pure = [t for t in a.pure if not ("ImagePlugin" in t[0] and t[0].startswith("PIL."))      # image formats
          and not t[0].startswith("reportlab.graphics")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TrainPlanningTools",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON if os.path.exists(ICON) else None,
    version=VERSION_FILE if os.path.exists(VERSION_FILE) else None,
)
