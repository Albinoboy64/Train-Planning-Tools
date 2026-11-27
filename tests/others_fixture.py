"""Synthetic other operators' files (nothing real): a Network Rail CIF and an Attune XML with trains but no unit
diagrams, for the tasks that take other operators' trains."""


def _rec(text: str) -> str:
    assert len(text) <= 80, text
    return text.ljust(80)


def _t(hhmm: str) -> str:
    return hhmm.replace(":", "").ljust(5)


def schedule(uid, headcode, days, atoc, calls, stp="P", start="261213", end="270515"):
    """calls: [(tiploc, arr 'HHMM' or '', dep 'HHMM' or '', platform)]; the first is the origin, the last the
    destination."""
    out = [_rec(f"BSN{uid}{start}{end}{days}" + " " + "P" + "OO" + headcode + "    " + " " + "12345678" + " "
                + "EMU" + "    " + "100" + "      " + "S" + " " + " " + " " + "    " + "    " + " ").ljust(79)[:79]
           + stp,
           _rec("BX" + "    " + "     " + atoc)]
    for i, (tip, arr, dep, plat) in enumerate(calls):
        loc = tip.ljust(8)
        if i == 0:
            out.append(_rec("LO" + loc + _t(dep) + dep.replace(":", "").ljust(4) + plat.ljust(3)))
        elif i == len(calls) - 1:
            out.append(_rec("LT" + loc + _t(arr) + arr.replace(":", "").ljust(4) + plat.ljust(3)))
        else:
            out.append(_rec("LI" + loc + _t(arr) + _t(dep) + "     " + arr.replace(":", "").ljust(4)
                            + dep.replace(":", "").ljust(4) + plat.ljust(3)))
    return out


def make_cif(path, schedules, names=None):
    """A CIF file: header, TIPLOC names, the schedules, trailer."""
    lines = [_rec("HDTPS.UDFROC1.PD261201" + "011226" + "1200" + "DFROC1A" + "       " + "F" + "A" + "131226"
                  + "150527")]
    for tip, name in (names or {}).items():
        lines.append(_rec("TI" + tip.ljust(7) + "00" + "      " + " " + name.upper().ljust(26)))
    for s in schedules:
        lines += s
    lines.append(_rec("ZZ"))
    with open(path, "w", encoding="latin-1", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def southeastern_cif(path):
    """Southeastern (SE) trains at Victoria: 2T80 arrives on platform 3 at 23:50 every weekday and the unit forms
    1T05 at 05:40 the next morning; 2T10 turns round as 2T11 the same evening; 5T99 arrives in the carriage
    sidings (VICTCS road S1) on Saturdays and 5T98 leaves on Monday."""
    return make_cif(path, [
        schedule("Y10001", "2T80", "1111100", "SE", [("BROMLYS", "", "2300", ""), ("VICTRIC", "2350", "", "3")]),
        schedule("Y10002", "1T05", "1111100", "SE", [("VICTRIC", "", "0540", "3"), ("BROMLYS", "0620", "", "")]),
        schedule("Y10003", "2T10", "1111100", "SE", [("BROMLYS", "", "1800", ""), ("VICTRIC", "1830", "", "4")]),
        schedule("Y10004", "2T11", "1111100", "SE", [("VICTRIC", "", "1845", "4"), ("BROMLYS", "1925", "", "")]),
        schedule("Y10005", "5T99", "0000010", "SE", [("VICTRIC", "", "2310", "5"), ("VICTCS", "2320", "", "S1")]),
        schedule("Y10006", "5T98", "1000000", "SE", [("VICTCS", "", "0500", "S1"), ("VICTRIC", "0510", "", "5")]),
        schedule("Y10001", "2T80", "1111100", "SE", [("BROMLYS", "", "2300", ""), ("VICTRIC", "2355", "", "3")],
                 stp="O", start="261225", end="261225"),             # a one-day overlay: not the pattern
    ], {"VICTRIC": "London Victoria", "BROMLYS": "Bromley South", "VICTCS": "Victoria Carriage Sidings"})
