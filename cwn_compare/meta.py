"""Hidden data sheet stored inside every comparison CWN.

It holds the parsed baseline (the updated CWN of the last comparison) and the
list of all highlighted changes, so that 'Add new comparisons to previously
generated comparison CWN' can carry earlier amendments forward in their
original colour.
"""
from __future__ import annotations

import base64
import json
import zlib
import zipfile

META_SHEET = "_CWNCompareData"
MAGIC = "CWNCOMPARE-META"
VERSION = 2
CHUNK = 30000


def write_meta(wb, data: dict):
    if META_SHEET in wb.sheetnames:
        wb.remove(wb[META_SHEET])
    ws = wb.create_sheet(META_SHEET)
    blob = base64.b64encode(zlib.compress(json.dumps(data, separators=(",", ":")).encode("utf-8"), 9)).decode("ascii")
    ws.cell(row=1, column=1, value=MAGIC)
    ws.cell(row=2, column=1, value=VERSION)
    ws.cell(row=3, column=1, value=(len(blob) + CHUNK - 1) // CHUNK)
    for i in range(0, len(blob), CHUNK):
        ws.cell(row=4 + i // CHUNK, column=1, value=blob[i:i + CHUNK])
    ws.sheet_state = "veryHidden"


def is_comparison_output(path: str) -> bool:
    """Cheap check (no workbook load) for the hidden data sheet."""
    try:
        with zipfile.ZipFile(path) as z:
            return META_SHEET.encode() in z.read("xl/workbook.xml")
    except Exception:
        return False


def read_meta_file(path: str):
    """Read the hidden data straight from a file without loading every tab."""
    from rstools.fsutil import long_path
    path = long_path(path)              # files in very deep folders
    if not is_comparison_output(path):
        return None
    import openpyxl
    from rstools.fsutil import check_office_file
    check_office_file(path)     # refuse a 'zip bomb' before unpacking
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        ws = wb[META_SHEET]
        col = [r[0] for r in ws.iter_rows(min_col=1, max_col=1, values_only=True)]
        if not col or col[0] != MAGIC:
            return None
        blob = "".join(str(v or "") for v in col[3:3 + int(col[2] or 0)])
        return json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
    except Exception:
        return None
    finally:
        wb.close()
