"""Which box a dropped file goes to - the same rule on every tab."""
from __future__ import annotations

import os
from typing import Callable, List, Optional, Sequence, Tuple


# --------------------------------------------------------------------------- #
class Slot:
    """A file box files can be dropped on: its variable, the files it takes, and whether it holds several."""

    def __init__(self, var, accepts: Callable[[str], bool], multi: bool = False, prefer=None):
        self.var, self.accepts, self.multi = var, accepts, multi
        self.prefer = prefer or (lambda p: False)       # a file this box is the natural home of (when all full)

    def empty(self) -> bool:
        return not self.var.get().strip()


def route_drop(files: Sequence[str], slots: Sequence[Slot], target: Optional[Slot] = None,
               join: Callable[[List[str]], str] = lambda fs: " ; ".join(fs)) -> Tuple[int, List[str]]:
    """Put dropped files into their boxes. Dropped on a box that takes the file: it replaces what is there (a
    box holding several files adds them). Dropped elsewhere: each file goes to the first empty box that takes
    it; when every such box is full, it replaces the one that is its natural home, else the last one. Two
    files for the same pair of boxes go in date order (the older first). Returns (files placed, files left
    over)."""
    files = list(files)
    if target is not None:
        mine = [f for f in files if target.accepts(f)]
        if mine:
            if target.multi:
                have = [] if target.empty() else [p.strip() for p in target.var.get().split(";") if p.strip()]
                target.var.set(join(have + [f for f in mine if f not in have]))
            else:
                target.var.set(mine[0])
                mine = mine[:1]
            rest = [f for f in files if f not in mine]
            if not rest:
                return len(mine), []
            placed, left = route_drop(rest, [s for s in slots if s is not target])
            return len(mine) + placed, left
    placed, left = 0, []
    used: set = set()
    groups: dict = {}
    for f in files:                                   # files of one kind together (e.g. two CWNs: date order)
        kinds = tuple(i for i, s in enumerate(slots) if s.accepts(f))
        groups.setdefault(kinds, []).append(f)
    for kinds, fs in groups.items():
        fit = [slots[i] for i in kinds]
        if not fit:
            left += fs
            continue
        multi = [s for s in fit if s.multi]
        if multi and len(fit) == 1:
            s = multi[0]
            have = [] if s.empty() else [p.strip() for p in s.var.get().split(";") if p.strip()]
            s.var.set(join(have + [f for f in fs if f not in have]))
            placed += len(fs)
            continue
        if len(fs) >= 2:
            fs = sorted(fs, key=_mtime)
            if len(fs) > len(fit):
                left += fs[len(fit):]
                fs = fs[:len(fit)]
            if len(fs) == len(fit):                   # a full set: replace them all, oldest first
                for s, f in zip(fit, fs):
                    s.var.set(f)
                    used.add(id(s))
                placed += len(fs)
                continue
        for f in fs:
            free = [s for s in fit if s.empty() and id(s) not in used]
            home = [s for s in fit if s.prefer(f) and id(s) not in used]
            choice = (home and home[0].empty() and home[0]) or (free and free[0]) or (home and home[0]) \
                or next((s for s in reversed(fit) if id(s) not in used), None)
            if choice is None:
                left.append(f)
                continue
            choice.var.set(f)
            used.add(id(choice))
            placed += 1
    return placed, left


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
