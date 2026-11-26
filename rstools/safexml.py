"""Guards for the XML the app reads: Attune XML exports (read as a stream) and the XML parts of Word and Excel
files.

Attune exports and Office parts never contain a document type declaration, so any '<!DOCTYPE' or '<!ENTITY' is
refused before parsing: that rules out entity expansion ('billion laughs') and external entities / references
(files or web addresses pulled in by the XML) whatever the XML library would do with them. Sizes are checked
against rstools.limits. A truncated file or a bad character is reported by the parser as ET.ParseError, which every
reader already turns into its own plain message; UnsafeXMLError is a ParseError too, so it is reported the same way."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

from . import limits

HEAD_BYTES = 64 * 1024                  # the start of a file looked at for a declaration (it must come first)
_DECL = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.I)
_ELEMENT = re.compile(rb"<[A-Za-z_]")       # the first element: a declaration can only come before it


class UnsafeXMLError(ET.ParseError):
    pass


def _check_head(head: bytes, name: str):
    probe = head
    if probe[:2] in (b"\xff\xfe", b"\xfe\xff"):           # UTF-16 (with its byte order mark)
        probe = head.decode("utf-16", "ignore").encode("utf-8", "ignore")
    first = _ELEMENT.search(probe)
    if first is None and len(head) >= HEAD_BYTES:
        raise UnsafeXMLError(f"'{name}' does not start like an XML file (no element in its first "
                             f"{HEAD_BYTES // 1024} KB), so it was not read")
    if _DECL.search(probe[:first.start()] if first else probe):
        raise UnsafeXMLError(f"'{name}' has a document type declaration (DOCTYPE / ENTITY), which Attune and Office "
                             "files never have, so it was not read")


def check_file(path: str) -> str:
    """Check an XML file before it is parsed (size and declarations); returns the path."""
    limits.check_size(path, "XML_MAX_BYTES", "Attune XML")
    with open(path, "rb") as fh:
        _check_head(fh.read(HEAD_BYTES), os.path.basename(path))
    return path


def fromstring(data: bytes, name: str = "XML") -> ET.Element:
    """ET.fromstring after checking the size and that there is no declaration (an Office file's XML part)."""
    limit = limits.get("XML_PART_MAX_BYTES")
    if len(data) > limit:
        raise UnsafeXMLError(f"'{name}' is larger than any real Office file part ({len(data) // limits.MB} MB), "
                             "so it was not read")
    _check_head(data[:HEAD_BYTES], name)
    return ET.fromstring(data)
