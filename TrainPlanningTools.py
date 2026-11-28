"""Train Planning Tools - entry point.

Double-click (or run with no arguments) to open the desktop app.
Command-line use:
    TrainPlanningTools.exe --original OLD.xlsx --updated NEW.xlsx [--acwn] [--name NAME] [--out DIR]
    TrainPlanningTools.exe --previous PREVIOUS_OUTPUT.xlsx --updated NEW.xlsx --colour 92D050
    TrainPlanningTools.exe --original OLD.xlsx --updated NEW.xlsx --days FO   (Friday trains only)
    TrainPlanningTools.exe --original-folder OLD_FOLDER --updated NEW_FOLDER    (every pair of CWNs)
    TrainPlanningTools.exe stationbook --xml PLAN.xml --station "London Kings Cross" [--platforms 10-15]
                                       [--sheets SX,SO,Su] [--book-operator TLGN|SNGX|GTR]
                                       [--merge OTHER_OPERATOR.xml|.vpt|.cif|F3.pdf ...] [--other-operators XC,SE]
    TrainPlanningTools.exe reorder CWN.xlsx [--by-time] [--merge ...] [--name NAME] [--out DIR]  (day variants in order)
    TrainPlanningTools.exe berthing --xml LTP.xml [STP.xml] --layout CHART.xlsx [--issue "Proof 1"]
    TrainPlanningTools.exe berthing --chart CHART.xlsx --original OLD.xml --updated NEW.xml [--colour "Light green"]
    TrainPlanningTools.exe berthing --compare OLD_CHART.xlsx NEW_CHART.xlsx [--colour Orange]
    TrainPlanningTools.exe berthing --blank [--operator TLGN] [--xml LTP.xml] [--leave-out ...] [--add ...]
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
    TrainPlanningTools.exe statspack --xml PLAN.xml --trent VL29.docx --mileage-period timetable|month|custom
    TrainPlanningTools.exe workings-berthing --workings WORKINGS.xlsx [--xml PLAN.xml ...] [--others OTHER.cif ...]
    TrainPlanningTools.exe other-trains --file CWN_OR_WORKINGS.xlsx --others OTHER.xml|.vpt|.cif [...]
    TrainPlanningTools.exe selftest ATTUNE_PRINT.pdf     (checks a built exe)
The README's "Command line" section lists every option.
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
    ap.add_argument("--colour", default=None, help="highlight colour: a name (Yellow, \"Light green\", Orange...) "
                                                   "or hex RRGGBB, e.g. FFFF00")
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
    ap.add_argument("--exclude", default="", help="comma-separated categories to strip, e.g. PLATFORM,STOCK")
    ap.add_argument("--days", default="", help="check and output only trains running on these days, e.g. MO,FO")
    a = _local_out(ap, ap.parse_args(argv))
    import re
    if a.colour:                             # a preset name (as in the window) or RRGGBB
        from cwn_compare.options import PRESET_COLOURS
        a.colour = {k.lower(): v for k, v in PRESET_COLOURS.items()}.get(a.colour.strip().lower(), a.colour)
    if a.colour and not re.fullmatch(r"#?[0-9A-Fa-f]{6}", a.colour):
        ap.error(f"--colour must be a colour name ({', '.join(PRESET_COLOURS)}) or a hex colour such as FFFF00, "
                 f"not '{a.colour}'")
    if a.acwn and a.highlight_only:
        ap.error("--acwn and --highlight-only cannot be used together (an ACWN has only the changed trains)")
    if a.original_folder:
        extra = [f for f, v in (("--name", a.name), ("--days", a.days)) if v]
        if extra:
            ap.error(f"{', '.join(extra)} cannot be used with --original-folder: each pair is named after its CWNs "
                     "and every day is compared")
    o = Options()
    unknown = [k for k in filter(None, (x.strip().upper() for x in a.exclude.split(","))) if k not in o.categories]
    if unknown:
        ap.error(f"--exclude: unknown categor{'y' if len(unknown) == 1 else 'ies'} {', '.join(unknown)} "
                 f"(choose from {', '.join(o.categories)})")
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
        for label, folder in (("original", o.original), ("updated", o.updated)):
            if not os.path.isdir(folder):
                print(f"ERROR: the {label} folder '{folder}' does not exist.")
                sys.exit(1)
        if os.path.normcase(os.path.abspath(o.original)) == os.path.normcase(os.path.abspath(o.updated)):
            print("ERROR: the original and updated folders are the same folder.")
            sys.exit(1)
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
        try:
            run_batch(pairs, o, done)
        except Exception as exc:              # e.g. the output folder could not be made
            from rstools import errorlog
            print("ERROR:", errorlog.file_problem(exc) or exc)
            sys.exit(1)
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
    ap.add_argument("--xml", required=True, help="Attune diagram XML (preferred: with every day's unit diagrams) or "
                                                 "a VPT (no stock column)")
    ap.add_argument("--station", required=True, help="station name as in the XML, e.g. 'London Kings Cross'; "
                                                     "several: 'London Kings Cross; Cambridge; London Bridge [10-15]' "
                                                     "(a book each, made on several CPU cores)")
    ap.add_argument("--platforms", default="", help="only these platforms, e.g. 10-15 or 1,2,4A")
    ap.add_argument("--book-operator", default="TLGN", type=str.upper, choices=("TLGN", "SNGX", "GTR"),
                    help="whose trains the book has (by unit diagram depot) and its title: TLGN, SNGX or GTR "
                         "(all GTR trains). Default TLGN")
    ap.add_argument("--operator", default="", help="title text instead of the book operator's, e.g. GTR(TLGN)")
    ap.add_argument("--timetable", default="", help="for the title, e.g. Dec23 (default: from the XML)")
    ap.add_argument("--services", default="", help="for the title (default: from --book-operator, e.g. "
                                                   "'Thameslink and Great Northern services only')")
    ap.add_argument("--label", default="", help="sheet name before SX / SO / Su (default: station (operator))")
    ap.add_argument("--sheets", default="SX,SO,Su", help="day sheets, any of SX,SO,Su (or MO, TO ... for one day)")
    ap.add_argument("--merge", "--merge-xml", nargs="+", default=[], metavar="FILE",
                    help="other operators' files whose trains are merged into the book: Attune XML (preferred, "
                         "gives the stock), VPT, Network Rail CIF or Attune Single Train Report (F3) print "
                         "(.pdf / .docx)")
    ap.add_argument("--other-operators", default=None, metavar="OPS",
                    help="only these merged operators, e.g. XC,SE (default: all of them); needs --merge")
    ap.add_argument("--name", default="", help="output name")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    a = _local_out(ap, ap.parse_args(argv))
    if a.other_operators is not None and not a.merge:
        ap.error("--other-operators chooses among the merged operators: give their files with --merge")
    from rstools.stationbook import DAY_GROUPS, SINGLE_DAYS
    sheets = [s.strip() for s in a.sheets.split(",") if s.strip()]
    bad = [s for s in sheets if s not in DAY_GROUPS and s not in SINGLE_DAYS]
    if bad or not sheets:                    # refused before the XML is read, not left out silently
        ap.error(f"--sheets: {'unknown ' + ', '.join(bad) if bad else 'none given'} (use any of "
                 f"{', '.join(dict.fromkeys([*DAY_GROUPS, *SINGLE_DAYS]))})")
    others = None if a.other_operators is None else [o.strip() for o in a.other_operators.split(",") if o.strip()]
    entries = parse_station_list(a.station)
    if len(entries) > 1:
        extra = [f for f, v in (("--name", a.name), ("--label", a.label), ("--platforms", a.platforms)) if v]
        if extra:
            ap.error(f"{', '.join(extra)} apply to one station: with several, give platforms in the list "
                     "('London Bridge [10-15]') and each book is named after its station")
        try:
            results = make_books(a.xml, entries, a.out, a.operator, a.timetable, a.services,
                                 [s.strip() for s in a.sheets.split(",") if s.strip()], log=print,
                                 merge_xml=a.merge, book_operator=a.book_operator, other_operators=others)
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
                                            log=print, merge_xml=a.merge, book_operator=a.book_operator,
                                            other_operators=others)
    except StationBookError as exc:
        print("ERROR: " + str(exc))
        sys.exit(1)
    for w in warnings:
        print("WARNING:", w)
    print(summary)


def _local_out(ap, a):
    """--out must be a folder on this PC: outputs are never written to a network or shared drive."""
    from rstools.fsutil import NETWORK_REFUSED, is_network_path
    out = getattr(a, "out", "")
    if out and is_network_path(out):
        ap.error(NETWORK_REFUSED)
    if out and not os.path.isdir(out):     # never quietly saved somewhere else (as the window refuses it too)
        ap.error(f"--out: the folder '{out}' does not exist. Create it first, or leave --out out to save to "
                 "Downloads.")
    return a


def reorder_cli(argv):
    from cwn_compare.loader import LoadError
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
    except (ReorderError, LoadError) as exc:          # a damaged or non-CWN file: its reader's own message
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
    from rstools.statspack.engine import (OUTPUTS, PackOptions, PlanInputs, StatsPackError, build_pack,
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
    ap.add_argument("--operators", default="SNGX,TLGN", help="operators whose diagrams count (default: SNGX,TLGN)")
    ap.add_argument("--fleets", default="", help="comma-separated fleets (default: all)")
    ap.add_argument("--output", choices=sorted(OUTPUTS), default="totals_days",
                    help="totals_days: totals + every day (default); totals: totals only; days: a file per day")
    ap.add_argument("--name", default="", help="output name (default: made from the plan)")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
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
    ap.add_argument("--mileage-period", choices=["timetable", "month", "custom"], default="",
                    help="instead of a stats pack: the mileage tabs added up over the whole timetable, one month "
                         "(--month) or from --period-from to --period-to; each date counts its own diagrams, STP "
                         "ones only on the dates they are valid for")
    ap.add_argument("--month", default="", help="with --mileage-period month: e.g. 'January 2027' or 2027-01")
    ap.add_argument("--period-from", default="", metavar="DATE",
                    help="with --mileage-period custom: the first date (DD/MM/YYYY or YYYY-MM-DD)")
    ap.add_argument("--period-to", default="", metavar="DATE",
                    help="with --mileage-period custom: the last date (DD/MM/YYYY or YYYY-MM-DD)")
    a = _local_out(ap, ap.parse_args(argv))
    if a.mileage_period:
        clash = [flag for flag, value in (("--old-xml", a.old_xml), ("--old-trent", a.old_trent),
                                          ("--old-pack", a.old_pack), ("--new-pack", a.new_pack),
                                          ("--unit-reports", a.unit_reports), ("--capacity-group", a.seats_group),
                                          ("--capacity-corridor", a.seats_corridor), ("--capacity-from", a.seats_from),
                                          ("--capacity-to", a.seats_to), ("--per-day", a.per_day)) if value]
        if clash:
            ap.error(f"{', '.join(clash)} cannot be used with --mileage-period")
        if (a.mileage_period == "month") != bool(a.month):
            ap.error("--month goes with --mileage-period month (and it needs one)")
        if (a.mileage_period == "custom") != bool(a.period_from or a.period_to) or \
                (a.mileage_period == "custom" and not (a.period_from and a.period_to)):
            ap.error("--period-from and --period-to go with --mileage-period custom (and it needs both)")
    elif a.month or a.period_from or a.period_to:
        ap.error("--month, --period-from and --period-to are used with --mileage-period")
    from rstools.statspack.compare import CompareOptions
    cmp = CompareOptions(summary=not a.no_summary, changed_tabs_only=a.changed_tabs_only,
                         changed_rows_only=a.changed_rows_only, flag_miles=a.flag_miles or None)
    if a.unit_period and not a.unit_reports:
        ap.error("--unit-period is used with --unit-reports")
    if a.possible and not a.unit_reports:
        ap.error("--possible is used with --unit-reports")
    if a.unit_period and a.per_day:
        ap.error("use --unit-period days instead of --per-day, not both")
    if (a.old_pack or a.new_pack) and a.xml:
        ap.error("--old-pack / --new-pack compare two stats packs: leave out --xml (or compare the plans instead)")
    capacity = any((a.seats_group, a.seats_corridor, a.seats_from, a.seats_to))
    if a.per_day and not (a.unit_reports or capacity):
        ap.error("--per-day is used with --unit-reports or a capacity report")
    _statspack_combinations(ap, a, capacity)  # every mix of flags checked before any file is read
    try:
        window = _capacity_window(a)          # checked before the (slow) timetable is read
        _capacity_names(a)
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
        if a.mileage_period:
            from rstools.statspack.engine import period_mileage
            paths, warnings, summary = period_mileage(new, o, a.mileage_period, version, a.month, a.period_from,
                                                      a.period_to)
            print(summary)
        elif seats:
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
            which = [w.strip().lower() for w in a.unit_reports.split(",") if w.strip()]   # checked up front
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


def _statspack_combinations(ap, a, capacity: bool):
    """Flags that cannot go together, or that only one kind of run uses, refused up front (not ignored)."""
    from rstools.statspack.engine import UNIT_REPORTS
    if a.unit_reports:
        which = [w.strip().lower() for w in a.unit_reports.split(",") if w.strip()]
        bad = [w for w in which if w not in UNIT_REPORTS]
        if bad or not which:
            what = f"unknown unit report {bad[0]!r}" if bad else "--unit-reports needs at least one report"
            ap.error(f"{what} (use any of {','.join(UNIT_REPORTS)})")
    if a.seats_group and a.seats_corridor:
        ap.error("choose --capacity-group or --capacity-corridor, not both")
    if bool(a.seats_from) != bool(a.seats_to):
        ap.error("--capacity-from and --capacity-to go together")
    if (a.seats_from or a.seats_to) and (a.seats_group or a.seats_corridor):
        ap.error("--capacity-from / --capacity-to is a capacity report of its own: leave out --capacity-group and "
                 "--capacity-corridor")
    if capacity and a.unit_reports:
        ap.error("run a capacity report or --unit-reports, not both at once")
    if a.no_seating and a.no_standing:
        ap.error("--no-seating and --no-standing together leave nothing to count")
    if (a.no_seating or a.no_standing) and not capacity:
        ap.error("--no-seating and --no-standing are used with a capacity report")
    if a.corridor_direction != "both" and not a.seats_corridor:
        ap.error("--corridor-direction is used with --capacity-corridor")
    if a.old_pack or a.new_pack:
        if a.old_xml or a.old_trent:
            ap.error("--old-pack / --new-pack compare two stats packs: leave out --old-xml and --old-trent")
        if capacity or a.unit_reports:
            ap.error("--old-pack / --new-pack compare two stats packs: leave out the capacity and unit report flags")
    comparing = bool(a.old_pack or a.new_pack or a.old_xml or a.old_trent)
    used = [f for f, v in (("--no-summary", a.no_summary), ("--changed-tabs-only", a.changed_tabs_only),
                           ("--changed-rows-only", a.changed_rows_only)) if v]
    if used and not comparing:
        ap.error(f"{', '.join(used)} used with a comparison (--old-xml / --old-trent or --old-pack / --new-pack)")
    if a.between:
        start, _sep, end = (part.strip() for part in a.between.partition("-"))
        if start and start == end:
            ap.error("--between: the two times are the same, so nothing can be in the window")
    if a.flag_miles is not None and a.flag_miles < 0:
        ap.error("--flag-miles must be 0 (off) or more")
    packs = bool(a.old_pack or a.new_pack)
    from rstools.days import DAYS
    every_day = {d.strip().upper() for d in a.days.split(",") if d.strip()} == {d.upper() for d in DAYS}
    if a.output != "totals_days" and (packs or capacity or a.unit_reports or a.mileage_period):
        ap.error("--output chooses how a stats pack is saved: leave it out of capacity, unit and mileage-period "
                 "reports and stats pack comparisons")
    if not every_day and (packs or a.mileage_period):
        ap.error("--days is not used " + ("when comparing two stats packs (they keep their own days)" if packs else
                                          "with --mileage-period (every date of the period counts)"))
    if packs and (a.fleets or a.operators != "SNGX,TLGN"):
        ap.error("--operators and --fleets are not used when comparing two stats packs (they keep their own)")


def _capacity_names(a):
    """The group or corridor named for a capacity report is checked against the list before the plan is read."""
    if not (a.seats_group or a.seats_corridor):
        return
    from rstools.statspack.engine import seats_group
    kind, name = ("Service group", a.seats_group) if a.seats_group else ("Corridor", a.seats_corridor)
    seats_group(kind, name, a.corridor_direction)    # StatsPackError when it is not known


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
    ap.add_argument("--other-vpt", "--other", nargs="+", default=[], metavar="FILE", dest="other_vpt",
                    help="with --s4-check: other operators' VPT(s) (preferred) or Attune Single Train Report (F3) "
                         "prints (.pdf / .docx), whose trains are checked too")
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
    flags = {x.split("=", 1)[0] for x in argv if x.startswith("--")}      # '--s4 A.pdf' or '--s4=A.pdf'
    if "--s4" in flags and "--vs-s4" in flags and not flags & {"--gtr", "--prints", "--lists", "--base-prints",
                                                               "--base-list", "--tpr", "--s4-check"}:
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
    if a.check and not (a.base_prints or a.base_list):
        ap.error("--check is used with --base-prints or --base-list")
    if a.nr and not a.gtr:
        ap.error("--nr is used with --gtr")
    if a.vs and not (a.prints or a.lists):
        ap.error("--vs is used with --prints or --lists")
    if a.s4_check:
        bad = _s4_files_problem(a)
        if bad:                              # reported as before the section4 subcommand: ERROR, exit code 1
            print("ERROR:", bad)
            sys.exit(1)
        _run_section4(a)
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
    ap.add_argument("--other-vpt", "--other", nargs="+", default=[], metavar="FILE", dest="other_vpt",
                    help="other operators' VPT(s) (preferred) or Attune Single Train Report (F3) prints "
                         "(.pdf / .docx), whose trains are checked too")
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
    _run_section4(a)


def _other_ok(path: str) -> bool:
    """An other operator's file for the Section 4 check: an Attune VPT export, or a train print (PDF / Word) -
    whether it is an Attune Single Train Report is checked when it is read."""
    from rstools.timetable.vpt import is_vpt
    return os.path.isfile(path) and (is_vpt(path) or path.lower().endswith((".pdf", ".docx", ".docm")))


def _check_vpts(ap, a):
    """--vpt must be an Attune VPT export, --other-vpt VPTs or F3 prints (checked before any large file is read)."""
    from rstools.timetable.vpt import is_vpt
    bad = [p for p in ([a.vpt] if a.vpt else []) if not (os.path.isfile(p) and is_vpt(p))]
    bad += [p for p in a.other_vpt if not _other_ok(p)]
    if bad:
        ap.error("these are not Attune VPT exports (.vpt) or F3 prints (.pdf / .docx): " + ", ".join(bad))


def _s4_files_problem(a) -> str:
    """What is wrong with the Section 4 check's files ('' if nothing): checked before any of them is read."""
    missing = [p for p in [a.s4_check] + a.s4 if not os.path.isfile(p)]
    if missing:
        return "These files could not be found:\n" + "\n".join(missing)
    from rstools.timetable.vpt import is_vpt
    bad = [p for p in ([a.vpt] if a.vpt else []) if not is_vpt(p)] + [p for p in a.other_vpt if not _other_ok(p)]
    if bad:
        return "These are not Attune VPT exports (.vpt) or F3 prints (.pdf / .docx):\n" + "\n".join(bad)
    return ""


def _section4_cli(a):
    """Run the Section 4 check for `section4` and `timetable --s4-check` and print its summary. Both callers
    have already checked the files; the check's own errors (Section4Error, TimetableRunError) are raised for the
    command to report (_run_section4)."""
    from rstools.fsutil import output_folder
    from rstools.timetable.section4 import run_check
    path, res, st, _start = run_check(a.s4_check, a.s4, output_folder(a.out), a.name, a.format, log=print,
                                      vpt=a.vpt or "", others=a.other_vpt)
    for w in st.warnings + res.warnings:
        print("WARNING:", w)
    print(f"{res.trains} train(s) in a possession window; {len(res.clashes)} clash(es), {len(res.exempt)} lifted "
          f"by the remarks, {len(res.skipped)} train(s) not checked"
          + (f"; {res.by_line} settled by the VPT's running lines" if res.by_line else ""))
    print("Saved:", path)


def _run_section4(a):
    """The Section 4 check from a command: its own errors end the run with an ERROR line and exit code 1."""
    from rstools.timetable.engine import TimetableRunError
    from rstools.timetable.section4 import Section4Error
    try:
        _section4_cli(a)
    except (Section4Error, TimetableRunError) as exc:
        print("ERROR:", exc)
        sys.exit(1)


def berthing_cli(argv):
    from cwn_compare.options import PRESET_COLOURS
    from rstools.berthing import engine
    from rstools.berthing.xmlread import BerthingError

    ap = argparse.ArgumentParser(prog="TrainPlanningTools berthing", description="Berthing charts")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--xml", nargs="+", help="make a chart: the LTP Attune XML, then optionally the STP XML "
                                            "(with --blank: the XML(s) to take the locations and dates from)")
    g.add_argument("--chart", help="add a round of changes to this chart (with --original and --updated)")
    g.add_argument("--compare", nargs=2, metavar=("OLD", "NEW"), help="compare two charts")
    ap.add_argument("--blank", action="store_true",
                    help="make a blank chart (sheets, berths, capacities and notes, no units) to fill in by hand; "
                         "--xml is optional")
    ap.add_argument("--timetable", default="", help="with --blank and no --xml: the timetable for the cover's "
                                                    "title, e.g. 'May 2027'")
    ap.add_argument("--from", dest="date_from", default="", metavar="YYYY-MM-DD",
                    help="with --blank and no --xml: the first date on the cover")
    ap.add_argument("--to", dest="date_to", default="", metavar="YYYY-MM-DD",
                    help="with --blank and no --xml: the last date on the cover")
    ap.add_argument("--layout", default="", help="the chart whose sheets, berths and notes the new chart follows "
                                                 "(default: the app's built-in layout)")
    ap.add_argument("--counts", action="store_true", help="add the unit counts of each siding location")
    ap.add_argument("--operator", default="SNGX", type=str.upper, choices=["SNGX", "TLGN"],
                    help="with --xml: SNGX (the built-in layout, default) or TLGN (a sheet for every place TLGN "
                         "units berth overnight, made from the XML)")
    ap.add_argument("--leave-out", nargs="+", default=[], metavar="LOCATION",
                    help="with --xml: sheets to leave off the chart (sheet names or TIPLOCs)")
    ap.add_argument("--add", nargs="+", default=[], metavar="LOCATION",
                    help="with --xml: locations to add a sheet for (names or TIPLOCs from the XML)")
    ap.add_argument("--others", nargs="+", default=[], metavar="FILE",
                    help="with --xml or --chart: other operators' files (Attune XML, VPT or Network Rail CIF); "
                         "their units are added in grey, matched by place where the file has no next-day workings")
    ap.add_argument("--no-notes", action="store_true",
                    help="leave the location notes off the chart (by default they are shown, with any changed for "
                         "the XML's timetable in the app's Settings > Berthing notes)")
    ap.add_argument("--original", nargs="+", help="the Attune XML(s) the chart was made from")
    ap.add_argument("--updated", nargs="+", help="the changed Attune XML(s)")
    ap.add_argument("--issue", default="", help="the issue shown under the cover's title, e.g. 'Proof 2' or 'Final' "
                                                "(the title is the timetable the XML is for)")
    ap.add_argument("--colour", default="",
                    help="highlight colour: a name (" + ", ".join(PRESET_COLOURS) + ") or RRGGBB")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--name", default="", help="output file name, without .xlsx")
    a = _local_out(ap, ap.parse_args(argv))
    blank_only = [("--timetable", a.timetable), ("--from", a.date_from), ("--to", a.date_to)]
    if a.blank:
        extra = [flag for flag, value in [("--chart", a.chart), ("--compare", a.compare), ("--original", a.original),
                                          ("--updated", a.updated), ("--colour", a.colour), ("--others", a.others),
                                          ("--counts", a.counts)] if value]
        if a.xml:
            extra += [flag for flag, value in blank_only if value]
        if extra:
            ap.error(f"{', '.join(extra)} cannot be used with --blank" + (" and --xml (the XML gives the "
                                                                           "timetable and dates)" if a.xml else ""))
        if a.layout and a.operator != "SNGX":
            ap.error(f"--layout cannot be used with --operator {a.operator}")
        if bool(a.date_from) != bool(a.date_to):
            ap.error("--from and --to go together")
        try:
            res = engine.blank(a.operator, a.layout, a.xml or [], a.out, a.name, a.issue, a.timetable, a.date_from,
                               a.date_to, a.leave_out, a.add, log=print, show_notes=not a.no_notes)
        except BerthingError as exc:
            print("ERROR:", exc)
            sys.exit(1)
        print(res.summary)
        for w in res.warnings:
            print("WARNING:", w)
        print("Saved:", res.chart)
        return
    if not (a.xml or a.chart or a.compare):
        ap.error("one of --xml, --chart, --compare or --blank is required")
    used_blank = [flag for flag, value in blank_only if value]
    if used_blank:
        ap.error(f"{', '.join(used_blank)} can only be used with --blank")
    chart_only = [("--operator", a.operator != "SNGX"), ("--leave-out", a.leave_out), ("--add", a.add)]
    ignored = {"--compare": [("--layout", a.layout), ("--issue", a.issue), ("--original", a.original),
                             ("--updated", a.updated), ("--others", a.others), ("--no-notes", a.no_notes)]
                + chart_only,
               "--xml": [("--original", a.original), ("--updated", a.updated), ("--colour", a.colour)],
               "--chart": [("--layout", a.layout)] + chart_only}
    used = "--compare" if a.compare else "--xml" if a.xml else "--chart"
    extra = [flag for flag, value in ignored[used] if value]
    if extra:
        ap.error(f"{', '.join(extra)} cannot be used with {used}")
    if a.xml and a.layout and a.operator != "SNGX":
        ap.error(f"--layout cannot be used with --operator {a.operator} (its chart is laid out from the XML)")
    named = {k.lower(): v for k, v in PRESET_COLOURS.items()}
    colour = named.get(a.colour.lower(), a.colour.lstrip("#")) if a.colour else ""
    try:
        if colour and not (len(colour) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in colour)):
            raise BerthingError(f"'{a.colour}' is not a colour: use a name ({', '.join(PRESET_COLOURS)}) or RRGGBB.")
        if a.xml:
            res = engine.generate(a.xml, a.layout, a.out, a.name, a.issue, log=print, counts=a.counts,
                                  operator=a.operator, leave_out=a.leave_out, add=a.add, others=a.others,
                                  show_notes=not a.no_notes)
        elif a.chart:
            if not (a.original and a.updated):
                raise BerthingError("--chart needs --original XML and --updated XML.")
            res = engine.add_round(a.chart, a.original, a.updated, colour or "92D050", a.out, a.name, a.issue,
                                   log=print, counts=a.counts, others=a.others, show_notes=not a.no_notes)
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
    ap.add_argument("--others", nargs="+", default=[], metavar="FILE",
                    help="other operators' files (Attune XML, VPT or Network Rail CIF): their units berthed at the "
                         "platforms are added to the arrangements (the workings' own rows are not changed)")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--name", default="", help="output file name, without .xlsx")
    a = _local_out(ap, ap.parse_args(argv))
    for path in [a.workings, *a.xml, *a.others]:
        if not os.path.isfile(path):
            ap.error(f"this file could not be found: {path}")
    try:
        res = add_berthing(a.workings, a.xml, a.out, a.name, log=print, others=a.others)
    except WorkingsError as exc:
        print("ERROR:", exc)
        sys.exit(1)
    print(res.summary)                          # add_berthing has logged where it saved


def other_trains_cli(argv):
    from cwn_compare.other_trains import OtherTrainsError, add_other_trains
    ap = argparse.ArgumentParser(prog="TrainPlanningTools other-trains",
                                 description="Save a copy of a CWN or platform workings with other operators' trains "
                                             "added in time order (grey italics, the operator code as the stock). "
                                             "The existing rows are not changed.")
    ap.add_argument("--file", required=True, help="the CWN or platform workings (.xlsx)")
    ap.add_argument("--others", nargs="+", required=True, metavar="FILE",
                    help="other operators' files: Attune XML, VPT or Network Rail CIF")
    ap.add_argument("--out", default="", help="output folder on this PC (default: Downloads)")
    ap.add_argument("--name", default="", help="output file name, without .xlsx")
    a = _local_out(ap, ap.parse_args(argv))
    for path in [a.file, *a.others]:
        if not os.path.isfile(path):
            ap.error(f"this file could not be found: {path}")
    try:
        res = add_other_trains(a.file, a.others, a.out, a.name, log=print)
    except OtherTrainsError as exc:
        print("ERROR:", exc)
        sys.exit(1)
    print(res.summary)
    for w in res.warnings:
        print("WARNING:", w)
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
            "other-trains", "selftest")


def main(argv):
    """Open the window (no arguments), run a subcommand, or compare two CWNs (arguments starting with --)."""
    first = argv[0].lower() if argv else ""
    runners = {"statspack": statspack_cli, "stationbook": stationbook_cli, "reorder": reorder_cli,
               "timetable": timetable_cli, "section4": section4_cli, "berthing": berthing_cli,
               "workings-berthing": workings_berthing_cli, "other-trains": other_trains_cli,
               "selftest": selftest_cli}
    if first in runners:
        runners[first](argv[1:])
    elif argv and not argv[0].startswith("-"):
        sys.stderr.write(f"TrainPlanningTools: unknown command '{argv[0]}' (commands: {', '.join(COMMANDS)}; "
                         "or compare CWNs with --original and --updated; run with --help for the options)\n")
        sys.exit(2)
    elif argv:
        cli(argv)
    else:
        _open_window()


def _open_window():
    """The window. The exe has no console, so a failure while it opens goes in error.log and a message box -
    never a silent exit."""
    try:
        from cwn_compare.gui import main as open_window
        open_window()
    except Exception as exc:
        import traceback
        from rstools import errorlog
        errorlog.write(traceback.format_exc())
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Train Planning Tools", errorlog.describe(exc), parent=root)
            root.destroy()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # lets the packaged exe start its helper process
    main(sys.argv[1:])
