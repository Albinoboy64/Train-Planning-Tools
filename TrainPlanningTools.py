"""Train Planning Tools - entry point.

Double-click (or run with no arguments) to open the desktop app.
Command-line use:
    TrainPlanningTools.exe --original OLD.xlsx --updated NEW.xlsx [--acwn] [--name NAME] [--out DIR]
    TrainPlanningTools.exe --previous PREVIOUS_OUTPUT.xlsx --updated NEW.xlsx --colour 92D050
    TrainPlanningTools.exe --original OLD.xlsx --updated NEW.xlsx --days FO   (Friday trains only)
    TrainPlanningTools.exe --original-folder OLD_FOLDER --updated NEW_FOLDER    (every pair of CWNs)
    TrainPlanningTools.exe stationbook --xml PLAN.xml --station "London Kings Cross" [--platforms 10-15]
                                       [--sheets SX,SO,Su] [--merge OTHER_OPERATOR.xml|.vpt ...]
    TrainPlanningTools.exe reorder CWN.xlsx [--by-time] [--merge ...] [--name NAME] [--out DIR]  (day variants in order)
    TrainPlanningTools.exe berthing --xml LTP.xml [STP.xml] --layout CHART.xlsx [--issue "Proof 1"]
    TrainPlanningTools.exe berthing --chart CHART.xlsx --original OLD.xml --updated NEW.xml [--colour "Light green"]
    TrainPlanningTools.exe berthing --compare OLD_CHART.xlsx NEW_CHART.xlsx [--colour Orange]
    TrainPlanningTools.exe statspack --xml PLAN.xml --trent VehicleLayout29.docx [--days MO,TO]
                                     [--output totals_days|totals|days]
    TrainPlanningTools.exe statspack --trent "LTP_VL29.docx;STP_VL29.docx" --unit-reports washes,depots,captive
    TrainPlanningTools.exe statspack --xml NEW.xml --trent NEW.docx --old-xml OLD.xml --old-trent OLD.docx
    TrainPlanningTools.exe statspack --old-pack OLD.xlsx --new-pack NEW.xlsx
    TrainPlanningTools.exe statspack --xml PLAN.xml --trent VL29.docx --capacity-group 1W --between 07:00-10:00
                                     --at "London Victoria"
    TrainPlanningTools.exe statspack --xml PLAN.xml --trent VL29.docx --capacity-from Brighton
                                     --capacity-to "London Victoria" --no-standing
    TrainPlanningTools.exe timetable --gtr GTR.xlsx --nr NR.xlsx [--format xlsx|pdf|docx]
    TrainPlanningTools.exe timetable --prints OLD.pdf [OLD2.pdf ...] --vs NEW.pdf [NEW2.docx ...] [--passenger-only]
    TrainPlanningTools.exe timetable --prints OLD.vpt --vs NEW.vpt          (Attune VPT exports, or a VPT with prints)
    TrainPlanningTools.exe timetable --lists OLD.xlsx --vs NEW.xlsx
    TrainPlanningTools.exe timetable --base-prints PRINT.pdf [...] --check TIMETABLE.xlsx
    TrainPlanningTools.exe timetable --base-list ATTUNE_LIST.xlsx --check TIMETABLE.xlsx
    TrainPlanningTools.exe timetable --s4-check PLAN.xml [--s4 SECTION4.pdf ...] [--vpt OURS.vpt]
                                     [--other-vpt OTHER.vpt ...]
    TrainPlanningTools.exe section4 --xml PLAN.xml [--pdf SECTION4.pdf ...] [--vpt OURS.vpt]
                                    [--other-vpt OTHER.vpt ...] [--out DIR] [--name NAME] [--format xlsx|pdf|docx]
    TrainPlanningTools.exe timetable --s4 OLD_S4.pdf [...] --vs-s4 NEW_S4.pdf [...] [--highlight-pdfs]
    TrainPlanningTools.exe timetable --tpr OLD_TPR.pdf [...] --vs-tpr NEW_TPR.pdf [...] [--highlight-pdfs]
"""
import argparse
import os
import sys

# A windowed (no console) build has no stdout/stderr - avoid crashes on print().
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def cli(argv):
    from cwn_compare.engine import run
    from cwn_compare.options import Options

    ap = argparse.ArgumentParser(
        description="Compare two Carriage Working Notices. Other commands: " + ", ".join(COMMANDS)
        + " (e.g. TrainPlanningTools statspack --help).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--original", help="original CWN")
    g.add_argument("--previous", help="previously generated comparison CWN (adds a new round)")
    g.add_argument("--original-folder", help="folder of original CWNs (batch: compared with --updated as a folder)")
    ap.add_argument("--updated", required=True, help="updated CWN (or, with --original-folder, folder of updated CWNs)")
    ap.add_argument("--acwn", action="store_true", help="output amended trains only")
    ap.add_argument("--colour", default=None, help="highlight colour as hex, e.g. FFFF00")
    ap.add_argument("--name", default="", help="output name (default: today's date)")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--keep-links", action="store_true",
                    help="keep the headcode hyperlinks between tabs (output opens more slowly)")
    ap.add_argument("--highlight-only", action="store_true",
                    help="highlight new and changed items only: no previous values, notes or cancelled trains")
    ap.add_argument("--report-format", choices=["xlsx", "pdf", "docx"], default="xlsx",
                    help="change report as Excel (default), PDF or Word")
    ap.add_argument("--exact-text", action="store_true",
                    help="report differences in spacing / punctuation in destinations and notes")
    ap.add_argument("--exclude", default="", help="comma separated categories to strip, e.g. PLATFORM,DIAGRAM")
    ap.add_argument("--days", default="", help="check and output only trains running on these days, e.g. MO,FO")
    a = _local_out(ap, ap.parse_args(argv))
    o = Options()
    o.mode = "cumulative" if a.previous else "batch" if a.original_folder else "compare"
    o.original = a.previous or a.original or a.original_folder
    o.updated = a.updated
    o.output_type = "acwn" if a.acwn else "highlight" if a.highlight_only else "full"
    if a.colour:
        o.colour = a.colour.lstrip("#")
    elif a.previous:
        o.colour = "92D050"
    o.output_name = a.name
    o.output_dir = a.out
    o.make_report = not a.no_report
    o.keep_links = a.keep_links
    o.ignore_spacing = not a.exact_text
    o.report_format = a.report_format
    if a.days:
        from cwn_compare.days import parse_day_list
        try:
            o.days = sorted(parse_day_list(a.days))
        except ValueError as exc:
            ap.error(str(exc))
    for k in o.categories:
        if a.highlight_only:
            o.categories[k]["show_old"] = False
    for k in filter(None, (x.strip().upper() for x in a.exclude.split(","))):
        if k in o.categories:
            o.categories[k] = {"cwn": False, "show_old": False, "report": False}
    if o.mode == "batch":
        from cwn_compare.batch import pair_files, run_batch
        pairs, left, right = pair_files(o.original, o.updated)
        for x in left + right:
            print("Not paired:", x)
        if not pairs:
            print("ERROR: no CWNs could be paired between the two folders.")
            sys.exit(1)
        bad = []

        def done(n, total, orig, upd, res, err):
            print(f"[{n}/{total}] {os.path.basename(upd)}: " + (f"{res['changes']} change(s) -> {res['cwn']}" if res
                                                               else f"ERROR {err}"))
            if not res:
                bad.append(upd)
        run_batch(pairs, o, done)
        sys.exit(1 if bad else 0)
    try:
        res = run(o, log=print)
    except Exception as exc:                 # readable messages from the CWN reader and engine
        print("ERROR:", exc)
        sys.exit(1)
    print(res)


def stationbook_cli(argv):
    from rstools.stationbook import StationBookError, make_book, make_books, parse_station_list
    ap = argparse.ArgumentParser(prog="TrainPlanningTools stationbook",
                                 description="Station Working Book (TRACS-RS layout) from an Attune XML")
    ap.add_argument("--xml", required=True, help="Attune diagram XML (with every day's unit diagrams)")
    ap.add_argument("--station", required=True, help="station name as in the XML, e.g. 'London Kings Cross'; "
                                                     "several: 'London Kings Cross; Cambridge; London Bridge [10-15]' "
                                                     "(a book each, made on several CPU cores)")
    ap.add_argument("--platforms", default="", help="only these platforms, e.g. 10-15 or 1,2,4A")
    ap.add_argument("--operator", default="GTR(TLGN)", help="for the title, e.g. GTR(TLGN)")
    ap.add_argument("--timetable", default="", help="for the title, e.g. Dec23 (default: from the XML)")
    ap.add_argument("--services", default="Thameslink and Great Northern services only", help="for the title")
    ap.add_argument("--label", default="", help="sheet name before SX / SO / Su (default: station (operator))")
    ap.add_argument("--sheets", default="SX,SO,Su", help="day sheets, any of SX,SO,Su (or MO, TO ... for one day)")
    ap.add_argument("--merge", "--merge-xml", nargs="+", default=[], metavar="XML",
                    help="other operators' Attune XML(s) or VPT(s) whose trains are merged into the book")
    ap.add_argument("--name", default="", help="output name")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    a = _local_out(ap, ap.parse_args(argv))
    entries = parse_station_list(a.station)
    if len(entries) > 1:
        try:
            results = make_books(a.xml, entries, a.out, a.operator, a.timetable, a.services,
                                 [s.strip() for s in a.sheets.split(",") if s.strip()], log=print,
                                 merge_xml=a.merge)
        except StationBookError as exc:
            print("ERROR: " + str(exc))
            sys.exit(1)
        for station, path, warnings, summary, error in results:
            print(f"{station}: " + (f"ERROR {error}" if error else f"{summary} -> {path}"))
            for w in warnings:
                print("  WARNING:", w)
        sys.exit(1 if any(r[4] for r in results) else 0)
    try:
        path, warnings, summary = make_book(a.xml, a.station, a.out, a.name, a.operator, a.timetable, a.services,
                                            a.label, a.platforms, [s.strip() for s in a.sheets.split(",") if s.strip()],
                                            log=print, merge_xml=a.merge)
    except StationBookError as exc:
        print("ERROR: " + str(exc))
        sys.exit(1)
    for w in warnings:
        print("WARNING:", w)
    print(summary)


def _local_out(ap, a):
    """--out must be a folder on this PC: outputs are never written to a network or shared drive."""
    from rstools.fsutil import NETWORK_REFUSED, is_network_path
    if getattr(a, "out", "") and is_network_path(a.out):
        ap.error(NETWORK_REFUSED)
    return a


def reorder_cli(argv):
    from cwn_compare.reorder import ReorderError, reorder_cwn
    ap = argparse.ArgumentParser(prog="TrainPlanningTools reorder",
                                 description="Save a copy of a multi-day CWN with each train's day variants in "
                                             "order (MO first ... FO, then SO, Su). Nothing else is changed.")
    ap.add_argument("cwn", help="the multi-day CWN")
    ap.add_argument("--by-time", action="store_true", help="order by departure time first, then by day")
    ap.add_argument("--merge", action="store_true",
                    help="merge a train's variants that are the same apart from their days (e.g. MO + FO = MFO)")
    ap.add_argument("--merge-diagrams", action="store_true",
                    help="with --merge: also when only the diagram numbers differ (each shown with its days)")
    ap.add_argument("--merge-berths", action="store_true",
                    help="with --merge: also when they berth for the same next working (berth day codes combined)")
    ap.add_argument("--merge-berth-diagrams", action="store_true",
                    help="with --merge-berths: also when that next working's diagram number differs")
    ap.add_argument("--name", default="", help="output name")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    a = _local_out(ap, ap.parse_args(argv))
    try:
        _reorder_flags(a)                                  # checked before the CWN is read
        from cwn_compare.reorder import MergeRules
        res = reorder_cwn(a.cwn, a.out, a.name, a.by_time, log=print, merge=a.merge,
                          rules=MergeRules(a.merge_diagrams, a.merge_berths, a.merge_berths and a.merge_berth_diagrams))
    except ReorderError as exc:
        print("ERROR: " + str(exc))
        sys.exit(1)
    if res["trains"]:
        print(f"{res['trains']} train(s) on {res['tabs']} tab(s) had their day variants put in order.")


def _reorder_flags(a):
    """The --merge-* flags checked up front: each one that only refines another needs it, so a flag that would be
    ignored is an error instead. Raises ReorderError (reported by the caller); nothing here ends the process."""
    from cwn_compare.reorder import ReorderError
    if a.merge_berth_diagrams and not a.merge_berths:
        raise ReorderError("--merge-berth-diagrams goes with --merge-berths (and --merge): add them, or leave it out.")
    if (a.merge_diagrams or a.merge_berths) and not a.merge:
        raise ReorderError("--merge-diagrams and --merge-berths go with --merge: add --merge, or leave them out.")


def statspack_cli(argv):
    from rstools.days import DAYS
    from rstools.statspack.engine import (OUTPUTS, UNIT_REPORTS, PackOptions, PlanInputs, StatsPackError, build_pack,
                                          compare_packs, compare_plans, day_availability, load_plan, unit_reports,
                                          write_pack)

    ap = argparse.ArgumentParser(prog="TrainPlanningTools statspack", description="Rolling stock stats pack")
    ap.add_argument("--xml", help="Attune diagram XML")
    ap.add_argument("--trent", help="TRENT unit diagram print (.docx): VehicleLayout29 (best), 23 (also the TLGN "
                                    "print), 11 or 05; several separated by ';' (e.g. TLGN SX;SO;SU, or VL29;VL23 "
                                    "for VL23's next-day links)")
    ap.add_argument("--old-xml", help="original plan XML (compare two plans)")
    ap.add_argument("--old-trent", help="original plan TRENT print (compare two plans)")
    ap.add_argument("--old-pack", help="original stats pack (compare two packs)")
    ap.add_argument("--new-pack", help="updated stats pack (compare two packs)")
    ap.add_argument("--days", default=",".join(DAYS), help="e.g. MO,TO,WO (default: every day)")
    ap.add_argument("--operators", default="SNGX,TLGN")
    ap.add_argument("--fleets", default="", help="comma separated fleets (default: all)")
    ap.add_argument("--output", choices=sorted(OUTPUTS), default="totals_days",
                    help="totals_days: totals + every day (default); totals: totals only; days: a file per day")
    ap.add_argument("--name", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-summary", action="store_true", help="comparisons: leave out the summary of key figures")
    ap.add_argument("--changed-tabs-only", action="store_true", help="comparisons: only tabs with differences")
    ap.add_argument("--changed-rows-only", action="store_true", help="comparisons: only rows that changed")
    ap.add_argument("--flag-miles", type=float, default=10.0,
                    help="comparisons: flag mileage increases over this many miles (0 = off, default 10)")
    ap.add_argument("--format", choices=["xlsx", "pdf", "docx"], default="xlsx",
                    help="save outputs as Excel (default), PDF or Word")
    ap.add_argument("--unit-reports", default="",
                    help="instead of a stats pack: unit reports, any of washes,cets,depots,captive,fuel")
    ap.add_argument("--per-day", action="store_true",
                    help="unit and capacity reports: each day on its own (default: whole week); same as "
                         "--unit-period days")
    ap.add_argument("--unit-period", choices=["week", "days", "timetable"], default="",
                    help="unit reports: follow units through the week (default), show each day separately, or "
                         "give only the fleet totals for the entire timetable")
    ap.add_argument("--possible", choices=["every", "over", "off"], default="",
                    help="unit reports: note where a WASH, CET or FUEL could be added, for every unit (default), "
                         "only units over a limit, or not at all")
    ap.add_argument("--capacity-group", "--seats-group", dest="seats_group", default="",
                    help="capacity report for a headcode group, e.g. 1F")
    ap.add_argument("--capacity-corridor", "--seats-corridor", dest="seats_corridor", default="",
                    help="capacity report for this corridor (name as in the list)")
    ap.add_argument("--no-seating", action="store_true", help="capacity report: leave out seats")
    ap.add_argument("--no-standing", action="store_true", help="capacity report: leave out standing room")
    ap.add_argument("--corridor-direction", choices=["forward", "reverse", "both"], default="both",
                    help="corridor: forward (first to last station in the list), reverse, or both (default)")
    ap.add_argument("--capacity-from", "--seats-from", dest="seats_from", default="",
                    help="capacity report from this station (with --capacity-to)")
    ap.add_argument("--capacity-to", "--seats-to", dest="seats_to", default="",
                    help="capacity report to this station (with --capacity-from)")
    ap.add_argument("--between", default="", help="capacity report: only trains between two times, e.g. 07:00-10:00")
    ap.add_argument("--at", default="", help="capacity report: the station for --between, e.g. 'London Victoria'")
    ap.add_argument("--direction", choices=["arriving", "departing", "both"], default=None,
                    help="capacity report: count trains arriving at / departing from --at (default arriving)")
    a = _local_out(ap, ap.parse_args(argv))
    from rstools.statspack.compare import CompareOptions
    cmp = CompareOptions(summary=not a.no_summary, changed_tabs_only=a.changed_tabs_only,
                         changed_rows_only=a.changed_rows_only, flag_miles=a.flag_miles or None)
    if a.unit_period and not a.unit_reports:
        ap.error("--unit-period is used with --unit-reports")
    if a.possible and not a.unit_reports:
        ap.error("--possible is used with --unit-reports")
    if a.unit_period and a.per_day:
        ap.error("use --unit-period days instead of --per-day, not both")
    try:
        window = _capacity_window(a)          # checked before the (slow) timetable is read
        from cwn_compare import __version__ as version
        if a.old_pack or a.new_pack:
            out, n = compare_packs(a.old_pack, a.new_pack, a.out, a.name, cmp, a.format)
            print(n, "difference(s):", out)
            return
        codes = {c.strip().upper(): i for i, c in enumerate(DAYS)}
        try:
            days = sorted({codes[c.strip().upper()] for c in a.days.split(",") if c.strip()})
        except KeyError as exc:
            raise StatsPackError(f"Unknown day {exc}; use {','.join(DAYS)}")
        o = PackOptions(days=days, operators={x.strip().upper() for x in a.operators.split(",") if x.strip()},
                        fleets={x.strip() for x in a.fleets.split(",") if x.strip()} or None,
                        output=a.output, output_dir=a.out, output_name=a.name, compare=cmp, fmt=a.format,
                        possible=a.possible or "every")
        new = load_plan(PlanInputs(a.xml or "", a.trent), print, xml_optional=bool(a.unit_reports))
        for m in day_availability(new, days) + new.warnings:
            print("WARNING:", m)
        o.days = [d for d in days if d in new.trent.days()]
        old = None
        seats = a.seats_group or a.seats_corridor or a.seats_from or a.seats_to
        if (seats or a.unit_reports) and (a.old_xml or a.old_trent):
            old = load_plan(PlanInputs(a.old_xml or "", a.old_trent), print,
                            xml_optional=bool(a.unit_reports))                     # compare with this timetable
            o.days = [d for d in o.days if d in old.trent.days()]
        if seats:
            from rstools.statspack.engine import seats_report
            journey = a.seats_from or a.seats_to
            kind, name = (("Station to station", "") if journey else ("Service group", a.seats_group)
                          if a.seats_group else ("Corridor", a.seats_corridor))
            paths, warnings, summary = seats_report(new, o, kind, name, not a.per_day, window,
                                                    a.direction or "arriving", old=old,
                                                    corridor_dir=a.corridor_direction,
                                                    journey=(a.seats_from, a.seats_to),
                                                    seating=not a.no_seating, standing=not a.no_standing)
            print(summary)
        elif a.unit_reports:
            which = [w.strip().lower() for w in a.unit_reports.split(",") if w.strip()]
            bad = [w for w in which if w not in UNIT_REPORTS]
            if bad:
                raise StatsPackError(f"Unknown unit report {bad[0]!r}; use {','.join(UNIT_REPORTS)}")
            paths, warnings = unit_reports(new, o, which, a.unit_period or ("days" if a.per_day else "week"),
                                           old=old)
        elif a.old_xml or a.old_trent:
            old = load_plan(PlanInputs(a.old_xml, a.old_trent), print)
            o.days = [d for d in o.days if d in old.trent.days()]
            paths, warnings, n = compare_plans(old, new, o, version)
            print(n, "difference(s)")
        else:
            per_day, warnings = build_pack(new, o, version)
            if not per_day:
                raise StatsPackError("No diagrams match the selected days, operators and fleets.")
            paths = write_pack(per_day, o, new, version)
        for w in warnings:
            print("WARNING:", w)
        for p in paths:
            print("Saved:", p)
    except StatsPackError as exc:
        print("ERROR:", exc)
        sys.exit(1)


def _capacity_window(a):
    """--between / --at / --direction checked up front: (station, from, to) for the capacity report, or None.
    A mistake raises StatsPackError (reported by the caller) instead of being ignored; nothing here ends the
    process, so it can be called from anywhere."""
    from rstools.statspack.engine import StatsPackError
    from rstools.statspack.seats import SeatsError, parse_time
    capacity = a.seats_group or a.seats_corridor or a.seats_from or a.seats_to
    journey = a.seats_from or a.seats_to
    try:
        if (a.between or a.at or a.direction) and not capacity:
            raise StatsPackError("--between, --at and --direction are for a capacity report: add --capacity-group, "
                                 "--capacity-corridor or --capacity-from and --capacity-to.")
        if (a.at or a.direction) and not a.between:
            raise StatsPackError("--at and --direction go with --between, e.g. --between 07:00-10:00 --at Brighton.")
        if not a.between:
            return None
        start, sep, end = (part.strip() for part in a.between.partition("-"))
        if not (sep and start and end):
            raise StatsPackError(f"--between needs two times, e.g. 07:00-10:00 (not '{a.between}').")
        parse_time(start), parse_time(end)
        if journey and a.at:
            raise StatsPackError("--at is not used with --capacity-from / --capacity-to: the window is the departure "
                                 "from the first station. Leave out --at.")
        if not journey and not a.at:
            raise StatsPackError("--between needs --at STATION (the station the window is at).")
    except SeatsError as exc:                 # a time that is not a time
        raise StatsPackError(str(exc)) from exc
    return (a.at, start, end)


def timetable_cli(argv):
    from rstools.timetable.engine import run

    ap = argparse.ArgumentParser(prog="TrainPlanningTools timetable", description="Timing Tools")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--gtr", help="GTR timetable check workbook (compared with --nr)")
    g.add_argument("--prints", nargs="+", help="original train print(s), PDF or Word, or Attune VPT export(s) "
                                               "(compared with --vs)")
    g.add_argument("--lists", help="original Attune train list export (compared with --vs)")
    g.add_argument("--base-prints", nargs="+", help="Attune Single Train Report print(s) as the reference "
                                                   "(checked against --check)")
    g.add_argument("--base-list", help="Attune train list as the reference (checked against --check)")
    g.add_argument("--tpr", nargs="+", help="original Timetable Planning Rules PDF(s) (compared with --vs-tpr)")
    g.add_argument("--s4-check", metavar="XML", help="Section 4 check: the Attune XML to check against the Section 4 "
                                                     "PDF(s) in --s4 (or the rule set in use)")
    ap.add_argument("--check", help="timetable workbook (GTR or Network Rail layout) to check")
    ap.add_argument("--nr", help="Network Rail timetable workbook (the reference)")
    ap.add_argument("--vs", nargs="+", help="updated train print(s) or train list")
    ap.add_argument("--vpt", metavar="VPT", help="with --s4-check: a VPT of the same timetable, whose running lines "
                                                 "settle clashes where only some lines are blocked")
    ap.add_argument("--other-vpt", nargs="+", default=[], metavar="VPT",
                    help="with --s4-check: other operators' VPT(s), whose trains are checked too")
    ap.add_argument("--s4", nargs="+", default=[], help="Section 4 PDF(s): for --s4-check, or the original set "
                                                        "compared with --vs-s4")
    ap.add_argument("--vs-s4", nargs="+", default=[], help="updated Section 4 PDF(s), compared with --s4")
    ap.add_argument("--vs-tpr", nargs="+", default=[], help="updated TPR PDF(s), compared with --tpr")
    ap.add_argument("--highlight-pdfs", action="store_true",
                    help="with --s4 / --vs-s4 or --tpr / --vs-tpr: also save the PDFs with the changes highlighted")
    ap.add_argument("--passenger-only", action="store_true",
                    help="train prints: leave out passing times and calls without a public time (for prints where "
                         "one side does not show the intermediate timing points)")
    ap.add_argument("--name", default="", help="output name (default chosen from the inputs)")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--format", choices=["xlsx", "pdf", "docx"], default="xlsx", help="output format")
    argv = list(argv)
    if "--s4" in argv and "--vs-s4" in argv and not any(x in argv for x in ("--gtr", "--prints", "--lists",
                                                                             "--base-prints", "--base-list",
                                                                             "--tpr", "--s4-check")):
        argv.append("--s4-compare")               # --s4 OLD --vs-s4 NEW: the Section 4 comparison
    g.add_argument("--s4-compare", action="store_true", help=argparse.SUPPRESS)
    a = _local_out(ap, ap.parse_args(argv))
    if a.vs_s4 and not a.s4_compare:
        ap.error("--vs-s4 needs --s4 (the original Section 4 PDFs) and no other comparison")
    if a.vs_tpr and not a.tpr:
        ap.error("--vs-tpr is used with --tpr")
    if (a.vpt or a.other_vpt) and not a.s4_check:
        ap.error("--vpt and --other-vpt are used with --s4-check")
    if a.s4 and not (a.s4_check or a.s4_compare):
        ap.error("--s4 is used with --s4-check or --vs-s4")
    if a.highlight_pdfs and not (a.s4_compare or a.tpr):
        ap.error("--highlight-pdfs is used with --s4 / --vs-s4 or --tpr / --vs-tpr")
    if a.passenger_only and not a.prints:
        ap.error("--passenger-only is used with --prints")
    if a.s4_check:
        _section4_cli(a)
        return
    if a.s4_compare:
        mode, first, second = "s4docs", a.s4, a.vs_s4
    elif a.tpr:
        mode, first, second = "tprs", a.tpr, a.vs_tpr
    elif a.gtr:
        mode, first, second = "timetables", [a.gtr], [a.nr] if a.nr else []
    elif a.base_prints or a.base_list:
        mode = "print_tt" if a.base_prints else "list_tt"
        first, second = (a.base_prints or [a.base_list]), [a.check] if a.check else []
    else:
        mode, first, second = ("prints", a.prints, a.vs or []) if a.prints else ("lists", [a.lists], a.vs or [])
    if not second:
        ap.error("--nr is needed with --gtr, --vs with --prints / --lists, --check with --base-prints / "
                 "--base-list, and --vs-tpr with --tpr")
    from rstools.fsutil import output_folder
    out = output_folder(a.out)
    try:
        res = run(mode, first, second, out, a.name, a.format, log=print, passenger_only=a.passenger_only,
                  highlight_pdfs=a.highlight_pdfs)
    except Exception as exc:                 # readable messages from the readers and the engine
        print("ERROR:", exc)
        sys.exit(1)
    for line in res.lines:
        print(line)
    print("Saved:", res.path)


def section4_cli(argv):
    """`section4`: the Section 4 possession check of an Attune XML (the same check as `timetable --s4-check`)."""
    ap = argparse.ArgumentParser(prog="TrainPlanningTools section4",
                                 description="Section 4 check: every train in a Section 4 possession window, with "
                                             "the clashes, the trains the remarks exempt and those not checked")
    ap.add_argument("--xml", required=True, help="the Attune XML to check")
    ap.add_argument("--pdf", nargs="+", default=[], metavar="PDF",
                    help="Network Rail Section 4 PDF(s) (default: the Section 4 rule set in use)")
    ap.add_argument("--vpt", metavar="VPT", help="a VPT of the same timetable, whose running lines settle clashes "
                                                 "where only some lines are blocked")
    ap.add_argument("--other-vpt", nargs="+", default=[], metavar="VPT",
                    help="other operators' VPT(s), whose trains are checked too")
    ap.add_argument("--name", default="", help="output name (default chosen from the XML)")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--format", choices=["xlsx", "pdf", "docx"], default="xlsx", help="output format")
    a = _local_out(ap, ap.parse_args(argv))
    not_pdf = [p for p in a.pdf if not p.lower().endswith(".pdf")]
    if not_pdf:
        ap.error("--pdf takes Section 4 PDF files: " + ", ".join(not_pdf))
    for p in [a.xml] + a.pdf + ([a.vpt] if a.vpt else []) + a.other_vpt:
        if not os.path.isfile(p):
            ap.error(f"this file could not be found: {p}")
    _check_vpts(ap, a)
    a.s4_check, a.s4 = a.xml, a.pdf
    _section4_cli(a)


def _check_vpts(ap, a):
    """--vpt / --other-vpt must be Attune VPT exports (checked before any large file is read)."""
    from rstools.timetable.vpt import is_vpt
    bad = [p for p in ([a.vpt] if a.vpt else []) + list(a.other_vpt) if not (os.path.isfile(p) and is_vpt(p))]
    if bad:
        ap.error("these are not Attune VPT exports (.vpt): " + ", ".join(bad))


def _section4_cli(a):
    """Run the Section 4 check for `section4` and `timetable --s4-check` and print its summary."""
    from rstools.timetable.engine import TimetableRunError
    from rstools.timetable.section4 import Section4Error, run_check
    try:
        if not os.path.isfile(a.s4_check):
            raise Section4Error(f"This file could not be found:\n{a.s4_check}")
        missing = [p for p in a.s4 if not os.path.isfile(p)]
        if missing:
            raise Section4Error("These Section 4 PDF(s) could not be found:\n" + "\n".join(missing))
        from rstools.timetable.vpt import is_vpt
        bad = [p for p in ([a.vpt] if a.vpt else []) + list(a.other_vpt) if not (os.path.isfile(p) and is_vpt(p))]
        if bad:
            raise Section4Error("These are not Attune VPT exports (.vpt):\n" + "\n".join(bad))
        path, res, st, _start = run_check(a.s4_check, a.s4, a.out, a.name, a.format, log=print,
                                          vpt=a.vpt or "", others=a.other_vpt)
    except (Section4Error, TimetableRunError) as exc:
        print("ERROR:", exc)
        sys.exit(1)
    for w in st.warnings + res.warnings:
        print("WARNING:", w)
    print(f"{res.trains} train(s) in a possession window; {len(res.clashes)} clash(es), {len(res.exempt)} lifted "
          f"by the remarks, {len(res.skipped)} train(s) not checked"
          + (f"; {res.by_line} settled by the VPT's running lines" if res.by_line else ""))
    print("Saved:", path)


def berthing_cli(argv):
    from cwn_compare.options import PRESET_COLOURS
    from rstools.berthing import engine
    from rstools.berthing.xmlread import BerthingError

    ap = argparse.ArgumentParser(prog="TrainPlanningTools berthing", description="Berthing charts")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--xml", nargs="+", help="make a chart: the LTP Attune XML, then optionally the STP XML")
    g.add_argument("--chart", help="add a round of changes to this chart (with --original and --updated)")
    g.add_argument("--compare", nargs=2, metavar=("OLD", "NEW"), help="compare two charts")
    ap.add_argument("--layout", default="", help="the chart whose sheets, berths and notes the new chart follows "
                                                 "(default: the app's built-in layout)")
    ap.add_argument("--counts", action="store_true", help="add the unit counts of each siding location")
    ap.add_argument("--original", nargs="+", help="the Attune XML(s) the chart was made from")
    ap.add_argument("--updated", nargs="+", help="the changed Attune XML(s)")
    ap.add_argument("--issue", default="", help="the issue shown on the cover, e.g. 'Proof 2'")
    ap.add_argument("--colour", default="",
                    help="highlight colour: a name (" + ", ".join(PRESET_COLOURS) + ") or RRGGBB")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--name", default="", help="output file name, without .xlsx")
    a = _local_out(ap, ap.parse_args(argv))
    named = {k.lower(): v for k, v in PRESET_COLOURS.items()}
    colour = named.get(a.colour.lower(), a.colour.lstrip("#")) if a.colour else ""
    try:
        if colour and not (len(colour) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in colour)):
            raise BerthingError(f"'{a.colour}' is not a colour: use a name ({', '.join(PRESET_COLOURS)}) or RRGGBB.")
        if a.xml:
            res = engine.generate(a.xml, a.layout, a.out, a.name, a.issue, log=print, counts=a.counts)
        elif a.chart:
            if not (a.original and a.updated):
                raise BerthingError("--chart needs --original XML and --updated XML.")
            res = engine.add_round(a.chart, a.original, a.updated, colour or "92D050", a.out, a.name, a.issue,
                                   log=print, counts=a.counts)
        else:
            res = engine.compare_charts(a.compare[0], a.compare[1], colour or "FFFF00", a.out, a.name, log=print,
                                        counts=a.counts)
    except BerthingError as exc:
        print("ERROR:", exc)
        sys.exit(1)
    print(res.summary)
    for w in res.warnings:
        print("WARNING:", w)
    print("Saved:", res.chart)
    if res.report:
        print("Saved:", res.report)


def workings_berthing_cli(argv):
    from cwn_compare.workings_berthing import WorkingsError, add_berthing
    ap = argparse.ArgumentParser(prog="TrainPlanningTools workings-berthing",
                                 description="Save a copy of platform workings (Victoria, London Bridge or "
                                             "Brighton) with each day's Berthing Arrangements made from its trains")
    ap.add_argument("--workings", required=True, help="the platform workings (.xlsx)")
    ap.add_argument("--xml", nargs="*", default=[], help="optional Attune XML(s): gives the siding road each "
                                                         "unit stands on")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--name", default="", help="output file name, without .xlsx")
    a = _local_out(ap, ap.parse_args(argv))
    for path in [a.workings, *a.xml]:
        if not os.path.isfile(path):
            ap.error(f"this file could not be found: {path}")
    try:
        res = add_berthing(a.workings, a.xml, a.out, a.name, log=print)
    except WorkingsError as exc:
        print("ERROR:", exc)
        sys.exit(1)
    print(res.summary)
    print("Saved:", res.chart)


def selftest_cli(argv):
    """Checks the packaged exe (used by the build): its fast PDF reader reads an Attune print, the built-in
    Section 4 rule set is inside it, and a window opens with drag and drop (the tkdnd files bundled must match the
    exe's Tcl/Tk)."""
    from rstools.timetable.prints import _pdfium_lines
    if argv and argv[0] in ("-h", "--help"):
        print("usage: TrainPlanningTools selftest ATTUNE_PRINT.pdf\n\nChecks the built exe: it reads an Attune print "
              "with PDFium, finds its built-in Section 4 rules and berthing layout, and opens a window with drag "
              "and drop. Exits with 1 if anything is wrong.")
        return
    path = argv[0] if argv else ""
    pages = _pdfium_lines(path) if path else None
    if not pages:
        print("ERROR: the fast PDF reader (PDFium) could not read", path or "(no file given)")
        sys.exit(1)
    print(f"PDFium OK: {len(pages)} page(s)")
    from rstools import rules
    if rules._builtin_data() is None:
        print("ERROR: the built-in Section 4 rule set is missing from the exe")
        sys.exit(1)
    print(f"Rules OK: {rules.BUILT_IN_S4}, {len(rules._builtin_data()['possessions'])} possession rows")
    from rstools.berthing.layout import default_info
    lay = default_info()
    if lay is None:
        print("ERROR: the built-in berthing chart layout is missing from the exe")
        sys.exit(1)
    print(f"Layout OK: berthing chart layout from {lay['source']}, {lay['sheets']} sheets")
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print("SKIPPED window check (no display):", exc)
        return
    try:
        from tkinterdnd2 import TkinterDnD
        version = TkinterDnD._require(root)
        print(f"Window OK: Tcl/Tk {root.tk.call('info', 'patchlevel')}, drag and drop (tkdnd {version})")
    except Exception as exc:
        print("ERROR: drag and drop could not be loaded:", exc)
        sys.exit(1)
    finally:
        root.destroy()


COMMANDS = ("stationbook", "reorder", "statspack", "timetable", "section4", "berthing", "workings-berthing",
            "selftest")


def main(argv):
    """Open the window (no arguments), run a subcommand, or compare two CWNs (arguments starting with --)."""
    first = argv[0].lower() if argv else ""
    runners = {"statspack": statspack_cli, "stationbook": stationbook_cli, "reorder": reorder_cli,
               "timetable": timetable_cli, "section4": section4_cli, "berthing": berthing_cli,
               "workings-berthing": workings_berthing_cli, "selftest": selftest_cli}
    if first in runners:
        runners[first](argv[1:])
    elif argv and not argv[0].startswith("-"):
        sys.stderr.write(f"TrainPlanningTools: unknown command '{argv[0]}' (commands: {', '.join(COMMANDS)}; "
                         "or compare CWNs with --original and --updated; run with --help for the options)\n")
        sys.exit(2)
    elif argv:
        cli(argv)
    else:
        from cwn_compare.gui import main as open_window
        open_window()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # lets the packaged exe start its helper process
    main(sys.argv[1:])
