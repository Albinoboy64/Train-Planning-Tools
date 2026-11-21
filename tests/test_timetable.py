"""Timing Tools: parsing, matching, the template output, train prints and train lists.

All inputs are small synthetic workbooks / prints built here (no real timetable data is stored)."""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATIONS = [("Brighton (BTN)", "d"), ("Haywards Heath (HHE)", "a"), ("", "d"), ("East Croydon (ECR)", "a"),
            ("London Bridge (LBG)", "a")]


def _nr_book(path, trains):
    """Network Rail layout: a page block per sheet, 'a' / 'd' markers, '0510' times, '. .' for none."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "OUT_K_D26_SX_14_12_2026"
    ws.append(["Table K_D26"])
    ws.append(["Brighton to London"])
    ws.append(["Mondays to Fridays"])
    ws.append(["Operator", None] + [t["op"] for t in trains])
    ws.append(["Train ID/Head Code", None] + [t["hc"] for t in trains])
    ws.append(["Notes", None] + [t.get("notes", "") for t in trains])
    name = ""
    for i, (station, role) in enumerate(STATIONS):
        name = station.replace(" (HHE)", "") if station else name
        ws.append([name if station or role == "d" and i == 2 else name, role]
                  + [t["times"][i] or ". ." for t in trains])
    notes = wb.create_sheet("OUT_K_D26_SX_14_12_2026_Notes")
    notes.append(["A", "From Littlehampton to London Bridge"])
    wb.save(path)


def _gtr_book(path, trains):
    """GTR layout: TID / TOC / Day of Operation rows, 'arr' / 'dep', '05 10' times, blank = same station."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "OT SNGX TT Checks K - OUT SX"
    ws.append(["TID", None, None] + [t["hc"] for t in trains])
    ws.append(["TOC", None, None] + [t["op"] for t in trains])
    ws.append(["Day of Operation", None, None] + [t.get("days", "SX") for t in trains])
    for i, (station, role) in enumerate(STATIONS):
        ws.append([station.split(" (")[0] if station else None, "arr" if role == "a" else "dep", i + 1]
                  + [(t["times"][i][:2] + " " + t["times"][i][2:]) if t["times"][i] else "....." for t in trains])
    wb.save(path)


def _books(d):
    nr = [dict(op="SN", hc="1A01", times=["0500", "0520", "0521", "0540", "0555"], notes="A"),
          dict(op="SN", hc="1A02", times=["0600", "0620", "0621", "0640", "0655"]),
          dict(op="SN", hc="1A03", times=["0700", "0720", "0721", "0740", "0755"]),
          dict(op="SN", hc="1A04", times=["0800", "0820", "0821", "0840", "0855"]),
          dict(op="LO", hc="2X10", times=["0900", "0920", "0921", "0940", "0955"]),
          dict(op="TL", hc="9A05", times=["1000", "1020", "1021", "1040", "1055"])]
    gtr = [dict(op="SN", hc="1A01BT", times=["0500", "0520", "0521", "0540", "0555"]),
           dict(op="SN", hc="1A02BT", times=["0600", "0620", "0621", "0640", ""]),        # London Bridge missing
           dict(op="SN", hc="1A03BT", times=["0700", "0720", "0721", "0742", "0755"]),    # East Croydon 2 late
           dict(op="TL", hc="9B05ET", times=["1000", "1020", "1021", "1040", "1055"])]    # other headcode
    _nr_book(os.path.join(d, "nr.xlsx"), nr)
    _gtr_book(os.path.join(d, "gtr.xlsx"), gtr)
    return os.path.join(d, "gtr.xlsx"), os.path.join(d, "nr.xlsx")


def test_times_and_headcodes():
    from rstools.timetable.parse import norm_headcode, norm_loc, norm_time
    assert [norm_time(v) for v in ("0634a", "06a34", "a0634", "05 10", "0510", ". .", ".....", "2460", None)] == \
        ["0634", "0634", "0634", "0510", "0510", None, None, None, None]
    assert norm_time(dt.time(6, 5)) == "0605" and norm_time(0.25) == "0600"
    assert norm_headcode("9R00ET") == "9R00" and norm_headcode("XX") == ""
    assert norm_loc("London Bridge (LBG)") == norm_loc("  london bridge ") == "london bridge"


def test_parse_and_compare():
    from rstools.timetable.compare import ISSUE_MISSING, ISSUE_TIME, compare_timetables
    from rstools.timetable.parse import read_timetable
    with tempfile.TemporaryDirectory() as d:
        g_path, n_path = _books(d)
        gtr, nr = read_timetable(g_path), read_timetable(n_path)
    assert nr.identifier == "K_D26" and gtr.identifier == ""
    assert [t.headcode for t in nr.sections["OUT SX"]] == ["1A01", "1A02", "1A03", "1A04", "2X10", "9A05"]
    first = nr.sections["OUT SX"][0]
    assert (first.origin, first.destination) == ("Littlehampton", "London Bridge")
    assert [e.role for e in first.events] == ["dep", "arr", "dep", "arr", "arr"]
    cmp = compare_timetables(gtr, nr)
    res = cmp.sections[0]
    assert res.section == "OUT SX" and res.out_of_scope == 1                  # the LO train
    assert [m.nr.headcode for m in res.missing] == ["1A04"]
    issues = {(m.nr.headcode, i.location, i.summary) for m in res.matched for i in m.issues}
    assert issues == {("1A02", "London Bridge (LBG)", ISSUE_MISSING), ("1A03", "East Croydon (ECR)", ISSUE_TIME)}
    assert [(m.nr.headcode, m.gtr.headcode) for m in res.headcode_mismatches] == [("9A05", "9B05")]
    assert res.compared + res.not_compared == res.cells and res.not_compared == 5     # 1A04's five times


def test_template_output_and_formats():
    import openpyxl
    from rstools.timetable.engine import run
    SHEETS = ("Summary", "Issues", "Missing Trains", "Headcode Mismatches", "Service Group Review", "Match Audit",
              "Audit Totals")
    with tempfile.TemporaryDirectory() as d:
        g_path, n_path = _books(d)
        res = run("timetables", [g_path], [n_path], d)
        assert os.path.basename(res.path) == "K_D26 Consolidated TT Comparison.xlsx"
        wb = openpyxl.load_workbook(res.path)
        assert tuple(wb.sheetnames) == SHEETS
        summary = [c.value for c in wb["Summary"][2]]
        assert summary == ["OUT SX", 5, 4, 4, 1, 0, 2, 1, "Differences found"]
        assert wb["Summary"]["B3"].value == "-"                                   # section not in the files
        assert wb["Summary"]["A8"].value == "All sections"
        assert wb["Missing Trains"]["C2"].value == "1A04"
        assert wb["Headcode Mismatches"]["B2"].value == "9A05"
        audit = [c.value for c in wb["Audit Totals"][2]]
        assert audit[1] == audit[2] + audit[3] and audit[4].startswith("Not complete")
        for fmt in ("pdf", "docx"):
            out = run("timetables", [n_path], [g_path], d, fmt=fmt)               # swapped: put right
            assert out.path.endswith("." + fmt) and os.path.getsize(out.path) > 1000
            assert any("swapped" in w for w in [out.lines[0]] + out.warnings) or out.differences == res.differences


def test_train_prints():
    from rstools.timetable.prints import compare_prints, parse_pages
    page = ["Train 1A23   UID C12345   SX", "Location            Arr    Dep    Plat  Line",
            "Brighton                   0510   4     FL", "Haywards Heath      0525   0526   2     FL",
            "East Croydon        0545   0546   3     FL", "London Bridge       0558          5",
            "Page 1 of 1", "Train 1A25   UID C12346   SX", "Location            Arr    Dep    Plat",
            "Brighton                   0610   4", "London Bridge       0658          5"]
    before = parse_pages([page], "a.pdf")
    after_page = list(page)
    after_page[4] = "East Croydon        0547   0548   3     FL"      # retimed
    after_page[3] = "Haywards Heath      0525   0526   1     FL"      # platform change
    del after_page[7:]                                                # 1A25 removed
    after = parse_pages([after_page], "b.pdf")
    assert [t.label() for t in before] == ["1A23 C12345", "1A25 C12346"]
    assert before[0].calls[0].times == {"dep": "0510"} and before[0].calls[3].times == {"arr": "0558"}
    cmp = compare_prints(before, after)
    assert [t.label() for t in cmp.removed] == ["1A25 C12346"] and not cmp.added
    kinds = sorted((c.location, c.change) for c in cmp.changes)
    assert kinds == [("East Croydon", "Arrival time changed"), ("East Croydon", "Departure time changed"),
                     ("Haywards Heath", "Call details changed (platform, line, activity...)")]


def test_train_prints_word_and_pdf():
    from rstools.docexport import Section, write_docx, write_pdf
    from rstools.timetable.engine import run
    rows = [["Brighton (BTN)", "", "0500", "4"], ["Gatwick Airport", "0526", "0527", "5"],
            ["London Bridge", "0553", "", "6"]]
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "old.docx"), os.path.join(d, "new.pdf")
        write_docx(a, "Prints", [Section("Train 1A00  UID C12340  SX", ["Location", "Arr", "Dep", "Plat"], rows)])
        rows[1] = ["Gatwick Airport", "0528", "0529", "5"]
        write_pdf(b, "Prints", [Section("Train 1A00  UID C12340  SX", ["Location", "Arr", "Dep", "Plat"], rows)])
        res = run("prints", [a], [b], d)
        assert res.differences == 2 and res.path.endswith("Train Print Comparison.xlsx")


def test_train_lists():
    import openpyxl
    from rstools.timetable.trainlist import compare_train_lists, read_train_list
    with tempfile.TemporaryDirectory() as d:
        for v in (1, 2):
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["Attune export"])
            ws.append(["Headcode", "UID", "Days", "Origin", "Origin Dep", "Destination", "Class"])
            for i in range(5):
                dep = dt.time(6, 10 * i + (3 if v == 2 and i == 1 else 0))
                if not (v == 2 and i == 4):
                    ws.append([f"1A0{i}", f"C1000{i}", "SX", "Brighton", dep, "Bedford", 377 if i != 2 or v == 1
                               else 700])
            if v == 2:
                ws.append(["2B00", "D20000", "SO", "Horsham", "07:15", "Victoria", 377])
            ws.append(["Total", None, None, None, None, None, None])
            wb.save(os.path.join(d, f"l{v}.xlsx"))
        a, b = read_train_list(os.path.join(d, "l1.xlsx")), read_train_list(os.path.join(d, "l2.xlsx"))
    assert a.header_row == 2 and len(a.rows) == 5 and a.rows[1][4] == "0610"
    cmp = compare_train_lists(a, b)
    assert [b.rows[j][0] for j in cmp.added] == ["2B00"] and [a.rows[i][0] for i in cmp.removed] == ["1A04"]
    assert [(h, old, new) for _i, _j, h, old, new in cmp.changes] == [("Origin Dep", "0610", "0613"),
                                                                      ("Class", "377", "700")]


def test_train_lists_without_uid_pair_retimed_trains():
    """No UID column: trains pair by headcode, days, departure and origin. A retimed train is a time
    change when it is the only one left with its headcode, days and origin (never a guess between two),
    and an LTP row and its STP twin with the same key keep to their own stage when the export is re-sorted."""
    import openpyxl
    from rstools.timetable.trainlist import compare_train_lists, read_train_list
    heads = ["Stage", "Headcode", "Days", "Origin", "Work Dep", "Destination", "Stock"]
    first = [["LTP Published", "1A08", "SX", "Victoria", dt.time(9, 0), "Brighton", "377"],
             ["STP", "1A08", "SX", "Victoria", dt.time(9, 0), "Brighton", "387"],
             ["LTP Published", "2B10", "SX", "Horsham", dt.time(7, 15), "Victoria", "377"],
             ["LTP Published", "5C20", "SO", "Selhurst", dt.time(5, 0), "Norwood", "377"],
             ["LTP Published", "5C20", "SO", "Selhurst", dt.time(6, 0), "Norwood", "377"]]
    second = [first[1], first[0],                                       # re-sorted twins
              ["LTP Published", "2B10", "SX", "Horsham", dt.time(7, 16), "Victoria", "377"],   # retimed
              ["LTP Published", "5C20", "SO", "Selhurst", dt.time(5, 5), "Norwood", "377"],    # two left over:
              ["LTP Published", "5C20", "SO", "Selhurst", dt.time(6, 5), "Norwood", "377"]]    # not guessed
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for n, rows in enumerate((first, second)):
            wb = openpyxl.Workbook()
            wb.active.append(heads)
            for r in rows:
                wb.active.append(r)
            paths.append(os.path.join(d, f"l{n}.xlsx"))
            wb.save(paths[-1])
        a, b = read_train_list(paths[0]), read_train_list(paths[1])
    assert "uid" not in a.roles
    cmp = compare_train_lists(a, b)
    assert [(h, old, new) for _i, _j, h, old, new in cmp.changes] == [("Work Dep", "0715", "0716")]
    assert cmp.retimed == 1 and cmp.loose_headers == ["Headcode", "Days", "Origin"]
    assert sorted(a.rows[i][4] for i in cmp.removed) == ["0500", "0600"]
    assert sorted(b.rows[j][4] for j in cmp.added) == ["0505", "0605"]


def test_damaged_workbooks_give_plain_messages():
    """A workbook with a damaged sheet inside gives the reader's own plain message, never a raw XML error."""
    import zipfile
    import openpyxl
    from rstools.timetable.parse import TimetableError, read_timetable
    from rstools.timetable.trainlist import TrainListError, read_train_list
    with tempfile.TemporaryDirectory() as d:
        good, bad = os.path.join(d, "good.xlsx"), os.path.join(d, "bad.xlsx")
        wb = openpyxl.Workbook()
        wb.active.append(["Headcode", "Days", "Origin", "Work Dep"])
        for i in range(50):
            wb.active.append([f"1A{i:02d}", "SX", "Brighton", "0600"])
        wb.save(good)
        with zipfile.ZipFile(good) as zi, zipfile.ZipFile(bad, "w") as zo:
            for it in zi.infolist():
                data = zi.read(it.filename)
                zo.writestr(it.filename, data[:len(data) // 2] if it.filename.startswith("xl/worksheets/") else data)
        for reader, error in ((read_train_list, TrainListError), (read_timetable, TimetableError)):
            try:
                reader(bad)
            except error as exc:
                assert "damaged" in str(exc) and "bad.xlsx" in str(exc) and d not in str(exc)
            else:
                raise AssertionError(f"{reader.__name__} accepted a damaged workbook")


def test_settings_carried_over():
    from rstools import branding
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "RollingStockTools"))
        with open(os.path.join(d, "RollingStockTools", "settings.json"), "w") as fh:
            fh.write('{"theme": "dark"}')
        env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        try:
            path = branding.settings_dir()
        finally:
            if env is None:
                del os.environ["LOCALAPPDATA"]
            else:
                os.environ["LOCALAPPDATA"] = env
        with open(os.path.join(path, "settings.json")) as fh:
            assert "dark" in fh.read()


# ------------------------------------------------------------------ Attune Single Train Report as the base
ROW_FMT = "{:<14}{:<25}{:<9}{:<10}{:<7}{:<8}{:<7}{:<10}{:<7}{:<6}"


def _attune_lines(trains):
    """Synthetic Attune 'Single Train Report' pages (same layout as the real print)."""
    pages = []
    for t in trains:
        lines = ["Generated on 06/10/2026, 10:33:11", "Timetable: May 2027 PDNS", "Single Train Report",
                 f"Train: XX {t['id']}(ET) {t['days']} [ET/24746000] Greater Thameslink Railway (Southern)",
                 f"TrainID:      {t['id']}       Train Class:     1       Train Category:   XX",
                 f"SignalID:     {t['id'][:4]}         TOC TrainID:             Train UID:",
                 f"From:         17/05/2027     Until:     10/12/2027     Days Pattern      {t['days']}",
                 " Location     Location Name            Working Times     Public Times  Dwell  Activity   Line",
                 "                                       Arr      Dep       Arr    Dep                   Plat  Line"]
        for tip, name, wa, wd, pa, pd, dwell, act, plat in t["rows"]:
            lines.append(ROW_FMT.format(tip, name, wa, wd, pa, pd, dwell, act, plat, "").rstrip())
        pages.append(lines)
    return pages


ATTUNE = [
    dict(id="1H05BS", days="SX", rows=[
        ("BTN", "Brighton", "05.08", "05.37", "", "05.37", "29:00", "TB", "3"),
        ("KEYMERJ", "Keymer Jn", "", "05/41", "", "", "/", "", ""),
        ("HYWRDSH", "Haywards Heath", "05a52½", "05p53½", "05.53", "05.53", "1:00", "T", "4"),
        ("ECROYDN", "East Croydon", "06a18½", "06.20", "06.19", "06.20", "1:30", "T", "1"),
        ("VICTRIC", "London Victoria", "06.37", "06.54", "06.37", "", "17:00", "TF", "18")]),
    dict(id="5H07BV", days="FSX", rows=[
        ("BTN", "Brighton", "", "07.00", "", "", "", "TB", "2"),
        ("LOVERSW", "Lovers Walk", "07.05", "", "", "", "", "TF", "")]),
]


def test_attune_print_continuation_pages_and_unreadable_lines():
    """A train's heading repeated at the top of the next page continues the train; the same heading twice on
    one page is two trains; a line with a time printed on to the station name is reported, not dropped silently."""
    from rstools.timetable.attune_print import parse_attune, skipped_note
    first, second = _attune_lines(ATTUNE[:1])[0], _attune_lines(ATTUNE[:1])[0]
    head, rows = second[:9], second[9:]
    # one train over two pages: the second page repeats the heading, then the rest of the rows
    split = [first[:9] + first[9:11], head + rows[2:]]
    trains = parse_attune(split)
    assert len(trains) == 1 and len(trains[0].rows) == 5
    # two identical headings on one page: two trains
    trains = parse_attune([first + second])
    assert len(trains) == 2 and [len(t.rows) for t in trains] == [5, 5]
    assert skipped_note(trains) == ""
    bad = first[:9] + [first[9], "BRGHTN       Littlehampton 05.08", *first[10:]]
    trains = parse_attune([bad])
    assert trains[0].skipped and "Littlehampton 05.08" in trains[0].skipped[0]
    note = skipped_note(trains)
    assert note.startswith("1 location line(s)") and "1H05BS" in note


def write_attune_pdf(path, trains=ATTUNE):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=A4)
    for lines in _attune_lines(trains):
        for i, line in enumerate(lines):
            c.setFont("Courier", 6.5)
            c.drawString(20, 800 - 10 * i, line)
        c.showPage()
    c.save()


def test_attune_print_reader():
    from rstools.timetable.attune_print import is_attune_report, parse_attune
    pages = _attune_lines(ATTUNE)
    assert is_attune_report(pages)
    t, ecs = parse_attune(pages, "p.pdf")
    assert (t.train_id, t.headcode, t.days, t.operator, t.public) == ("1H05BS", "1H05", "SX", "SN", True)
    assert not ecs.public and ecs.days == "FSX"
    hh = t.rows[2]
    assert hh.values["wtt_arr"] == "05a52½" and hh.values["pub_arr"] == "05.53" and hh.values["dwell"] == "1:00"
    assert t.rows[0].values.get("pub_dep") == "05.37" and "pub_arr" not in t.rows[0].values   # dwell is no time
    assert t.rows[1].values["pass"] == "05/41"


def test_attune_print_pdf_round_trip():
    from rstools.timetable.prints import read_print
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "print.pdf")
        write_attune_pdf(path)
        trains = read_print(path)
    assert [t.label() for t in trains] == ["1H05BS", "5H07BV"]
    assert trains[0].calls[2].times == {"wtt_arr": "05a52½", "wtt_dep": "05p53½", "pub_arr": "05.53",
                                        "pub_dep": "05.53"}


def _gtr_from(trains, path, edit=None):
    """A GTR-layout timetable holding the base trains' public times (edit(train_index, station, role, time))."""
    import openpyxl
    names = list(dict.fromkeys(r[1] for t in trains for r in t["rows"]))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "OT SNGX TT Checks X - OUT SX"
    ws.append(["TID", None, None] + [t["id"] for t in trains])
    ws.append(["TOC", None, None] + ["SN" for _t in trains])
    ws.append(["Day of Operation", None, None] + [t["days"] for t in trains])
    for name in names:
        for role, i in (("arr", 4), ("dep", 5)):
            cells = []
            for n, t in enumerate(trains):
                row = next((r for r in t["rows"] if r[1] == name), None)
                v = row[i].replace(".", "") if row and row[i] and "." in row[i] else ""
                v = edit(n, name, role, v) if edit else v
                cells.append(f"{v[:2]} {v[2:]}" if v else ".....")
            ws.append([name if role == "arr" else None, role, None] + cells)
    wb.save(path)


def test_print_against_timetable():
    from rstools.timetable.engine import run
    with tempfile.TemporaryDirectory() as d:
        pdf = os.path.join(d, "print.pdf")
        write_attune_pdf(pdf)
        exact, wrong = os.path.join(d, "exact.xlsx"), os.path.join(d, "wrong.xlsx")
        _gtr_from(ATTUNE[:1], exact)
        _gtr_from(ATTUNE[:1], wrong, lambda n, s, r, v: {("East Croydon", "dep"): "0621",
                                                       ("Haywards Heath", "arr"): ""}.get((s, r), v))
        env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        try:
            ok = run("print_tt", [pdf], [exact], d, name="ok")
            bad = run("print_tt", [pdf], [wrong], d, name="bad")
        finally:
            if env is None:
                del os.environ["LOCALAPPDATA"]
            else:
                os.environ["LOCALAPPDATA"] = env
        assert ok.differences == 0, ok.lines                       # no false positives
        assert any("no public times" in w for w in ok.warnings)     # the empty-stock train is explained
        import openpyxl
        issues = [r for r in openpyxl.load_workbook(bad.path)["Issues"].iter_rows(min_row=2, values_only=True)]
        assert [(r[4], r[5], r[6], r[7], r[8]) for r in issues] == [
            ("Haywards Heath", "Arr", "0553", "-", "Time/location missing"),
            ("East Croydon", "Dep", "0620", "0621", "Time mismatch")]
        headers = [c.value for c in openpyxl.load_workbook(bad.path)["Issues"][1]]
        assert headers[1:3] == ["Print headcode", "GTR headcode"]


def test_list_against_timetable():
    import openpyxl
    from rstools.timetable.engine import run
    with tempfile.TemporaryDirectory() as d:
        lst = os.path.join(d, "list.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["TrainID", "SignalID", "Days Pattern", "Origin Loc", "Origin Time", "Destination Loc",
                   "Destination Time"])
        ws.append(["1H05BS", "1H05", "SX", "Brighton", "05:37", "London Victoria", "06:37"])
        ws.append(["5H07BV", "5H07", "FSX", "Brighton", "07:00", "Lovers Walk", "07:05"])      # empty stock
        ws.append(["1H09BS", "1H09", "SX", "Brighton", "06:40", "London Victoria", "07:40"])   # not in timetable
        wb.save(lst)
        tt = os.path.join(d, "tt.xlsx")
        _gtr_from(ATTUNE[:1], tt)
        env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        try:
            res = run("list_tt", [lst], [tt], d)
        finally:
            if env is None:
                del os.environ["LOCALAPPDATA"]
            else:
                os.environ["LOCALAPPDATA"] = env
        assert res.differences == 1 and any("empty-stock" in w for w in res.warnings)
        missing = [r for r in openpyxl.load_workbook(res.path)["Missing Trains"].iter_rows(min_row=2,
                                                                                          values_only=True)]
        assert [(r[0], r[2]) for r in missing] == [("Missing from GTR", "1H09")]


def test_role_rule_and_days():
    from rstools.timetable.compare import ISSUE_DEP_FOR_ARR, ISSUE_MISSING, _issues, _index, parse_days
    from rstools.timetable.parse import Event, TTrain
    base = [Event("hove", "Hove", "arr", "0615", ""), Event("hove", "Hove", "dep", "0616", "")]
    shown = TTrain("", "1H05", "", "SN", "SX", "", 0, [Event("hove", "Hove", "dep", "0616", "")])
    assert [i.summary for i in _issues(base, _index(shown))] == [ISSUE_MISSING]       # its own dep is right
    terminating = [Event("cyp", "Crystal Palace", "arr", "0700", "")]
    other = TTrain("", "1A01", "", "SN", "SX", "", 0, [Event("cyp", "Crystal Palace", "dep", "0700", "")])
    assert [i.summary for i in _issues(terminating, _index(other))] == [ISSUE_DEP_FOR_ARR]
    assert parse_days("MSX") == {1, 2, 3, 4} and parse_days("TThO") == {1, 3} and parse_days("XYZ") is None


def test_train_on_next_days_sheet():
    """A timetable that shows an after-midnight SX train on its SO sheet: compared there, not 'missing'."""
    import openpyxl
    from rstools.timetable.base import build_base, trains_from_prints
    from rstools.timetable.attune_print import parse_attune
    from rstools.timetable.compare import compare_timetables
    from rstools.timetable.parse import read_timetable
    with tempfile.TemporaryDirectory() as d:
        tt = os.path.join(d, "tt.xlsx")
        _gtr_from(ATTUNE[:1], tt)
        wb = openpyxl.load_workbook(tt)
        wb.active.title = "OT SNGX TT Checks X - OUT SO"
        wb.save(tt)
        other = read_timetable(tt)
    trains, notes = trains_from_prints(parse_attune(_attune_lines(ATTUNE)))
    base = build_base(trains, other, "p.pdf", "P", notes)
    assert list(base.sections) == ["OUT SO"] and any("another section" in w for w in base.warnings)
    res = compare_timetables(other, base, base_label="Print").sections
    assert [(r.section, len(r.matched), len(r.missing)) for r in res] == [("OUT SO", 1, 0)]


def test_fast_pdf_reader_matches_pypdf():
    """Attune prints are read with PDFium (much quicker); it must read them as pypdf does."""
    import pickle
    import importlib.util
    if importlib.util.find_spec("pypdfium2") is None:
        return
    from rstools.timetable import prints
    from rstools.timetable.attune_print import PlacedLine, parse_attune
    with tempfile.TemporaryDirectory() as d:
        pdf = os.path.join(d, "a.pdf")
        write_attune_pdf(pdf)
        fast = prints._pdfium_lines(pdf)
        assert fast and isinstance(fast[0][0], PlacedLine)
        from pypdf import PdfReader
        slow = [prints._page_text(p) for p in PdfReader(pdf).pages]
        a, b = parse_attune(fast), parse_attune(slow)
        assert [(t.train_id, t.days, t.fields) for t in a] == [(t.train_id, t.days, t.fields) for t in b]
        assert [[(r.tiploc, r.name, r.values) for r in t.rows] for t in a] == \
               [[(r.tiploc, r.name, r.values) for r in t.rows] for t in b]
        line = fast[0][-1]
        copy = pickle.loads(pickle.dumps(line))             # sent between helper processes
        assert copy == line and copy.spans == line.spans
        with open(os.path.join(d, "x.pdf"), "wb") as fh:   # not an Attune report: the pypdf reader is used
            fh.write(b"%PDF-1.4 broken")
        assert prints._pdfium_lines(os.path.join(d, "x.pdf")) is None


def test_half_minutes_kept_unless_compared_with_whole_minutes():
    import datetime as dt
    from rstools.timetable.base import trains_from_prints
    from rstools.timetable.attune_print import parse_attune
    from rstools.timetable.compare import compare_timetables
    from rstools.timetable.parse import Event, Timetable, TTrain, has_halves, norm_time, public_time
    assert norm_time("0634½") == "0634½" and norm_time("0634H") == "0634½" and norm_time("0634") == "0634"
    assert norm_time(dt.time(6, 34, 30)) == "0634½" and norm_time((6 * 60 + 34.5) / 1440) == "0634½"
    assert public_time("0634½", "dep") == "0634" and public_time("0634½", "arr") == "0635"

    def tt(times, ident=""):
        ev = [Event("brighton", "Brighton", "dep", times[0], times[0]),
              Event("london victoria", "London Victoria", "arr", times[1], times[1])]
        t = TTrain("OUT SX", "1A01", "1A01", "SN", "SX", "", 0, ev, "Brighton", "London Victoria")
        return Timetable("x", ident, {"OUT SX": [t]}, {"OUT SX": [("brighton", "dep"), ("london victoria", "arr")]}, [])

    half_a, half_b = tt(["0600½", "0700½"]), tt(["0600½", "0701"])
    assert has_halves(half_a)
    cmp = compare_timetables(half_a, half_b)             # both working timetables: the half minute counts
    issues = [i for r in cmp.sections for m in r.matches for i in m.issues]
    assert [(i.nr_time, i.gtr_time) for i in issues] == [("0701", "0700½")]
    cmp = compare_timetables(tt(["0600½", "0700½"]), tt(["0600", "0701"], "K_D26"))   # against a public one
    issues = [i for r in cmp.sections for m in r.matches for i in m.issues]
    assert issues == [] and any("rounded to whole public minutes" in w for w in cmp.warnings)

    trains = parse_attune(_attune_lines(ATTUNE))
    public, _n = trains_from_prints(trains)
    working, _n = trains_from_prints(trains, working=True)
    hh_pub = [e.time for e in public[0].events if e.name == "Haywards Heath"]
    hh_wtt = [e.time for e in working[0].events if e.name == "Haywards Heath"]
    assert hh_pub == ["0553", "0553"] and hh_wtt == ["0552½", "0553½"]
    assert any(e.name == "Keymer Jn" for e in working[0].events)          # a passing time: working only


def test_attune_train_list_columns():
    """Attune's own export: 'Work Dep' / 'Work Arr' / 'Stage' columns are recognised, bus IDs are kept and the
    record-keeping columns (Last Update, Lock Id...) are listed but never compared."""
    import openpyxl
    from rstools.timetable.trainlist import compare_train_lists, read_train_list
    with tempfile.TemporaryDirectory() as d:
        for v in (1, 2):
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append([None, "Stage", "Headcode", "Origin", "Work Dep", "Destination", "Work Arr", "Days",
                       "Last Update", "Last Updated By", "Lock Id"])
            ws.append([None, "LTP Published", "1A08BU", "VICTRIC", dt.time(9, 0), "BRGHTN", dt.time(10, 5), "SX",
                       f"2026-0{v}-01", f"user{v}", v])
            ws.append([None, "STP", "BHQ200", "CAMBDGE", dt.time(4, 53), "ROYSTON",
                       dt.time(5, 33 if v == 1 else 40), "Su", None, None, None])
            wb.save(os.path.join(d, f"l{v}.xlsx"))
        a, b = read_train_list(os.path.join(d, "l1.xlsx")), read_train_list(os.path.join(d, "l2.xlsx"))
    assert len(a.rows) == 2 and {"origin_time", "dest_time", "stp"} <= set(a.roles)
    cmp = compare_train_lists(a, b)
    assert [(h, old, new) for _i, _j, h, old, new in cmp.changes] == [("Work Arr", "0533", "0540")]
    assert cmp.ignored == ["Last Update", "Last Updated By", "Lock Id"]


def test_section4_windows_sections_and_check():
    """Section 4: windows ('0140 T-F to 0350 T-F'), section names, cells holding two possessions, and the check of
    an Attune XML: a train over both ends of a section inside a window clashes; outside it, or on a line left open
    in its direction, it does not."""
    from datetime import date
    from rstools import stationbook as SB
    from rstools.timetable import section4 as S4
    w = S4.parse_windows("0140 T-F to 0350 T-F")
    assert [x.text for x in w] == ["0140 Tue to 0350 Tue", "0140 Wed to 0350 Wed", "0140 Thu to 0350 Thu",
                                   "0140 Fri to 0350 Fri"]
    assert [(x.start, x.end) for x in S4.parse_windows("2340 T to 0540 W")] == [(1440 + 1420, 2880 + 340)]
    assert S4.parse_windows("2350 Sat to 0750 Sun")[0].text == "2350 Sat to 0750 Sun"
    assert S4._section("Shepherds Lane Jn and Herne Hill 110.3") == ("Shepherds Lane Jn and Herne Hill", "110.3",
                                                                     ("Shepherds Lane Jn", "Herne Hill"))
    name, num, ends = S4._section("London Bridge and Bricklayers Arms Jn and New Cross Jn 130.5a Thameslink Lines")
    assert num == "130.5a" and ends == ("London Bridge", "New Cross Jn") and "Thameslink Lines" in name
    segs = S4._segments_of("2350 Sat to 0750 Sun Fast Lines BLOCKED or 0150 Sun to 0750 Sun Slow Lines BLOCKED")
    assert [(len(ws), b) for ws, b in segs] == [(1, "Fast Lines BLOCKED"), (1, "Slow Lines BLOCKED")]
    assert "London Victoria (Eastern)" in S4._alternatives("Victoria Eastern")
    assert "Holloway" in S4._alternatives("Holloway (Excl.)")
    # a timetable: 1A01 Alpha 01:50 -> Beta 02:10 Tue-Fri (Down); 1A02 Beta 02:00 -> Alpha 02:20 (Up); 1A03 at 05:00
    d = tempfile.mkdtemp()
    x = os.path.join(d, "plan.xml")

    def tr(tid, a, t1, b, t2):
        return (f'<train id="{tid}" daysRun="NNNYYYYNN" planType="L" validFrom="2026-12-13" validUntil="2027-05-15">'
                f'<leg origin="{a}" dep="{t1}" dest="{b}" arr="{t2}" depPlat="1" arrPlat="1"/></train>')
    with open(x, "w", encoding="utf-8") as fh:
        fh.write('<diagramExchange xmlns="http://www.tracsis.com/TTVP_Interface" version="1.0" plantype="L" '
                 'startdate="2026-12-13" enddate="2027-05-15"><trainList>'
                 + tr("1A01XX", "AAA", "01:50:00", "BBB", "02:10:00")
                 + tr("1A02XX", "BBB", "02:00:00", "AAA", "02:20:00")
                 + tr("1A03XX", "AAA", "05:00:00", "BBB", "05:20:00")
                 + '</trainList><locationList><location tiploc="AAA" longDesc="Alpha"/>'
                 '<location tiploc="BBB" longDesc="Beta Jn"/></locationList></diagramExchange>')
    plan = SB.read_plan(x)
    per = S4.Period("Periods A and B", date(2026, 12, 13), date(2027, 2, 14))
    later = S4.Period("Periods E to G", date(2027, 5, 16), date(2027, 10, 2))
    both = S4.Possession("XX100 TEST", "Alpha and Beta Junction", "100.1", ("Alpha", "Beta Junction"), "MID WEEK",
                         [per, later], S4.parse_windows("0140 T-F to 0350 T-F"), "Down and Up BLOCKED", "", "t")
    down = S4.Possession("XX100 TEST", "Alpha and Beta Junction", "100.2", ("Alpha", "Beta Junction"), "MID WEEK",
                         [per], S4.parse_windows("0140 T-F to 0350 T-F"), "Down Slow BLOCKED", "", "t")
    gone = S4.Possession("XX100 TEST", "Gamma and Alpha", "100.3", ("Gamma", "Alpha"), "WEEK END", [per],
                         S4.parse_windows("0100 Sun to 0600 Sun"), "BLOCKED", "", "t")
    res = S4.check(plan, S4.Statement([both, down, gone]))
    got = sorted((c.possession.number, c.train, c.direction) for c in res.clashes)
    assert ("100.1", "1A01XX", "Down") in got and ("100.1", "1A02XX", "Up") in got
    assert not any(t == "1A03XX" for _n, t, _d in got)                 # after the window
    assert ("100.2", "1A02XX", "Up") not in got and ("100.2", "1A01XX", "Down") in got     # only Down blocked
    assert not any(c.period is later for c in res.clashes)            # the XML ends before that period
    assert res.not_found == {"Gamma": ["100.3 Gamma and Alpha"]}
    assert both.every_line and not down.every_line and down.direction == "Down"
    assert {c.day for c in res.clashes if c.train == "1A01XX" and c.possession.number == "100.1"} == {1, 2, 3, 4}
    wb = S4.build_workbook(res, S4.Statement([both, down, gone], ["eas.pdf"]), x)
    assert wb.sheetnames == ["Summary", "Clashes", "By Section", "Not Checked", "What Was Compared"]


def test_rules_sets_reminder_and_timetables(monkeypatch):
    """Rule sets: added (only what the check needs, compressed, in the settings folder), switched and removed;
    the new-timetable reminder comes once per timetable from Dec 27; out-of-date rules are flagged."""
    from datetime import date
    from rstools import rules
    from rstools.timetable import section4 as S4
    assert rules.change_dates(2026)[1] == date(2026, 12, 13) and rules.change_dates(2027) == (date(2027, 5, 16),
                                                                                           date(2027, 12, 12))
    assert [rules.timetable_of(date(*d)) for d in ((2027, 12, 11), (2027, 12, 12), (2028, 6, 1), (2028, 1, 5))] == [
        "MAY27", "DEC27", "MAY28", "DEC27"]
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        monkeypatch.setattr(rules, "_dir", lambda: os.makedirs(os.path.join(d, "rules"), exist_ok=True) or
                            os.path.join(d, "rules"))
        assert rules.new_timetable_reminder("2027-05-16") is None              # before Dec 27: no reminder
        first = rules.new_timetable_reminder("2027-12-12")
        assert first and "DEC27" in first and rules.RULES_URL in first
        assert rules.new_timetable_reminder("2027-12-20") is None              # same timetable: once only
        assert "MAY28" in rules.new_timetable_reminder("2028-05-21")
        per = S4.Period("Periods A and B", date(2026, 12, 13), date(2027, 2, 14))
        pos = S4.Possession("XX1 TEST", "A and B", "1.1", ("A", "B"), "WEEK END", [per],
                            S4.parse_windows("0100 Sun to 0600 Sun"), "BLOCKED", "", "t")
        monkeypatch.setattr(S4, "read_statement", lambda pdfs, log=None: S4.Statement([pos], list(pdfs)))
        rules.add_section4_set("EAS 2027 v4", ["/x/KS.pdf"])
        rules.add_section4_set("EAS 2028 v1", ["/x/KS2.pdf"])
        assert [s["name"] for s in rules.list_sets() if s["active"]] == ["EAS 2028 v1"]     # the newest is in use
        rules.use_set("EAS 2027 v4")
        st = rules.load_set()
        assert rules.active_set_info()["name"] == "EAS 2027 v4" and len(st.possessions) == 1
        p = st.possessions[0]
        assert (p.number, p.ends, p.periods[0].start, p.windows[0].text) == ("1.1", ("A", "B"), date(2026, 12, 13),
                                                                           "0100 Sun to 0600 Sun")
        assert rules.coverage_warning(st, "2026-12-13", "2027-02-01") is None
        assert rules.RULES_URL in rules.coverage_warning(st, "2028-12-10", "2029-05-01")
        rules.remove_set("EAS 2027 v4")
        assert rules.active_set_info()["name"] == "EAS 2028 v1"
        assert len(os.listdir(os.path.join(d, "rules"))) == 2                # rules.json + the one set left
