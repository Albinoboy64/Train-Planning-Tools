"""Write the Windows version resource used by PyInstaller (--version-file).

This puts the product name, description, version and publisher into the exe's
Properties > Details tab and into the information Windows shows about it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cwn_compare import __version__  # noqa: E402

PUBLISHER = os.environ.get("CWN_PUBLISHER", "GTR Train Planning")

parts = [int(p) for p in __version__.replace("-", ".").split(".") if p.isdigit()]
parts = (parts + [0, 0, 0, 0])[:4]
ver_tuple = tuple(parts)

TEMPLATE = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={ver_tuple}, prodvers={ver_tuple}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080904B0', [
      StringStruct('CompanyName', '{PUBLISHER}'),
      StringStruct('FileDescription', 'Train Planning Tools - CWN Tools, Stats Pack, Timetable Comparison and Live View'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'TrainPlanningTools'),
      StringStruct('LegalCopyright', '{PUBLISHER}'),
      StringStruct('OriginalFilename', 'TrainPlanningTools.exe'),
      StringStruct('ProductName', 'Train Planning Tools'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [2057, 1200])])
  ]
)
"""

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "version_info.txt"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE)
    print(f"wrote {out} for version {__version__}")
