"""The parts every Attune diagram XML reader shares (Stats Pack, station working book, berthing chart): walking
the file safely, times, plan types and location names. Each reader builds its own view of the trains and
diagrams from these."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, Iterator, Optional, Tuple


def walk(path: str) -> Iterator[Tuple[str, str, ET.Element]]:
    """(event, tag without namespace, element) for every start and end of the XML, after the size and
    DOCTYPE checks of rstools.safexml. Raises ET.ParseError or OSError as iterparse does."""
    from rstools import safexml
    from rstools.fsutil import long_path
    for event, el in ET.iterparse(safexml.check_file(long_path(path)), events=("start", "end")):
        yield event, el.tag.rsplit("}", 1)[-1], el


def secs(text: Optional[str]) -> Optional[int]:
    """'05:34:30' / '05:34' as seconds after midnight; None if blank or not a time."""
    if not text:
        return None
    try:
        parts = [int(p) for p in text.split(":")]
    except ValueError:
        return None
    parts += [0] * (3 - len(parts))
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def plan_type(attrib: Dict[str, str]) -> str:
    """A <train>'s plan type, with a draft (provisional) version of an LTP train shown as 'D'."""
    plan = attrib.get("planType", "")
    if attrib.get("provisional", "").lower() == "true" and plan.upper() in ("", "L"):
        return "D"
    return plan


def location(el: ET.Element) -> Optional[Tuple[str, str]]:
    """(TIPLOC, name) of a <location>; None for one without a code (it could never be looked up)."""
    tiploc = el.get("tiploc", "").strip()
    if not tiploc:
        return None
    return tiploc, el.get("longDesc") or el.get("shortDesc") or tiploc
