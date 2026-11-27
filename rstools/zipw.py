"""Write .xlsx (ZIP) files, compressing the parts on all CPU cores.

zlib releases Python's global lock while it compresses, so the parts of a workbook (one XML file
per tab) are deflated in parallel threads - the slowest step of saving a large workbook. The file
is a plain ZIP (deflate, no ZIP64 needed below 4 GB), written to a temporary name and then moved
into place, so a failed save never leaves a half-written workbook.
"""
from __future__ import annotations

import os
import struct
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List, Tuple

LEVEL = 6                                     # the same compression Excel and openpyxl use


def workers() -> int:
    """Threads for compression: every core but one (so the PC stays responsive), at least one."""
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def _deflate(data: bytes) -> Tuple[int, bytes]:
    c = zlib.compressobj(LEVEL, zlib.DEFLATED, -15)
    return zlib.crc32(data) & 0xFFFFFFFF, c.compress(data) + c.flush()


class Deflated:
    """A part compressed piece by piece as it is made, so a very large part (a Word document of thousands of
    pages) is never held whole in memory, nor copied to bytes before compressing. write() text, then close()."""

    def __init__(self):
        self._c = zlib.compressobj(LEVEL, zlib.DEFLATED, -15)
        self.crc, self.size, self.comp = 0, 0, b""
        self._out: List[bytes] = []

    def write(self, text: str):
        data = text.encode("utf-8")
        self.crc = zlib.crc32(data, self.crc)
        self.size += len(data)
        self._out.append(self._c.compress(data))

    def close(self) -> "Deflated":
        self._out.append(self._c.flush())
        self.comp, self._out = b"".join(self._out), []
        self.crc &= 0xFFFFFFFF
        return self


def _dos_time() -> Tuple[int, int]:
    t = time.localtime()
    return ((t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2),
            ((max(t.tm_year, 1980) - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday)


def write_zip(path: str, items: Iterable[Tuple[str, object]]):
    """Write `items` [(name inside the zip, bytes or a closed Deflated)] to `path` (replacing it only once
    complete)."""
    parts = list(items)
    plain = [d for _n, d in parts if not isinstance(d, Deflated)]
    big = [d for d in plain if len(d) > 64 * 1024]      # type: ignore[arg-type]

    def pack(d) -> Tuple[int, bytes]:
        return (d.crc, d.comp) if isinstance(d, Deflated) else _deflate(d)
    if len(big) > 1 and workers() > 1:
        with ThreadPoolExecutor(max_workers=workers()) as pool:
            packed = list(pool.map(pack, (d for _n, d in parts)))
    else:
        packed = [pack(d) for _n, d in parts]
    dos_t, dos_d = _dos_time()
    from .fsutil import long_path, move_new, temp_path
    tmp, final = long_path(temp_path(path)), long_path(path)
    try:
        with open(tmp, "xb") as fh:          # a new file only: never one already there
            central = []
            for (name, data), (crc, comp) in zip(parts, packed):
                size = data.size if isinstance(data, Deflated) else len(data)      # type: ignore[arg-type]
                raw = name.encode("utf-8")
                flags = 0x0800 if not name.isascii() else 0
                if max(size, len(comp), fh.tell()) >= 0xFFFFFFFF:
                    raise ValueError("Workbook too large (over 4 GB).")
                offset = fh.tell()
                fh.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, flags, 8, dos_t, dos_d, crc,
                                     len(comp), size, len(raw), 0))
                fh.write(raw)
                fh.write(comp)
                central.append(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, flags, 8, dos_t, dos_d,
                                           crc, len(comp), size, len(raw), 0, 0, 0, 0, 0, offset) + raw)
            start = fh.tell()
            for entry in central:
                fh.write(entry)
            size = fh.tell() - start
            fh.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central), size, start, 0))
        move_new(tmp, final)                 # never over a file already there
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
