"""Clock times as text, shared by every report: seconds or minutes after midnight shown as '05 34', '05+34',
'0534' or '05:34' (times past midnight wrap round to the next day's clock)."""
from __future__ import annotations

from typing import List, Optional

DAY_SECONDS = 86400


def clock(sec: Optional[int], sep: str = ":") -> str:
    """Seconds after midnight as 'HH<sep>MM' ('' for a missing time)."""
    if sec is None:
        return ""
    sec %= DAY_SECONDS
    return f"{sec // 3600:02d}{sep}{sec % 3600 // 60:02d}"


def hhmm(minutes: Optional[int], sep: str = "") -> str:
    """Minutes after midnight as 'HH<sep>MM' ('' for a missing time)."""
    return "" if minutes is None else clock(int(minutes) * 60, sep)


def unroll(values: List[Optional[int]]) -> List[Optional[int]]:
    """Seconds after midnight in running order, continued past 24:00 so they always increase (a time more than six
    hours before the one before it is the next day's). Missing times stay None."""
    out: List[Optional[int]] = []
    base, last = 0, None
    for v in values:
        if v is None:
            out.append(None)
            continue
        v += base
        while last is not None and v < last - 6 * 3600:
            v += DAY_SECONDS
            base += DAY_SECONDS
        out.append(v)
        last = v
    return out
