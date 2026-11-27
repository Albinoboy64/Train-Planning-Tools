"""Clock times as text, shared by every report: seconds or minutes after midnight shown as '05 34', '05+34',
'0534' or '05:34' (times past midnight wrap round to the next day's clock)."""
from __future__ import annotations

from typing import Optional

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
