"""Other operators' units on a berthing chart, from their own files (Attune XML, VPT or CIF).

An Attune XML whose unit diagrams give each unit's next-day working is read like the chart's own XML. Any other
file (no diagrams, no next-day workings, a VPT or a CIF) is matched by place: a train ending at a location forms
the next train starting there (same platform or road where both say), and a pair that crosses into another day is
a stay. With no unit type known, the headcodes stand in for it. Other operators' units are shown in grey."""
from __future__ import annotations

import os
from typing import Dict, List, Sequence, Tuple

from rstools import others as O

from .stays import End, Stay, build
from .xmlread import BerthingError, read_xml
from rstools.naming import plural

SOURCE = 1000                   # other operators' files are told apart from the chart's own XMLs (0, 1)


def _from_diagrams(path: str, source: int, op: str) -> List[Stay]:
    """The stays of an Attune XML whose diagrams give the next-day workings, else []."""
    try:
        x = read_xml(path, source)
    except BerthingError:
        return []
    stays = build([x]).stays
    if not any(s.depart is not None for s in stays):
        return []
    for s in stays:
        s.other = op
    return stays


def _from_places(plan, source: int) -> List[Stay]:
    fleet = O.fleets(plan)
    out = []
    for lk in O.link(O.ends([plan])):
        a, d = lk.arrive, lk.depart
        if d is not None and lk.nights == 0:
            continue                                    # a turnround the same day: not berthed overnight
        op = O.operator(plan, a.train)
        unit_type = fleet.get(a.train.id, "")
        arrive = End(a.day, a.time, a.train.id, a.plat, O.is_empty(a.train), False, (source, f"{a.n}"), [])
        depart = None
        if d is not None:
            depart = End(d.day, d.time, d.train.id, d.plat, O.is_empty(d.train), False, (source, f"{d.n}"), [])
        out.append(Stay(a.headcode, unit_type, a.loc, a.plat or (d.plat if d else ""), a.day,
                        lk.nights if d is not None else 1, arrive, depart, op, not unit_type))
    return out


def other_stays(paths: Sequence[str], log=lambda _m: None) -> Tuple[List[Stay], List[str], Dict[str, str]]:
    """(stays, warnings, location names) of the other operators' files."""
    stays: List[Stay] = []
    warnings: List[str] = []
    names: Dict[str, str] = {}
    try:
        plans = O.load(paths, log)
    except O.OthersError as exc:
        raise BerthingError(str(exc))
    for i, (path, plan) in enumerate(zip(paths, plans)):
        names.update(plan.locations)
        op = O.operator(plan)
        found = _from_diagrams(path, SOURCE + i, op) if path.lower().endswith(".xml") and plan.diagrams else []
        how = "their next-day workings"
        if not found:
            found = _from_places(plan, SOURCE + i)
            how = "where each train ends and the next one starts (no next-day workings in the file)"
        if found and all(s.by_headcode for s in found):
            how += "; no unit types, so the headcodes are shown"
        warnings.append(f"Other operator {op} ({os.path.basename(path)}): {plural(len(found), 'overnight stay')}, "
                        f"from {how}. "
                        "They are shown in grey.")
        stays += found
    return stays, warnings, names
