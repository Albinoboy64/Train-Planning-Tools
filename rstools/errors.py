"""The errors the app's readers and engines raise with a message meant for the user (a file that cannot be read, a
choice that does not fit). The window shows these as they are; anything else is an unexpected error, written to the
error log (errorlog.describe). The classes are imported only when asked for, so the window opens quickly."""
from __future__ import annotations

from typing import Tuple


class LiveError(ValueError):
    """A Live View comparison that cannot be shown, with the reason (raised by rstools.live.adapters)."""


def user_errors() -> Tuple[type, ...]:
    """Every error class whose message is written for the user."""
    from cwn_compare.engine import RunError
    from cwn_compare.loader import LoadError
    from rstools.berthing.xmlread import BerthingError
    from rstools.stationbook import StationBookError
    from rstools.statspack.compare import PackReadError
    from rstools.statspack.engine import StatsPackError
    from rstools.statspack.trent import TrentFormatError
    from rstools.timetable.engine import TimetableRunError
    from rstools.timetable.parse import TimetableError
    from rstools.timetable.prints import PrintError
    from rstools.timetable.section4 import Section4Error
    from rstools.timetable.tpr import TPRError
    from rstools.timetable.trainlist import TrainListError
    return (RunError, LoadError, TimetableError, TimetableRunError, PrintError, TrainListError, StatsPackError,
            PackReadError, TrentFormatError, Section4Error, TPRError, BerthingError, StationBookError, LiveError)
