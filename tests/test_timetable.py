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
    assert wb.sheetnames == ["Summary", "Clashes", "Exempt", "Skipped", "By Section", "Not Checked",
                             "What Was Compared"]


def test_section4_remarks_parsed():
    from rstools.timetable import s4remarks as R
    r = R.parse_remarks("Except ECS. 1A23 excepted.")
    assert r.except_types == {"ecs"} and r.except_trains == ["1A23"] and r.understood
    assert R.parse_remarks("Freight only").only_types == {"freight"}
    assert R.parse_remarks("Possession starts after passage of 5E10").after_train == "5E10"
    dep = R.parse_remarks("Access to Selhurst Depot via Norwood Jn maintained.")
    assert dep.depot_access == [("Selhurst", "Norwood Jn")], dep.depot_access
    assert R.parse_remarks("Fast lines open").lines_open == ["Fast lines"]
    assert R.parse_remarks("Not 24/12").not_dates == [(24, 12, None)]
    assert R.parse_remarks("Not when 110.4 is taken").other_possession
    assert not R.parse_remarks("Something unusual").understood
    assert R._headcode_hits("5EXX", "5E12AB") and not R._headcode_hits("5EXX", "1E12AB")


def test_section4_remarks_rar_and_maint():
    """The check applies remarks (excepted types and headcodes, after passage of, depot access, unknown wording)
    and leaves out RAR non-passenger trains and trains on MAINT diagrams."""
    from datetime import date
    from rstools import stationbook as SB
    from rstools.timetable import section4 as S4
    d = tempfile.mkdtemp()
    x = os.path.join(d, "plan.xml")

    def tr(tid, a, t1, b, t2, extra="", via=""):
        legs = (f'<leg origin="{a}" dep="{t1}" dest="{b}" arr="{t2}"/>' if not via else
                f'<leg origin="{a}" dep="{t1}" dest="{via}" arr="{t1}" arrStopType="P"/>'
                f'<leg origin="{via}" dep="{t1}" dest="{b}" arr="{t2}"/>')
        return (f'<train id="{tid}" daysRun="NNNYNNNNN" planType="L" validFrom="2026-12-13" '
                f'validUntil="2027-05-15" {extra}>{legs}</train>')
    with open(x, "w", encoding="utf-8") as fh:
        fh.write('<diagramExchange xmlns="http://www.tracsis.com/TTVP_Interface" version="1.0" plantype="L" '
                 'startdate="2026-12-13" enddate="2027-05-15"><trainList>'
                 + tr("1A01XX", "AAA", "02:00:00", "BBB", "02:10:00")
                 + tr("5A02XX", "AAA", "02:00:00", "BBB", "02:10:00")                        # ECS: excepted
                 + tr("2A23XX", "AAA", "02:00:00", "BBB", "02:10:00")                        # named: excepted
                 + tr("5A04XX", "AAA", "02:00:00", "BBB", "02:10:00", 'runsAsRequired="true"')   # RAR ECS
                 + tr("1A05XX", "AAA", "02:00:00", "BBB", "02:10:00", 'runsAsRequired="true"')   # RAR passenger
                 + tr("5A06XX", "AAA", "02:00:00", "BBB", "02:10:00")                        # MAINT diagram
                 + tr("5D07XX", "AAA", "02:00:00", "DEP", "02:20:00", via="BBB")             # to the depot via BBB
                 + '</trainList><locationList><location tiploc="AAA" longDesc="Alpha"/>'
                 '<location tiploc="BBB" longDesc="Beta Jn"/><location tiploc="DEP" longDesc="Delta Depot"/>'
                 '</locationList><diagramList><unitDiagram id="9" daysrun="NNNYNNNNN"><depot id="MA"/>'
                 '<res id="MAINT"/><journey origin="AAA" dest="BBB" dep="02:00:00" arr="02:10:00">'
                 '<activity trainid="5A06XX"/></journey></unitDiagram></diagramList></diagramExchange>')
    plan = SB.read_plan(x)
    per = S4.Period("Periods A and B", date(2026, 12, 13), date(2027, 2, 14))

    def poss(num, remarks):
        return S4.Possession("XX100 TEST", "Alpha and Beta Jn", num, ("Alpha", "Beta Jn"), "MID WEEK", [per],
                             S4.parse_windows("0140 M-F to 0350 M-F"), "BLOCKED", remarks, "t")
    res = S4.check(plan, S4.Statement([poss("1.1", "Except ECS. 2A23 excepted."),
                                       poss("1.2", "Something unusual"),
                                       poss("1.3", "Access to Delta Depot via Beta Jn maintained.")]))
    kept = {(c.possession.number, c.train) for c in res.clashes}
    lifted = {(c.possession.number, c.train) for c in res.exempt}
    assert ("1.1", "1A01XX") in kept and ("1.1", "5A02XX") in lifted and ("1.1", "2A23XX") in lifted
    assert ("1.1", "1A05XX") in kept                                     # RAR but passenger: checked
    assert not any(t in ("5A04XX", "5A06XX") for _n, t in kept | lifted)
    assert dict(res.skipped)["5A06XX"] == "On a MAINT diagram" and "Runs as required" in dict(res.skipped)["5A04XX"]
    assert all(c.outcome == "check" and c.remark.startswith("Check remark") for c in res.clashes
               if c.possession.number == "1.2")
    assert ("1.3", "5D07XX") in lifted and ("1.3", "1A01XX") in kept
    assert SB.runs_as_required({"operatingCharacteristics": "BQ"}) and not SB.runs_as_required({"status": "P"})


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


def test_section4_built_in_rule_set(monkeypatch, tmp_path):
    """The 2027 EAS v4 Section 4 rule set ships with the app: in use until another is added or chosen, cannot be
    removed, and every possession has a clean line of route title."""
    import re
    from datetime import date
    from rstools import rules
    from rstools.timetable import section4 as S4
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    sets = rules.list_sets()
    assert [(s["name"], s["active"], s["built_in"]) for s in sets] == [(rules.BUILT_IN_S4, True, True)]
    b = sets[0]
    assert (b["possessions"], b["sections"], b["from"], b["to"]) == (5848, 702, "2026-12-13", "2027-12-11")
    assert len(b["files"]) == 5 and all(f.startswith("2027 EAS V4 S4") for f in b["files"])
    st = rules.load_set()
    assert len(st.possessions) == 5848
    routes = {p.route for p in st.possessions}
    assert "SO110 VICTORIA EASTERN TO RAMSGATE" in routes and "EA1110 THORPE-LE-SOKEN TO WALTON-ON-NAZE" in routes
    assert not [r for r in routes if re.search("[a-z]", r)]          # no notes or remarks caught in a title
    assert rules.coverage_warning(st, "2026-12-13", "2027-05-15") is None
    # an added set takes over; the built-in one can be chosen again but not removed
    per = S4.Period("Periods A and B", date(2026, 12, 13), date(2027, 2, 14))
    pos = S4.Possession("XX1 TEST", "A and B", "1.1", ("A", "B"), "WEEK END", [per],
                        S4.parse_windows("0100 Sun to 0600 Sun"), "BLOCKED", "", "t")
    monkeypatch.setattr(S4, "read_statement", lambda pdfs, log=None: S4.Statement([pos], list(pdfs)))
    rules.add_section4_set("EAS 2028 v1", ["/x/KS.pdf"])
    assert rules.active_set_info()["name"] == "EAS 2028 v1" and len(rules.load_set().possessions) == 1
    rules.use_set(rules.BUILT_IN_S4)
    assert rules.active_set_info()["built_in"] and len(rules.load_set().possessions) == 5848
    rules.remove_set(rules.BUILT_IN_S4)
    assert rules.BUILT_IN_S4 in [s["name"] for s in rules.list_sets()]
    rules.use_set("EAS 2028 v1")
    rules.remove_set("EAS 2028 v1")                                  # the set in use removed: back to built in
    assert rules.active_set_info()["name"] == rules.BUILT_IN_S4
    assert rules.add_section4_set(rules.BUILT_IN_S4, ["/x/a.pdf"])["name"] == "2027 EAS v4 (added)"


def test_section4_route_titles():
    """Line of route titles above a Section 4 table: notes left off, run-together lines split, signal numbers and
    'see ... in' notes not taken for titles."""
    from rstools.timetable.section4 import _titles
    t = lambda raw: [x[1] for x in _titles(raw)]
    assert t("OFFICIAL\r\nSO685 LEATHERHEAD TO HORSHAM (see also SW183) \r\nSECTION Periods") == [
        "SO685 LEATHERHEAD TO HORSHAM"]
    assert t("SO511/EA1325 HIGHBURY & ISLINGTON AND NEW CROSS GATE / NEW CROSS Published on behalf of TfL") == [
        "SO511/EA1325 HIGHBURY & ISLINGTON AND NEW CROSS GATE / NEW CROSS"]
    assert t("LN225 CLEETHORPES TO RETFORDNOTES: Please refer to the North and East Section 4 documentLN235 "
             "ROSSINGTON COLLIERY BRANCH ") == ["LN225 CLEETHORPES TO RETFORD", "LN235 ROSSINGTON COLLIERY BRANCH"]
    assert t("EA1320 CAMDEN ROAD WEST JN TO STRATFORDIncludes short sections (see SO400 and contact HS1)") == [
        "EA1320 CAMDEN ROAD WEST JN TO STRATFORD"]
    assert t("EA1290 TOTTENHAM SOUTH JN TO SOUTH TOTTENHAM EAST J\r\nN") == [
        "EA1290 TOTTENHAM SOUTH JN TO SOUTH TOTTENHAM EAST JN"]
    assert t("LN150 FLYOVER EAST JN TO DECOY NORTH JN LN722 FLYOVER EAST JN TO DECOY NORTH JN")[-1] == (
        "LN722 FLYOVER EAST JN TO DECOY NORTH JN")
    assert t("Dudding Hill Jn towards Brent Curve Jn (see LN3222 in Midlands & Continental section)") == []
    assert t("(2520pts to BE536sigs,\r\n2521pts to BE547 and Up Branch Siding)") == []
    assert t("SW230 BARNES TO FELTHAM JN / WHITTON JN (VIA HOUNSLOW) SECTION Barnes to Chiswick") == [
        "SW230 BARNES TO FELTHAM JN / WHITTON JN (VIA HOUNSLOW)"]


# --------------------------------------------------------------------------- synthetic rule documents
def write_s4_pdf(path, rows, period="Periods A and B 13.12.2026 to 14.02.2027", route="XX100 TEST ROUTE",
                 notes=(), construction=(), version="4.0", date="10th July 2026"):
    """A Section 4 PDF laid out like Network Rail's: pages turned through 90 degrees (the text runs up the page),
    a running header and footer, then per route a page of timetable construction notes and a page with the
    possession table (rows: section text, night, cell text, remarks) followed by NOTES.
    construction: (stretch of line, note text); notes: NOTES text."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=(1100, 600))           # displayed size; the content is 600 wide, 1100 high

    def text(x, y, s, size=6):
        c.saveState()
        c.translate(x, y)
        c.rotate(90)
        c.setFont("Helvetica", size)
        c.drawString(0, 0, s)
        c.restoreState()

    def page(n):
        c.setPageRotation(90)
        text(18, 40, f"Network Rail Engineering Access Statement 2027 Version: {version}", 9)
        text(30, 40, f"Test Route Confirmed Rules Date : {date}", 9)
        text(42, 40, f"Section 4 - Standard Possessions and Opportunities Page : {n} of 2", 9)
        text(580, 40, "Electronic copy - uncontrolled when printed. Next scheduled issue: 23rd October 2026", 9)
    page(1)
    text(70, 60, route, 12)
    x = 95
    for scope, line in construction:
        text(x, 60, f"{scope} Timetable Construction Notes", 10)
        text(x + 16, 60, line, 8)
        x += 44
    c.showPage()
    page(2)
    text(70, 60, route + " Continued....", 12)
    cols = [50, 250, 330, 630, 1000]             # SECTION, night, period, REMARKS (along y)
    edges = [100, 140] + [140 + 30 * (i + 1) for i in range(len(rows))]
    for e in edges:
        c.line(e, cols[0], e, cols[-1])
    for y in cols:
        c.line(edges[0], y, edges[-1], y)
    for a_, t in zip(cols, ["SECTION", "Night", period, "REMARKS"]):
        text(edges[1] - 6, a_ + 3, t)
    for x1, (sec, night, cell, rem) in zip(edges[2:], rows):
        for a_, t in zip(cols, [sec, night, cell, rem]):
            text(x1 - 6, a_ + 3, t)
    x = edges[-1] + 28
    for note in notes:
        text(x, 60, "NOTES: " + note, 8)
        x += 22
    c.showPage()
    c.save()


def write_tpr_pdf(path, rows, note="Trains must not be timed to pass Beta Jn within 3 minutes of each other.",
                  pages=1, commentary=2, version="4.0", date="26 June 2026"):
    """A TPR laid out like Network Rail's route rules: covering commentary pages, then pages with a four-line
    running header and a footer, numbered headings (16 and 14 pt), a paragraph with a deleted sentence (green,
    struck through) and a new one (red), a line-of-route title, a ruled table (with a deleted value in a cell, a
    change bar in the margin), repeated over `pages` pages with its heading row repeated."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=(595, 842))
    for _k in range(commentary):
        c.setFont("Helvetica", 10)
        c.drawString(40, 800, "Commentary on the Test Route Timetable Planning Rules 2027, Version 4")
        c.drawString(40, 780, "5.2 Headways: the value for Beta Jn is changed.")
        c.showPage()

    def struck(x, y, s):
        c.setFillColorRGB(0, 0.69, 0.31)
        c.setFont("Helvetica", 10)
        c.drawString(x, y, s)
        c.setLineWidth(0.6)
        c.line(x, y + 3.5, x + c.stringWidth(s, "Helvetica", 10), y + 3.5)
        c.setFillColorRGB(0, 0, 0)
    for pg in range(pages):
        c.setFont("Helvetica", 10)
        c.drawString(40, 820, f"NETWORK RAIL Timetable Planning Rules Version: {version}")
        c.drawString(40, 808, f"Route: Draft Rules for Test Change 2027 Date: {date}")
        c.drawString(40, 796, f"Test Route Page: {commentary + pg + 1} of {commentary + pages}")
        c.drawString(40, 30, "Electronic copy - uncontrolled when printed.")
        top = 740
        if pg == 0:
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, 765, "5 Running Times and Margins")
            c.setFont("Helvetica", 14)
            c.drawString(40, 740, "5.2 Headways")
            c.setFont("Helvetica", 10)
            c.drawString(40, 718, note)
            struck(40, 704, "This sentence was deleted in the issue.")
            c.setFillColorRGB(1, 0, 0)
            c.drawString(40, 690, "A new sentence shown in red.")
            c.setFillColorRGB(0, 0, 0)
            c.drawString(40, 664, "LN100 TEST ROUTE TO OTHER JN")
            top = 650
            c.setLineWidth(1)
            c.line(566, 600, 566, 640)                              # a change bar in the right margin
        c.setLineWidth(0.5)
        heads = ["Location", "Line", "Headway"]
        xs = [40, 200, 320, 440]
        body = rows if pages == 1 else rows[pg::pages]
        ys = [top - 18 * i for i in range(len(body) + 2)]
        for y in ys:
            c.line(xs[0], y, xs[-1], y)
        for x in xs:
            c.line(x, ys[-1], x, ys[0])
        for r, cells in enumerate([heads] + list(body)):
            for x, v in zip(xs, cells):
                c.setFont("Helvetica", 10)
                c.drawString(x + 3, ys[r] - 13, v)
        if pg == 0 and body:
            struck(xs[2] + 14, ys[1] - 13, "9")                      # a deleted value beside the real one
        c.showPage()
    c.save()


S4_ROWS = [("Alpha and Beta Jn 100.1", "MID WEEK", "0140 T-F to 0350 T-F Down and Up BLOCKED", "Except ECS"),
           ("Beta Jn and Gamma 100.2", "WEEK END", "2350 Sat to 0750 Sun BLOCKED", "")]
S4_ROWS_NEW = [("Alpha and Beta Jn 100.1", "MID WEEK", "0110 T-F to 0350 T-F Down and Up BLOCKED", "Except ECS"),
               ("Delta and Gamma 100.3", "SUN/MON", "0100 Mon to 0500 Mon BLOCKED", "Freight only")]
S4_NOTES = ["Access to be maintained to Alpha depot via the slow lines.", "Possessions to be given up at 0750."]
S4_NOTES_NEW = ["Access to be maintained to Delta depot via the slow lines.", "Possessions to be given up at 0750."]
S4_CONSTRUCTION = [("Alpha to Beta Jn", "Sat/Sun All trains to be timed over the slow lines.")]
TPR_ROWS = [("Alpha", "Fast", "3"), ("Beta Jn", "Slow", "4"), ("Gamma", "All", "2")]
TPR_ROWS_NEW = [("Alpha", "Fast", "3"), ("Beta Jn", "Slow", "5"), ("Delta", "All", "2")]


def write_rule_docs(folder):
    """Original and updated Section 4 and TPR PDFs (also used by the Windows build's smoke test)."""
    out = {k: os.path.join(folder, f"{k}.pdf") for k in ("s4_old", "s4_new", "tpr_old", "tpr_new")}
    write_s4_pdf(out["s4_old"], S4_ROWS, notes=S4_NOTES, construction=S4_CONSTRUCTION)
    write_s4_pdf(out["s4_new"], S4_ROWS_NEW, notes=S4_NOTES_NEW, construction=S4_CONSTRUCTION, date="14th August 2026",
                 version="4.1")
    write_tpr_pdf(out["tpr_old"], TPR_ROWS, pages=2)
    write_tpr_pdf(out["tpr_new"], TPR_ROWS_NEW, pages=2, version="4.1", date="14 August 2026",
                  note="Trains must not be timed to pass Beta Jn within 4 minutes of each other.")
    return out


def test_section4_documents_compared():
    """Two Section 4 PDFs: a window changed, a section removed and one added, a note edited; headings are not
    compared but the versions and dates are shown for information."""
    import openpyxl
    from rstools.timetable.engine import run
    d = tempfile.mkdtemp()
    f = write_rule_docs(d)
    res = run("s4docs", [f["s4_old"]], [f["s4_new"]], d)
    wb = openpyxl.load_workbook(res.path)
    assert wb.sheetnames == ["Summary", "Changes", "Added", "Removed", "What Was Compared"]
    changes = [tuple(c.value for c in r[2:6]) for r in wb["Changes"].iter_rows(min_row=2)]
    assert ("100.1 MID WEEK - Down and Up BLOCKED", "Windows", "0140 Tue to 0350 Tue; 0140 Wed to 0350 Wed; "
            "0140 Thu to 0350 Thu; 0140 Fri to 0350 Fri", "0110 Tue to 0350 Tue; 0110 Wed to 0350 Wed; "
            "0110 Thu to 0350 Thu; 0110 Fri to 0350 Fri") in changes, changes
    assert any(c[1] == "Text" and "Alpha depot" in c[2] and "Delta depot" in c[3] for c in changes), changes
    added = [r[2].value for r in wb["Added"].iter_rows(min_row=2)]
    removed = [r[2].value for r in wb["Removed"].iter_rows(min_row=2)]
    assert added == ["100.3 SUN/MON - BLOCKED"] and removed == ["100.2 WEEK END - BLOCKED"]
    assert res.differences == 4
    audit = [[c.value for c in r] for r in wb["What Was Compared"].iter_rows(min_row=2)]
    assert any(r[0] == "Original document" and "Version 4.0" in r[1] and "10th July 2026" in r[1] for r in audit)
    assert any(r[0] == "Updated document" and "Version 4.1" in r[1] for r in audit)       # shown, not compared
    from rstools.timetable.section4 import read_statement
    st = read_statement([f["s4_old"]])
    kinds = {(n.kind, n.scope): n.text for n in st.notes}
    assert kinds[("Timetable construction notes", "Alpha to Beta Jn")].startswith("Sat/Sun All trains")
    assert [n.text for n in st.notes if n.kind == "Notes"] == S4_NOTES
    assert all(n.route == "XX100 TEST ROUTE" for n in st.notes)
    assert not any("Version" in n.text or "uncontrolled" in n.text for n in st.notes)     # not header or footer


def test_section4_rows_repeating_a_section_and_night_pair_correctly():
    """A section can have several possessions for one night (one per line blocked): an inserted row, or one whose
    blocked line changed, never shifts the pairing of the others."""
    from rstools.timetable.s4compare import compare_statements
    from rstools.timetable.section4 import read_statement
    d = tempfile.mkdtemp()
    base = [("Alpha and Beta Jn 100.1", "MID WEEK", f"0140 T-F to 0350 T-F {line} BLOCKED", "")
            for line in ("Down Slow", "Up Slow", "Fast")]
    old, ins, ren = (os.path.join(d, n) for n in ("old.pdf", "ins.pdf", "ren.pdf"))
    write_s4_pdf(old, base)
    write_s4_pdf(ins, [("Alpha and Beta Jn 100.1", "MID WEEK", "0140 T-F to 0350 T-F Down Fast BLOCKED", "")] + base)
    write_s4_pdf(ren, [base[0], ("Alpha and Beta Jn 100.1", "MID WEEK",
                                 "0140 T-F to 0350 T-F Up Slow No2 BLOCKED", ""), base[2]])
    a = read_statement([old])
    c = compare_statements(a, read_statement([ins]))
    assert [(i.status, i.label) for i in c.items if i.status != "same"] == [
        ("added", "100.1 MID WEEK - Down Fast BLOCKED")], [(i.status, i.label) for i in c.items]
    c = compare_statements(a, read_statement([ren]))
    diff = [i for i in c.items if i.status != "same"]
    assert len(diff) == 1 and diff[0].status == "changed" and [x[0] for x in diff[0].changes] == ["Blocked"]


def test_tpr_documents_compared():
    """Two TPR PDFs: a table cell changed, a row added and one removed, a paragraph edited. The covering commentary,
    the running header and footer, deleted (green struck-through) text and the change bar in the margin are not
    part of the comparison; a table carried over two pages is one table."""
    import openpyxl
    from rstools.timetable.engine import run
    from rstools.timetable.tpr import read_tpr
    d = tempfile.mkdtemp()
    f = write_rule_docs(d)
    doc = read_tpr([f["tpr_old"]])
    (table,) = doc.tables
    assert table.section == "5 Running Times and Margins > 5.2 Headways"
    assert table.title == "LN100 TEST ROUTE TO OTHER JN"
    assert table.headers == ["Location", "Line", "Headway"]                  # the change bar is not a column
    assert table.rows[0] == ["Alpha", "Fast", "3"]                            # the deleted '9' is ignored
    assert sorted(r[0] for r in table.rows) == ["Alpha", "Beta Jn", "Gamma"]  # one table over the two pages
    text = " ".join(p for _s, p, _n in doc.paragraphs)
    assert "within 3 minutes" in text and "A new sentence shown in red." in text
    assert "deleted in the issue" not in text and "Page:" not in text and "uncontrolled" not in text
    assert "Commentary" not in text and doc.deleted == 2
    assert doc.skipped == ["tpr_old.pdf: pages 1-2 (covering commentary)"]
    assert doc.info and "Version 4.0" in doc.info[0][1] and "26 June 2026" in doc.info[0][1]
    res = run("tprs", [f["tpr_old"]], [f["tpr_new"]], d)
    wb = openpyxl.load_workbook(res.path)
    changes = [tuple(c.value for c in r[2:6]) for r in wb["Changes"].iter_rows(min_row=2)]
    assert ("Beta Jn", "Headway", "4", "5") in changes, changes
    assert any(c[1] == "Text" and "3 minutes" in c[2] and "4 minutes" in c[3] for c in changes), changes
    assert [r[2].value for r in wb["Added"].iter_rows(min_row=2)] == ["Delta"]
    assert [r[2].value for r in wb["Removed"].iter_rows(min_row=2)] == ["Gamma"]
    audit = [[c.value for c in r] for r in wb["What Was Compared"].iter_rows(min_row=2)]
    assert any(r[0] == "Updated document" and "Version 4.1" in r[1] for r in audit)
    assert any(r[0] == "Not compared" and "covering commentary" in r[1] for r in audit)
    assert any(r[0] == "Not compared" and "deleted in the issue" in r[1] for r in audit)
    two = os.path.join(d, "two.pdf")
    write_tpr_pdf(two, TPR_ROWS, pages=2)
    doc = read_tpr([two])
    assert len(doc.tables) == 1 and sorted(r[0] for r in doc.tables[0].rows) == ["Alpha", "Beta Jn", "Gamma"]
    assert not any("Page" in p for _s, p, _n in doc.paragraphs)


def write_s4_xml(path):
    """A one-train Attune XML running over the synthetic Section 4 section 100.1 (Windows build smoke test)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<diagramExchange xmlns="http://www.tracsis.com/TTVP_Interface" version="1.0" plantype="L" '
                 'startdate="2026-12-13" enddate="2027-05-15"><trainList><train id="1A01XX" daysRun="NNNYYYYNN" '
                 'planType="L"><leg origin="AAA" dep="02:00:00" dest="BBB" arr="02:10:00"/></train></trainList>'
                 '<locationList><location tiploc="AAA" longDesc="Alpha"/><location tiploc="BBB" longDesc="Beta Jn"/>'
                 '</locationList></diagramExchange>')


def test_document_text_ignores_dates_case_and_spelling_but_not_numbers():
    from rstools.timetable.doccompare import book_of, books_of, same_text
    assert same_text("Possession from 12/12/2026 to 03/01/2027 on Brighton Jn", "possession from 11/12/2027 to "
                     "02/01/2028 on  brighton junction")
    assert same_text("Valid 5 January 2026 - 3 March 2026.", "Valid 4 January 2027 - 2 March 2027.")
    assert same_text("Colour light signals", "Color light signals")
    assert same_text("Access to Alpha depot & the slow lines", "Access to Alpha depot and the slow lines")
    assert not same_text("Block 0100 to 0400", "Block 0110 to 0400")
    assert not same_text("Down Slow No1", "Down Slow No2")
    assert not same_text("Down line blocked", "Up line blocked")
    assert not same_text("Trains may pass Beta", "Trains must not pass Beta")
    assert book_of("2027 EAS V4 S4 - EC.pdf p12") == "EC"
    assert book_of("C:/x/TPR 2027 V4 KT.pdf") == "KT"
    assert books_of("2027 EAS V4 S4 - EC.pdf p3", "2027 EAS V4 S4 - KS.pdf p9") == "EC / KS"
    assert books_of("2027 EAS V4 S4 - EC.pdf", "2028 EAS V1 S4 - EC.pdf") == "EC"


def test_changes_highlighted_in_copies_of_the_pdfs():
    import hashlib
    import pypdf
    from rstools.timetable.engine import run
    d = tempfile.mkdtemp()
    f = write_rule_docs(d)
    before = {k: hashlib.sha256(open(v, "rb").read()).hexdigest() for k, v in f.items() if v.endswith(".pdf")}
    for mode, old, new, kinds in (("s4docs", "s4_old", "s4_new", {"Highlight"}),
                                  ("tprs", "tpr_old", "tpr_new", {"Highlight"})):
        res = run(mode, [f[old]], [f[new]], d, highlight_pdfs=True)
        assert len(res.extra) == 2, res.extra                 # a copy of each side
        counts = {}
        for path in res.extra:
            assert " - highlighted" in os.path.basename(path)
            annots = [a.get_object() for pg in pypdf.PdfReader(path).pages for a in pg.get("/Annots", [])]
            assert annots and {str(a["/Subtype"])[1:] for a in annots} == kinds
            for a in annots:
                x0, y0, x1, y1 = (float(v) for v in a["/Rect"])
                assert x1 > x0 and y1 > y0 and str(a["/Contents"])
            counts[path] = [str(a["/Contents"]) for a in annots]
        texts = " ".join(" ".join(v) for v in counts.values())
        assert "Changed" in texts and "Added" in texts and "Removed" in texts, texts
    assert before == {k: hashlib.sha256(open(v, "rb").read()).hexdigest() for k, v in f.items()
                      if v.endswith(".pdf")}                    # the sources are untouched
    res = run("s4docs", [f["s4_old"]], [f["s4_new"]], d)
    assert res.extra == []


# ------------------------------------------------------------------ Attune VPT (Voyager plan train export)
def write_vpt(path, trains):
    """A synthetic VPT. Each train: dict(id, start, end, bits, points=[dict(tip, arr, dep, plat, line, allow, stop)])
    with times in seconds; an origin has no arr, a destination no dep, a pass has stop=False."""
    out = ["00,VoyagerPlanTrainExport,2,20261126152819,AA,20270516,20271211,"]
    for n, t in enumerate(trains, start=1):
        pts = t["points"]
        h = [""] * 86
        h[0], h[1], h[2], h[6], h[8], h[9] = "01", f"{t['id']:<8}", t["start"], str(n), pts[0]["tip"], pts[-1]["tip"]
        h[11], h[12], h[13], h[25], h[34], h[46], h[47] = "375", t["end"], str(t["bits"]), "66.3345", "XX", "EMU", "100"
        out.append(",".join(h))
        for i, (a, b) in enumerate(zip(pts, pts[1:]), start=1):
            start = a["dep"] if a.get("dep") is not None else a["arr"]
            end = b["arr"] if b.get("arr") is not None else b["dep"]
            dwell = (b["dep"] - b["arr"]) if b.get("dep") is not None and b.get("arr") is not None else 0
            al = b.get("allow", (0, 0, 0, 0))
            row = ["04", str(n), str(i), a["tip"], b["tip"], "L", "P", "0", "Y", str(end), "0", str(start), "0",
                   "N", "N", "0", "0", "0", str(dwell), a.get("plat", ""), "", b.get("line", ""),
                   *map(str, al), "S" if a.get("stop", True) else "P", "20260720"]
            out.append(",".join(row))
        last = pts[-1]
        out.append(",".join(["04", str(n), str(len(pts)), last["tip"], last["tip"], "L", "P", "0", "Y", "0", "0",
                             str(last["arr"]), "0", "N", "N", "0", "0", "0", "0", last.get("plat", ""), "", "",
                             "0", "0", "0", "0", "S"]))
    with open(path, "w", encoding="latin-1", newline="") as fh:
        fh.write("\r\n".join(out) + "\r\n")


def _h(h, m, s=0):
    return h * 3600 + m * 60 + s


def vpt_1h05(**over):
    """The synthetic Attune print's 1H05BS as a VPT train (Brighton to London Victoria, Monday to Friday)."""
    pts = [dict(tip="BTN", dep=_h(5, 37), plat="3"),
           dict(tip="KEYMERJ", arr=_h(5, 41), dep=_h(5, 41), stop=False),
           dict(tip="HYWRDSH", arr=_h(5, 52, 30), dep=_h(5, 53, 30), plat="4", line="UML", allow=(0, 0, 60, 0)),
           dict(tip="ECROYDN", arr=_h(6, 18, 30), dep=_h(6, 20), plat="1"),
           dict(tip="VICTRIC", arr=_h(6, 37), plat="18")]
    for k, v in over.items():
        tip, key = k.split("_", 1)
        next(p for p in pts if p["tip"] == tip.upper())[key] = v
    return dict(id="1H05BS", start="20270517", end="20271210", bits=62, points=pts)


def _print_1h05(path):
    import copy
    trains = copy.deepcopy(ATTUNE[:1])
    trains[0]["rows"][0] = ("BTN", "Brighton", "", "05.37", "", "05.37", "", "TB", "3")     # no arrival at the origin
    trains[0]["rows"][4] = ("VICTRIC", "London Victoria", "06.37", "", "06.37", "", "", "TF", "18")   # nor departure
    write_attune_pdf(path, trains)


def test_vpt_reader():
    from rstools.timetable.prints import read_print
    from rstools.timetable.vpt import is_vpt
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.vpt")
        write_vpt(p, [vpt_1h05()])
        assert is_vpt(p) and not is_vpt(os.path.join(d, "nothing.vpt"))
        (t,) = read_print(p)
        assert (t.ident, t.headcode, t.days, t.kind) == ("1H05BS", "1H05", "SX", "vpt")
        assert t.info["From"] == "17/05/2027" and t.info["Until"] == "10/12/2027" and t.info["Power Type"] == "EMU"
        by = {c.tiploc: c for c in t.calls}
        assert [c.tiploc for c in t.calls] == ["BTN", "KEYMERJ", "HYWRDSH", "ECROYDN", "VICTRIC"]
        assert by["BTN"].times == {"wtt_dep": "05.37"} and by["BTN"].fields == {"plat": "3"}
        assert by["KEYMERJ"].times == {"pass": "05/41"}
        hh = by["HYWRDSH"]
        assert hh.times == {"wtt_arr": "05a52½", "wtt_dep": "05p53½"}
        assert hh.fields["plat"] == "4" and hh.fields["line"] == "UML" and hh.fields["prf"] == "1"
        assert by["VICTRIC"].times == {"wtt_arr": "06.37"} and by["VICTRIC"].fields["plat"] == "18"
        bad = os.path.join(d, "bad.vpt")
        with open(bad, "w") as fh:
            fh.write("not a vpt\n")
        try:
            read_print(bad)
        except Exception as exc:
            assert "not an Attune Voyager" in str(exc)
        else:
            raise AssertionError("a file that is not a VPT was read")


def test_vpt_against_vpt():
    from rstools.timetable.engine import run
    from rstools.timetable.prints import change_kind
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.vpt"), os.path.join(d, "b.vpt")
        other = dict(id="1H09BS", start="20270517", end="20271210", bits=62, points=[
            dict(tip="BTN", dep=_h(9, 0), plat="1"), dict(tip="VICTRIC", arr=_h(10, 30), plat="2")])
        write_vpt(a, [vpt_1h05(), other])
        write_vpt(b, [vpt_1h05(HYWRDSH_dep=_h(5, 54, 30), HYWRDSH_plat="5", ECROYDN_allow=(0, 30, 0, 0))])
        from rstools.timetable.engine import compare_files
        cmp = compare_files("prints", [a], [b])
        assert len(cmp.pairs) == 1 and len(cmp.removed) == 1 and not cmp.added
        kinds = {(c.location, c.change) for c in cmp.changes}
        assert ("Haywards Heath", "Working departure time changed") in kinds
        assert ("Haywards Heath", "Platform changed") in kinds
        assert ("East Croydon", "Pathing allowance changed") in kinds
        assert {change_kind(c) for c in cmp.changes} == {"Timing", "Platform/line", "Dwell/allowances"}
        same = compare_files("prints", [a], [a])
        assert not same.changes and len(same.pairs) == 2
        res = run("prints", [a], [b], d, "vpt_vs_vpt")
        assert os.path.getsize(res.path) > 1000


def test_vpt_against_print_and_print_against_vpt():
    from rstools.timetable.engine import compare_files
    with tempfile.TemporaryDirectory() as d:
        pdf, a, b = os.path.join(d, "p.pdf"), os.path.join(d, "a.vpt"), os.path.join(d, "b.vpt")
        _print_1h05(pdf)
        write_vpt(a, [vpt_1h05()])
        write_vpt(b, [vpt_1h05(HYWRDSH_dep=_h(5, 54, 30), HYWRDSH_plat="5")])
        for first, second in (([a], [pdf]), ([pdf], [a])):
            cmp = compare_files("prints", first, second)
            assert len(cmp.pairs) == 1 and not cmp.changes, [(c.location, c.change) for c in cmp.changes]
            assert any("VPT export has no public times" in w for w in cmp.warnings)
        for first, second in (([b], [pdf]), ([pdf], [b])):
            cmp = compare_files("prints", first, second)
            got = {(c.location, c.change) for c in cmp.changes}
            assert ("Haywards Heath", "Working departure time changed") in got or \
                ("Haywards Heath", "Departure time changed") in got, got
            assert ("Haywards Heath", "Platform changed") in got and len(cmp.pairs) == 1
        # days and train ID are compared too; fields laid out differently (allowances, lines) are not
        c = vpt_1h05()
        c["bits"] = 64                                                     # Saturdays only now
        write_vpt(b, [c])
        cmp = compare_files("prints", [pdf], [b])
        assert [x.change for x in cmp.changes] == ["Days run changed"], [(x.location, x.change) for x in cmp.changes]
        # passenger times only: a stop only the VPT has (an operational stop) is not reported
        extra = vpt_1h05()
        extra["points"].insert(2, dict(tip="BALCMTJ", arr=_h(5, 47), dep=_h(5, 48), plat="2"))
        write_vpt(b, [extra])
        assert compare_files("prints", [pdf], [b], passenger_only=True).changes == []
        assert any(x.change == "Location added" for x in compare_files("prints", [pdf], [b]).changes)


def test_live_vpt_against_vpt_and_print():
    from rstools.live.adapters import compute
    with tempfile.TemporaryDirectory() as d:
        pdf, a, b = os.path.join(d, "p.pdf"), os.path.join(d, "a.vpt"), os.path.join(d, "b.vpt")
        _print_1h05(pdf)
        write_vpt(a, [vpt_1h05()])
        write_vpt(b, [vpt_1h05(HYWRDSH_dep=_h(5, 54, 30))])
        res = compute("prints", {"a": [a], "b": [b]})
        (item,) = res.items
        assert item.status == "Timing change" and item.state == "changed"
        res = compute("prints", {"a": [a], "b": [pdf]})
        assert [i.status for i in res.items] == ["No change"]
        res = compute("prints", {"a": [pdf], "b": [b]})
        assert [i.status for i in res.items] == ["Timing change"]
