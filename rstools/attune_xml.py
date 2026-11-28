"""The parts every Attune diagram XML reader shares (Stats Pack, station working book, berthing chart): walking
the file safely, times, plan types and location names. Each reader builds its own view of the trains and
diagrams from these."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple


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


# --------------------------------------------------------------------------- unit diagrams
@dataclass
class RawMove:
    """One <journey> of a unit diagram: the train it works (id and key, from its <activity>), where and when, and
    the units coupled to it (depot + diagram number, in position order)."""
    train: str
    key: str
    origin: str
    dest: str
    dep: Optional[int]
    arr: Optional[int]
    coupled: List[str]


@dataclass
class RawDiagram:
    """A <unitDiagram> as written in the XML, for each reader to turn into its own view. Everything inside a
    <coupled> block (another unit's depot, diagram, notes and activities) is kept apart from the diagram's own."""
    number: str                     # the diagram's id ('7', or already 'BI7' in some exports)
    depot: str                      # its own depot (the first <depot> outside a <coupled> block)
    fleet: str                      # the first <res>
    days_mask: str                  # daysrun
    type: str                       # plan type (L / S / D ...)
    moves: List[RawMove] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)          # every <text> of its own
    static_notes: List[str] = field(default_factory=list)   # the <text> of its <diagStatic> (where it stands)
    static_loc: str = ""
    activities: Counter = field(default_factory=Counter)    # its own WASH / CET / FUEL ... activities

    @property
    def key(self) -> str:
        """Depot + number ('BI7'), as every report names a diagram."""
        return self.depot + self.number


class UnitDiagramParser:
    """Reads the <unitDiagram> elements of an Attune XML from the walk() events it is given (start / end), so one
    reading of the file can also collect trains and locations. feed() returns a RawDiagram when one ends."""

    def __init__(self):
        self.cur: Optional[RawDiagram] = None
        self._move: Optional[dict] = None
        self._coupled: List[Tuple[int, str]] = []
        self._depth = 0                 # inside <coupled> (nested blocks counted)
        self._cpos = 0
        self._cdepot = self._cnum = ""
        self._static = False

    @property
    def inside(self) -> bool:
        return self.cur is not None

    def feed(self, event: str, tag: str, el: ET.Element) -> Optional[RawDiagram]:
        if event == "start":
            if tag == "unitDiagram":
                self.cur = RawDiagram(el.get("id", "").strip(), "", "", el.get("daysrun", ""), el.get("type", ""))
                self._depth = 0
            elif self.cur is None:
                return None
            elif tag == "journey":
                self._move = dict(el.attrib)
                self._move["train"] = self._move["key"] = ""
                self._coupled = []
            elif tag == "coupled":
                self._depth += 1
                self._cpos, self._cdepot, self._cnum = int(el.get("position", "0") or 0), "", ""
            elif tag == "diagStatic":
                self._static = True
                self.cur.static_loc = el.get("loc", "") or self.cur.static_loc
            return None
        cur = self.cur
        if cur is None:
            return None
        own = self._depth == 0
        if tag == "depot":
            if not own:
                self._cdepot = el.get("id", "").strip()
            elif not cur.depot:
                cur.depot = el.get("id", "").strip()
        elif tag == "res" and not cur.fleet:
            cur.fleet = el.get("id", "").strip()
        elif tag == "diagram" and not own:
            self._cnum = el.get("id", "").strip()
        elif tag == "coupled":
            self._coupled.append((self._cpos, self._cdepot + self._cnum))
            self._depth = max(self._depth - 1, 0)
        elif tag == "activity":
            if own and el.get("id", "").strip():
                cur.activities[el.get("id", "").strip()] += 1
            if self._move is not None and el.get("trainid"):
                self._move["train"], self._move["key"] = el.get("trainid", ""), el.get("trainKey", "")
        elif tag == "text" and own and (el.text or "").strip():
            cur.notes.append((el.text or "").strip())
            if self._static:
                cur.static_notes.append((el.text or "").strip())
        elif tag == "diagStatic":
            self._static = False
        elif tag == "journey" and self._move is not None:
            m = self._move
            cur.moves.append(RawMove(m["train"], m["key"], m.get("origin", ""), m.get("dest", ""),
                                     secs(m.get("dep")), secs(m.get("arr")), [k for _p, k in sorted(self._coupled)]))
            self._move = None
        elif tag == "unitDiagram":
            self.cur = None
            el.clear()
            return cur
        return None

