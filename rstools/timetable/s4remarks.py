"""Section 4 REMARKS: what a possession's remarks say about which trains it affects.

The Section 4 check finds trains running over a section inside a possession window. The REMARKS column can lift
that for some trains (an excepted train type, a named train, access to a depot by a given route), limit it to
some dates, or leave some lines open. Each remark is read into rules here and applied to each clash:

* *exempt*  - the remark lets this train run (the clash is listed on the Exempt sheet, with the reason);
* *stands*  - the remark was read and does not help this train (the clash stays, with the remark's result);
* *check*   - the remark could not be applied from the XML alone (dates, weeks, other possessions, lines): the
  clash stays and says what to check.

Nothing is ever dropped silently: a remark the reader does not recognise makes the clash say 'Check remark'.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Optional, Sequence, Set, Tuple

EXEMPT, STANDS, CHECK = "exempt", "stands", "check"

# train types as Section 4 words them -> the headcode classes that are that type
TYPE_CLASSES = {"passenger": set("129"), "ecs": set("530"), "freight": set("4678")}
_TYPE_WORDS = [
    ("passenger", r"passenger(?:\s+trains?|\s+services?)?|pass(?:enger)?\s+services?|loaded\s+passenger"),
    ("ecs", r"e\.?\s?c\.?\s?s\.?|empty\s+(?:coaching\s+)?stock|empty\s+trains?|light\s+locos?|light\s+engines?"),
    ("freight", r"freight(?:\s+trains?|\s+services?)?|goods\s+trains?"),
]
_HEADCODE = r"\d[A-Z](?:\d{2}|XX|\*\*)"
_EXCEPT = r"(?:except(?:ing)?|excluding|excl\.?|other\s+than|but\s+not|not\s+(?:applicable\s+to|for|to)|save\s+for)"
_DATE = r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?"
_DEPOT_ACCESS = re.compile(
    r"\baccess\s+(?:to|from|to\s*/\s*from|to\s+and\s+from|in\s+and\s+out\s+of)\s+(?P<depot>.+?)"
    r"(?:\s+(?:t&rsmd|tmd|depot|sidings?|yard|emud|traincare))?\s+(?:is\s+)?(?:via|by\s+way\s+of|using)\s+"
    r"(?P<via>.+?)(?:\s+(?:only|permitted|available|maintained|retained))?\s*(?:[.;,]|$)", re.I)
_LINES_OPEN = re.compile(r"\b(?P<what>[\w &/.-]{2,40}?\s+lines?)\s+(?:remain\s+)?(?:open|available|unaffected)\b"
                         r"|\bvia\s+(?P<via>[\w &/.-]{2,40}?)\s+(?:excepted|unaffected|open)\b", re.I)
_AFTER = re.compile(r"\b(?:after|following|not\s+before)\s+(?:the\s+)?(?:passage|arrival|departure)?\s*(?:of\s+)?"
                    rf"(?P<hc>{_HEADCODE})\b", re.I)
_UNTIL = re.compile(r"\b(?:until|before|not\s+after)\s+(?:the\s+)?(?:passage|arrival|departure)?\s*(?:of\s+)?"
                    rf"(?P<hc>{_HEADCODE})\b", re.I)
_OTHER_POSS = re.compile(r"\bnot\s+(?:when|if|while)\b.+\b(?:taken|blocked|possession|in\s+use)\b"
                         r"|\bnot\s+(?:to\s+be\s+taken\s+)?with\s+possessions?\b|\bnot\s+available\s+when\b"
                         r"|\b(?:if|when)\b.{0,80}\b(?:is|are)\s+blocked\b|\bwhen\s+(?:disruptive\s+)?possessions?\s+"
                         r"take\s+place\b|\b(?:only\s+)?(?:available|apply|applies)\s+(?:only\s+)?when\b|\bonly\s+when\b|"
                         r"\bwhen\b.{0,60}\bdiverted\b|"
                         r"\btimes?\s+to\s+be\s+\d+\s+min(?:ute)?s?\s+(?:later|earlier)\s+if\b", re.I)
_GIVEN_UP = re.compile(rf"\b(?:given\s+up|released|eased)\s+for\s+(?:the\s+)?passage\s+of\s+(?P<hc>{_HEADCODE})\b"
                       rf"|\bpath\s+for\s+(?P<hc2>{_HEADCODE})\b"
                       rf"|\b(?:access\s+(?:is\s+)?available\s+for|to\s+allow|to\s+enable)\s+(?:the\s+)?(?P<hc3>{_HEADCODE})\b",
                       re.I)
_PERMITTED = re.compile(rf"(?P<hcs>{_HEADCODE}(?:\s*(?:/|,|and)\s*{_HEADCODE})*)\s+(?:to\s+be\s+|is\s+|are\s+)?"
                        r"(?:permitted|allowed)\s+to\s+(?:pass|run)", re.I)
_ROUTE_KEPT = re.compile(r"\broute\b[^.]{0,120}?\b(?:must|to|should|will|shall)\s+(?:always\s+)?(?:be\s+)?"
                         r"(?:available|maintained|kept)\b[^.]*|\bblocked\s+only\s+if\s+route\b[^.]*"
                         r"|\bonly\s+permitted\s+if\s+route\b[^.]*", re.I)
_TIMED_OVER = re.compile(r"\btrains?\s+(?:to\s+)?(?:be\s+)?(?:timed|timetabled|to\s+travel)\s+over\s+(?:the\s+)?"
                         r"(?P<lines>[\w &/]{2,40}?\s+lines?)\b", re.I)
_INFO = re.compile(r"\b(?:isolations?|OLE|OHL|overhead\s+line|feeds?|c/o|pts|points|patrolling|stabl\w*|sectional\s+"
                   r"appendix|level\s+crossings?|shunting|signals?|sig\b|limits?|T\s*[-–]\s*\d+|CPPP|DPPP|"
                   r"remembrance|eased|outstabl\w*|units?)\b", re.I)
_WEEKS = re.compile(r"\bweeks?\s+\(?(\d{1,2})(?:\s*(?:-|to)\s*(\d{1,2}))?", re.I)
_WPA = re.compile(r"\b\d+\s*w\.?\s*p\.?\s*a\b", re.I)


@dataclass
class Remarks:
    text: str
    except_types: Set[str] = field(default_factory=set)        # 'ecs' / 'passenger' / 'freight'
    only_types: Set[str] = field(default_factory=set)          # the possession applies to these types only
    except_trains: List[str] = field(default_factory=list)     # headcodes ('1A23', '5Exx')
    after_train: str = ""                                      # 'after passage of 5E10': trains before it run
    until_train: str = ""                                      # 'until passage of 1A01': trains after it run
    not_dates: List[Tuple[int, int, Optional[int]]] = field(default_factory=list)   # (day, month, year)
    date_ranges: List[Tuple[Tuple[int, int, Optional[int]], Tuple[int, int, Optional[int]]]] = field(
        default_factory=list)                                  # 'only 01/06 to 30/06'
    weeks: str = ""                                            # 'Weeks 12-20'
    depot_access: List[Tuple[str, str]] = field(default_factory=list)   # (depot, via)
    lines_open: List[str] = field(default_factory=list)       # 'Fast lines open', 'via Quarry line'
    other_possession: str = ""                                 # 'Not when ... is taken'
    routes_kept: List[str] = field(default_factory=list)      # 'A route must be available via ...'
    timed_lines: List[str] = field(default_factory=list)      # 'Trains to be timed over the Slow lines'
    info_only: bool = False                                    # only engineering arrangements (isolations, points)
    understood: bool = False                                   # any rule was read


_TYPE_RES: List[Tuple[str, "re.Pattern[str]"]] = []


def _type_hits(text: str) -> Set[str]:
    if not _TYPE_RES:                          # compiled once, not for every clause
        _TYPE_RES.extend((name, re.compile(rf"\b(?:{pat})\b", re.I)) for name, pat in _TYPE_WORDS)
    return {name for name, rx in _TYPE_RES if rx.search(text)}


def parse_remarks(text: str) -> Remarks:
    """The rules in one possession's REMARKS text (blank text -> no rules)."""
    text = " ".join((text or "").split())
    r = Remarks(text)
    if not text:
        return r
    for clause in re.split(r"(?<=[.;])\s+|\n", text):
        low = clause.lower()
        # excepted types / trains: 'Except ECS', 'Not applicable to passenger trains', 'ECS excepted'
        m = re.search(rf"\b{_EXCEPT}\b(?P<rest>.+)", clause, re.I)
        tail_excepted = re.search(r"(?P<rest>.+?)\b(?:excepted|exempt(?:ed)?|not\s+affected|may\s+(?:run|pass))\b",
                                  clause, re.I)
        for rest in [g.group("rest") for g in (m, tail_excepted) if g]:
            if _DEPOT_ACCESS.search(rest):
                continue
            r.except_types |= _type_hits(rest)
            r.except_trains += [h.upper() for h in re.findall(rf"\b{_HEADCODE}\b", rest, re.I)]
        # 'Freight only', 'Applies to passenger trains only'
        om = re.search(r"\b(?:applies\s+to\s+)?(?P<what>[\w .]{2,40}?)\s+only\b", clause, re.I)
        if om and not m and not re.search(_DATE, om.group("what")):
            r.only_types |= _type_hits(om.group("what"))
        am, um = _AFTER.search(clause), _UNTIL.search(clause)
        if am:
            r.after_train = am.group("hc").upper()
        if um:
            r.until_train = um.group("hc").upper()
        for dm in _DEPOT_ACCESS.finditer(clause):
            r.depot_access.append((dm.group("depot").strip(" ,."), dm.group("via").strip(" ,.")))
        for lm in _LINES_OPEN.finditer(clause):
            r.lines_open.append((lm.group("what") or "via " + (lm.group("via") or "")).strip())
        if _OTHER_POSS.search(clause) and not r.other_possession:
            r.other_possession = clause.strip()
        for gm in _GIVEN_UP.finditer(clause):
            r.except_trains.append((gm.group("hc") or gm.group("hc2") or gm.group("hc3")).upper())
        for pm in _PERMITTED.finditer(clause):
            r.except_trains += [h.upper() for h in re.findall(rf"{_HEADCODE}", pm.group("hcs"), re.I)]
        for km in _ROUTE_KEPT.finditer(clause):
            r.routes_kept.append(km.group(0).strip(" .;"))
        for tm in _TIMED_OVER.finditer(clause):
            r.timed_lines.append(tm.group("lines").strip())
        wm = _WEEKS.search(clause)
        if wm and not _WPA.search(clause):
            r.weeks = wm.group(0)
        # dates: 'Not 24/12', 'Not 24/12 to 02/01', 'Only 01.06 to 30.06'
        for rm in re.finditer(rf"{_DATE}\s*(?:-|to)\s*{_DATE}", clause):
            g = rm.groups()
            rng = (_dmy(g[0], g[1], g[2]), _dmy(g[3], g[4], g[5]))
            if re.search(r"\b(?:not|except|excluding)\b", low[:rm.start()]):
                r.not_dates.append(rng[0])
                r.not_dates.append(rng[1])
            else:
                r.date_ranges.append(rng)
        if re.search(r"\b(?:not|except|excluding)\b", low):
            spans = [rm.span() for rm in re.finditer(rf"{_DATE}\s*(?:-|to)\s*{_DATE}", clause)]
            for dm2 in re.finditer(_DATE, clause):
                if any(a <= dm2.start() < b for a, b in spans):
                    continue
                if not r.not_dates or _dmy(*dm2.groups()) not in r.not_dates:
                    r.not_dates.append(_dmy(*dm2.groups()))
    r.except_trains = list(dict.fromkeys(r.except_trains))
    r.understood = bool(r.except_types or r.only_types or r.except_trains or r.after_train or r.until_train
                        or r.not_dates or r.date_ranges or r.weeks or r.depot_access or r.lines_open
                        or r.other_possession or r.routes_kept or r.timed_lines or _WPA.search(text))
    if not r.understood and _INFO.search(text):
        r.info_only = r.understood = True
    return r


def _dmy(d: str, m: str, y: Optional[str]) -> Tuple[int, int, Optional[int]]:
    year = int(y) if y else None
    if year is not None and year < 100:
        year += 2000
    return int(d), int(m), year


def train_type(headcode: str) -> str:
    c = (headcode or " ")[0]
    for name, classes in TYPE_CLASSES.items():
        if c in classes:
            return name
    return ""


def _headcode_hits(pattern: str, headcode: str) -> bool:
    p, h = pattern.upper(), (headcode or "")[:4].upper()
    return len(h) == 4 and all(a == b or a in "X*" for a, b in zip(p, h))


@dataclass
class Verdict:
    outcome: str            # EXEMPT / STANDS / CHECK
    text: str               # what the remark meant for this train ('' when there are no remarks)
    every_line: Optional[bool] = None      # False when a remark leaves some lines open


@dataclass
class TrainView:
    """What the remark rules need to know about one clash's train."""
    headcode: str
    calls: Sequence[str]                    # TIPLOCs in order
    valid_from: Optional[date]
    valid_until: Optional[date]
    time_at_section: int                    # minutes (the earlier end)
    other_time: Callable[[str], Optional[int]]   # a named train's time at the section (minutes), or None


def apply(rules: Remarks, t: TrainView, tips: Callable[[str], Set[str]]) -> Verdict:
    """What `rules` mean for this train: exempt, stands or check (with the reason in words)."""
    if not rules.text:
        return Verdict(STANDS, "")
    notes: List[str] = []
    kind = train_type(t.headcode)
    if kind and kind in rules.except_types:
        return Verdict(EXEMPT, f"{_TYPE_NAME[kind]} excepted by the remarks")
    if rules.only_types and kind and kind not in rules.only_types:
        return Verdict(EXEMPT, "Applies to " + " / ".join(_TYPE_NAME[k] for k in sorted(rules.only_types))
                       + " only")
    for hc in rules.except_trains:
        if _headcode_hits(hc, t.headcode):
            return Verdict(EXEMPT, f"{hc} excepted by the remarks")
    for depot, via in rules.depot_access:
        d_tips, v_tips = set(), tips(via)
        for name in (depot, f"{depot} Depot", f"{depot} T&RSMD", f"{depot} TMD", f"{depot} EMUD",
                     f"{depot} Sidings", f"{depot} Traincare"):
            d_tips = tips(name)
            if d_tips:
                break
        if not d_tips:
            notes.append(f"Depot access ({depot} via {via}): '{depot}' is not in the XML - check the route")
            continue
        ends_there = bool(t.calls) and (t.calls[-1] in d_tips or t.calls[0] in d_tips)
        if not ends_there:
            notes.append(f"Not going to or from {depot}, so the depot access does not apply")
            continue
        if not v_tips:
            notes.append(f"Goes to / from {depot}; '{via}' is not in the XML - check it runs via {via}")
            continue
        if any(c in v_tips for c in t.calls):
            return Verdict(EXEMPT, f"Access to {depot} via {via}: the train goes to / from {depot} via {via}")
        notes.append(f"Goes to / from {depot} but not via {via}: the depot access does not cover it")
    for named, before in ((rules.after_train, True), (rules.until_train, False)):
        if not named:
            continue
        other = t.other_time(named)
        if other is None:
            notes.append(f"{named} (named in the remarks) is not in the XML - check the train runs "
                         f"{'before' if before else 'after'} it")
        elif (t.time_at_section < other) if before else (t.time_at_section > other):
            return Verdict(EXEMPT, f"Runs {'before' if before else 'after'} {named} "
                                   f"({'possession starts after' if before else 'possession ends at'} its passage)")
        else:
            notes.append(f"Runs {'after' if before else 'before'} {named}, inside the possession")
    dates_out = _date_outcome(rules, t)
    if dates_out is not None:
        if dates_out[0] == EXEMPT:
            return Verdict(EXEMPT, dates_out[1])
        notes.append(dates_out[1])
    if rules.weeks:
        notes.append(f"Only some weeks ({rules.weeks}) - check the dates the train runs")
    if rules.other_possession:
        notes.append(f"Depends on another possession: '{rules.other_possession}'")
    for kept in rules.routes_kept:
        notes.append(f"'{kept}' - check this train keeps that route")
    every_line: Optional[bool] = None
    if rules.lines_open:
        every_line = False
        notes.append("Lines left open (" + "; ".join(rules.lines_open) + ") - check the line used")
    if rules.timed_lines:
        every_line = False
        notes.append("Trains timed over the " + "; ".join(rules.timed_lines) + " - check against the lines blocked")
    if rules.info_only and not notes:
        return Verdict(STANDS, "Remarks are about engineering arrangements (isolations, points, stabling), not "
                               "which trains may run")
    if not rules.understood:
        return Verdict(CHECK, "Check remark: " + rules.text)
    outcome = CHECK if any("check" in n.lower() for n in notes) else STANDS
    return Verdict(outcome, "; ".join(notes) if notes else "Remarks read: they do not except this train",
                   every_line)


_TYPE_NAME = {"passenger": "Passenger trains", "ecs": "Empty stock", "freight": "Freight"}


def _resolve(dmy: Tuple[int, int, Optional[int]], near: Optional[date]) -> Optional[date]:
    d, m, y = dmy
    years = [y] if y else ([near.year, near.year + 1, near.year - 1] if near else [])
    for yy in years:
        try:
            return date(yy, m, d)
        except ValueError:
            continue
    return None


def _date_outcome(rules: Remarks, t: TrainView) -> Optional[Tuple[str, str]]:
    """Dates in the remarks against the train's own dates: exempt only when every date it runs is excluded."""
    a, b = t.valid_from, t.valid_until
    if rules.date_ranges:
        hits = []
        for lo, hi in rules.date_ranges:
            d1, d2 = _resolve(lo, a), _resolve(hi, a)
            if d1 and d2 and d2 < d1:
                d2 = d2.replace(year=d2.year + 1)
            if d1 and d2:
                hits.append((d1, d2))
        if hits and a and b and not any(d1 <= b and d2 >= a for d1, d2 in hits):
            return EXEMPT, ("Possession only " + ", ".join(f"{d1:%d/%m} to {d2:%d/%m}" for d1, d2 in hits)
                            + f": the train runs {a:%d/%m/%Y} to {b:%d/%m/%Y}")
        if hits:
            return CHECK, ("Possession only " + ", ".join(f"{d1:%d/%m} to {d2:%d/%m}" for d1, d2 in hits)
                           + " - check the dates the train runs")
    if rules.not_dates:
        days = [_resolve(x, a) for x in rules.not_dates]
        shown = ", ".join(f"{d:%d/%m}" for d in days if d)
        if a and b and a == b and any(d == a for d in days):
            return EXEMPT, f"Not on {shown}: the train only runs {a:%d/%m/%Y}"
        return CHECK, f"Not on {shown} - the clash stands on the other dates"
    return None
