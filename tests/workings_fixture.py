"""Synthetic platform workings (nothing real): a Cover and one tab per day in the layout of the Victoria,
London Bridge and Brighton books, so the readers, the comparison and the berthing arrangements can be tested."""
import openpyxl

DAYS = ["MO", "TO", "WO", "ThO", "FO", "SO", "SuO"]
TABS = ["SO", "SuO", "MO", "TO", "WO", "ThO", "FO"]                 # the order in the real books
FIELDS = {
    "victoria": ["id", "time", "line", "plat", "dest", "cars", "unit", "dep", "frm", "pos", "in_line", "due",
                 "in_id"],
    "london bridge": ["id", "time", "line", "plat", "dest", "cars", "unit", "op", "dep", "frm", "pos", "in_line",
                      "due", "in_id"],
    "brighton": ["id", "time", "plat", "dest", "cars", "unit", "op", "dep", "frm", "pos", "due", "in_id"],
}
HEADINGS = {"id": "Train", "time": "Time", "line": "Ln", "plat": "Plat", "dest": "Destination", "cars": None,
            "unit": "Stock", "op": "Op", "dep": "Time", "frm": "From", "pos": "Pos", "in_line": "Ln", "due": "Due",
            "in_id": "Train"}
TITLES = {"victoria": "Victoria", "london bridge": "London Bridge", "brighton": "Brighton"}
SIDING = {"victoria": "Victoria C.H.S.", "brighton": "Brighton Wall Siding", "london bridge": ""}


def r(**kw):
    """One row of a tab, by field name."""
    return kw


def day_rows(station: str, day: int, op: str = ""):
    """The trains of one day tab: berths at platforms 14, 15 and 16, a unit leaving the siding and one arriving."""
    nxt = DAYS[(day + 1) % 7]
    rows = [
        r(id="1W92", time="05.05", line="DBF", plat="14", dest="Brighton", cars="(4", unit="387)", frm="Berth"),
        r(cars="(4", unit="387)"),
        r(id="1L04", time="05.50", line="DBF", plat="15", dest="East Grinstead", cars="(4", unit="377)",
          frm="Berth"),
        r(cars="(4", unit="377)"), r(cars="(4", unit="377)"),
        r(id="1R06", time="06.20", line="DBF", plat="16", dest="Reigate", cars="4", unit="377",
          dep="04+15", frm="Selhurst Depot", due="04+52", in_id="5R06"),
        r(cars="4", unit="377", frm="Berth"),
        r(id="2F08", time="07.20", line="DBS", plat="10", dest="London Bridge", cars="(4", unit="377)",
          dep="06+28", frm="Stewarts Lane Berthing Sdg", due="06+39", in_id="5F07"),
        r(cars="(4", unit="377)"),
        # berthed at the end of the day (the next day's working is in the destination column)
        r(plat="14", dest=f"Berth BI56 05.05{nxt} (2)", cars="(4", unit="387)", dep="23.13", frm="Brighton",
          pos="UBF", due="00.41", in_id="1A91"),
        r(dest=f"Berth BI57 05.05{nxt} (1)", cars="(4", unit="387)"),
        r(plat="15", dest=f"Berth BI151 05.50{nxt} (3)", cars="4", unit="377", dep="22.36", frm="East Grinstead",
          due="23.33", in_id="1L71"),
        r(plat="15F", dest=f"Berth BI150 05.50{nxt} (2)", cars="(4", unit="377)", dep="23.06",
          frm="East Grinstead", due="00.09", in_id="1L73"),
        r(dest=f"Berth BI149 05.50{nxt} (1)", cars="(4", unit="377)"),
        r(plat="16", dest=f"Berth BI160 06.20{nxt}", cars="4", unit="377", dep="22.24", frm="Eastbourne",
          due="23.50", in_id="1F71"),
    ]
    if SIDING[station]:
        rows[7:7] = [
            r(id="1C04", time="06.54", line="DBF", plat="19FT", dest="Portsmouth Hbr", cars="4", unit="377",
              dep="05+28", frm=SIDING[station], pos="RP", due="05+32", in_id="5V03"),
            r(id="1R04", time="07.08", line="DBF", plat="19", dest="Reigate", cars="4", unit="377", dep="05+28",
              frm=SIDING[station], pos="FP", due="05+32", in_id="5V03"),
        ]
        rows += [
            # to the siding for the night
            r(id="5V74", time="23+40", plat="16", dest=SIDING[station], cars="(4", unit="377)", dep="22.30",
              frm="Epsom Downs", due="23.20", in_id="2B53"),
            r(cars="(4", unit="377)"),
        ]
    if op:
        rows.append(r(plat="10", dest=f"Berth TB414 09.10{nxt}", cars="8", unit="700", op="TLK", dep="23+48",
                      frm="Sutton", due="00+12", in_id="5V82"))
        rows.append(r(id="9O25", time="09.10", plat="10", dest="Sutton", cars="8", unit="700", op="TLK",
                      frm="Berth"))
    return rows


def make(path: str, station: str = "victoria", edit=None, footer=None):
    """Write synthetic workings. edit(day name, rows) may change a tab's rows; footer: {day: [(label, text)]}
    writes a hand-made berthing section under that tab."""
    wb = openpyxl.Workbook()
    cover = wb.active
    cover.title = "Cover "
    for i, text in enumerate(["Govia Thameslink Railway", f"{TITLES[station]} (C)", "Permanent Platform Workings",
                              "SYNTHETIC SUPPLEMENT NO 1", "UPDATES HIGHLIGHTED IN  YELLOW"], 1):
        cover.cell(row=i, column=1, value=text)
    fields = FIELDS[station]
    for tab in TABS:
        day = DAYS.index(tab)
        ws = wb.create_sheet(tab + " ")
        ws.cell(row=1, column=1, value=TITLES[station])
        for c, f in enumerate(fields, 1):
            ws.cell(row=2, column=c, value=HEADINGS[f])
        rows = day_rows(station, day, "TLK" if station != "victoria" else "")
        if edit:
            rows = edit(tab, rows) or rows
        row = 3
        for item in rows:
            for c, f in enumerate(fields, 1):
                if item.get(f) not in (None, ""):
                    ws.cell(row=row, column=c, value=item[f])
            row += 1
        if footer and tab in footer:
            row += 3
            name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day]
            ws.cell(row=row, column=1 if station != "brighton" else 2, value=f"{name} Berthing Arrangements:-")
            for label, text in footer[tab]:
                row += 1
                ws.cell(row=row, column=1 if station != "brighton" else 2, value=label)
                ws.cell(row=row, column=3 if station != "brighton" else 4, value=text)
    wb.save(path)
    return path


def make_smoke(folder: str):
    """The two workings the .exe smoke tests use: an issue and a changed one (wk_a.xlsx, wk_b.xlsx)."""
    import os

    def change(tab, rows):
        for row in rows:
            if row.get("id") == "1W92":
                row["plat"] = "13"
    make(os.path.join(folder, "wk_a.xlsx"), "victoria")
    make(os.path.join(folder, "wk_b.xlsx"), "victoria", edit=change)
