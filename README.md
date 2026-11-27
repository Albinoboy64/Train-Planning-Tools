<img src="packaging/logo.png" alt="Train Planning Tools logo" width="96" align="right">

# Train Planning Tools

A portable Windows desktop app for GTR train planning (formerly *Rolling Stock Tools* and *CWN Compare*). It has four tabs:

* **Stock Tools** compares two **Carriage Working Notices (CWNs)**, puts a multi-day CWN's day variants in order ([see below](#putting-day-variants-in-order)) and makes **TRACS-RS style station working books** from an Attune XML ([see below](#station-working-book-tracs-rs-layout)). A comparison produces:
  1. **A comparison CWN.** This is the updated CWN with every amendment highlighted in a colour you choose. Tabs that contain changes are highlighted too.
  2. **A change report.** This is a separate Excel workbook summarising every change by category, by location tab and by train.
* **Stats Pack** builds the rolling stock stats pack (the same tabs and figures as the TRACS-RS stats pack), **unit reports** (washes and CETs, depot returns and swaps, captive units, the 171 fuel check) and **capacity reports** from an Attune diagram XML and the TRENT unit diagram prints (SNGX and TLGN). It can also compare two plans, or two stats packs, to show the mileage and other effects of a new plan. See [Stats Pack](#stats-pack).
* **Timing Tools** checks a timetable against the Network Rail timetable, Attune **train prints** or an Attune **train list** (each as the reference) and writes the approved *Consolidated TT Comparison* workbook. It also compares two sets of train prints (PDF or Word) or Attune VPT exports, two Attune train list exports (Excel), two sets of **Section 4** documents and two sets of **Timetable Planning Rules**, and runs the **Section 4 check** (the trains running in a possession window). See [Timing Tools](#timing-tools).
* **Live View** shows any of these comparisons inside the app, train by train, and refreshes as you save the files. See [Live View](#live-view).

## Running it (no admin rights needed)

1. Download `TrainPlanningTools.exe` (or `TrainPlanningTools-portable.zip`, which also contains this guide) from the latest release on the [Releases](https://github.com/Albinoboy64/Train-Planning-Tools/releases) page.
2. Save `TrainPlanningTools.exe` anywhere you can write to, such as your Desktop, Documents or a network drive. Whatever it runs from, its outputs are only ever saved on your PC (see [Where outputs are saved](#where-outputs-are-saved)).
3. Double-click it. Nothing is installed, and no admin rights or Python are needed.

### "Windows protected your PC" / unknown publisher

Windows shows this warning for any downloaded program that isn't **digitally signed** with a code-signing certificate. The app itself can't switch the warning off. The exe carries its name, version, publisher ("GTR Train Planning") and icon in *Properties → Details*, and its start-up code is built specially to avoid false antivirus alerts. The publisher only shows as verified once the exe is signed.

Updates installed with *Help > Check for updates* never show this warning: the app downloads them itself, so they don't carry the "downloaded from the internet" mark. Only the first download from the browser does.

Ways to stop the warning, from quickest to most complete:

1. **Unblock it once.** Right-click `TrainPlanningTools.exe` (or the zip, *before* extracting it), choose **Properties**, tick **Unblock**, then **OK**. Windows won't warn again for that copy.
2. **Run it from a GTR network share.** Programs on an internal file share don't carry the "downloaded from the internet" mark, so SmartScreen doesn't prompt. Unblock it once, copy it to the shared drive, and the team runs it from there.
3. **Ask IT to allow it.** IT can publish the exe through Company Portal / Intune, or allow it by its file hash or publisher. Each release's notes on GitHub give the exe's SHA-256 hash for this.
4. **Sign it (removes "unknown publisher" for good).** Get a code-signing certificate, either from GTR/Govia IT or from a public certificate authority such as DigiCert or Sectigo. Then add two repository secrets on GitHub: `SIGNING_CERT_PFX_BASE64` (the `.pfx` file, base64-encoded) and `SIGNING_CERT_PASSWORD`. Every build is then signed and time-stamped automatically. To base64-encode the certificate in PowerShell, run
   `[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx")) | Set-Clipboard`.
   A certificate from an internal GTR certificate authority is trusted on GTR-managed PCs. A public one is trusted everywhere. A brand-new public certificate can still show a SmartScreen notice until it builds up reputation.

Your option choices, theme, recent files, rule sets, fleet data and the error log are kept in a **TrainPlanningTools-data** folder beside the exe, so the app is portable: move or copy the exe and that folder together. If the exe's folder cannot be written to, they are kept in `%LOCALAPPDATA%\TrainPlanningTools` instead (nothing is written to the registry). The first time the data folder is made, settings already saved in `%LOCALAPPDATA%` are copied into it. *Data > Open settings folder* shows where they are. Recent-file lists show each file's name (with its folder where two share a name); *Options > Show full paths in recent files* shows the whole path instead. A file that has been moved, renamed or deleted is listed in red with that note, and hovering over a file shows its full path beside the list. Help tips never open over a drop-down list. Press **F5** or **Ctrl+Enter** to run the current tab. *Options > Theme* switches between *Follow Windows*, *Light*, *Dark* and *High contrast*.

**Menus and keyboard.** *Options* has the theme, text size and notifications; *Data* has the lists and rules the tasks read (fleet data, depot list, corridors, *Rules and reference data*, the settings folder); *Save/Load* keeps each tab's files and options to load or run again; *Help* has the user guide, keyboard shortcuts, updates and the error log. Shortcuts: **F5** or **Ctrl+Enter** run the tab, **Esc** stops a run, **Ctrl+1** to **4** or **Ctrl+Tab** switch tabs, **Ctrl+F** finds a train in the Live View and **Space** confirms it (*Help > Keyboard shortcuts* lists them all).

**Accessibility.** *Options > Text size* makes all text in the app *Small*, *Normal*, *Large* or *Extra large* (also **Ctrl +**, **Ctrl -** and **Ctrl 0**); boxes, columns and tables grow with it. *High contrast* is white text on black with yellow buttons and focus outlines and cyan selections (the Windows high-contrast colours), and *Follow Windows* switches to it automatically when Windows high-contrast mode is on. Both only change the app window, not the outputs. The app uses the Windows fonts: Segoe UI Variable (Windows 11) or Segoe UI for text and Cascadia Mono or Consolas for logs.

### Updates

*Help > Check for updates...* finds the latest release, shows what's new and installs it in place (the app closes and reopens on the new version). The repository is public, so no account or token is needed. (For a private copy of the repository, add a read-only access token once in *Help > GitHub access token...*: on GitHub go to *Settings > Developer settings > Personal access tokens > Fine-grained tokens*, give it access to that repository only with *Contents: Read-only*, and paste it in. The token is stored encrypted for your Windows login (DPAPI) and is only ever sent to GitHub.)

**Upgrading from 3.11.0 or earlier:** those versions look for updates in the app's previous repository, which is now private, so they report that GitHub did not allow access. Download **TrainPlanningTools.exe** from this repository's [Releases](https://github.com/Albinoboy64/Train-Planning-Tools/releases) once and replace the old exe; your settings are kept, and updates work from the app again after that.

### Where outputs are saved

Every output (comparison CWNs, change reports, tidied CWNs, station books, berthing charts, stats packs, unit and capacity reports, timetable comparisons) is saved **on your PC only**. Leave *Save to folder* blank to save to your **Downloads** folder (where Windows keeps it, even if IT has moved it). A folder on a network or shared drive (a `\\server\share` path or a drive letter mapped to one) is refused, whether it is chosen, typed or was saved in your settings, and the box goes back to blank. A batch of CWN comparisons with no folder chosen goes into a folder in Downloads named after the updated CWNs' folder. On the command line, `--out` must also be a local folder. Settings stay in the app's data folder as before.

### Dragging and dropping files

Files can be dropped on any tab. Dropped on a file box (or its label or *Browse* button), a file **replaces** what is in that box (a box that takes several train prints adds it). Dropped anywhere else, each file goes to an empty box that takes it; when every such box is full it **replaces** the file in the box it belongs in (e.g. a second CWN replaces the *Updated CWN*). Two files for a pair of boxes go in date order, the older first.

## Using the app (Stock Tools tab)

| Step | What to do |
|---|---|
| Task | Choose the task from the **Task** list at the top. The list has a heading for each group - **CWNs and platform workings**, **Berthing charts**, **Station books** - and the tasks in the order the work goes. Only what the chosen task needs is shown below. |
| 1. Input | **Compare two CWNs**, **Add a new round to an earlier comparison CWN** or **Compare two folders of CWNs (batch)**, then the **Original CWN** and the **Updated CWN** (in the same section), either with *Browse* or by **dragging and dropping** the files onto this section. If you drop both files at once, the older file becomes the original. Use *Swap* if they end up the wrong way round. In "add a new round" mode, the first file is a comparison CWN that this app made earlier. The same **Input** section holds the one-file tools: **Put each train's day variants in order (one CWN)** ([see below](#putting-day-variants-in-order)) and the **Station Working Book** ([see below](#station-working-book-tracs-rs-layout)), with their own box and drop area. |
| 2. Output | **Full CWN with changes highlighted and noted** (previous values struck through, change notes and cancelled trains put back, as set under *3. Changes to include*), **Full CWN with new or changed items highlighted only** (the updated CWN as it is, with anything new or changed highlighted and no original versions: no previous values, notes or cancelled trains, which are still in the change report), or **ACWN** (amended trains only, with unchanged trains and unchanged tabs removed). Pick the highlight colour, the output folder (blank: Downloads) and the output name. If you leave the name blank, today's date and the two CWN names are used, e.g. `19-11-2026 Proof 1 vs Proof 2`. *Keep links between tabs* keeps the clickable headcode links; it's off by default because they make the file much slower to open in Excel. |
| 3. Changes to include | For each change type, choose whether it is **shown in the CWN**, whether the **previous value / note** is shown, and whether it is **included in the report** |
| 4. Run | Press **Compare** (or *Compare folders* / *Add round*), then use *Open output*, *Open report* or *Open folder* |

Supported input formats are `.xlsx`, `.xlsm`, `.xls`, `.xlsb`, `.xltx` and `.xltm`. The output is always `.xlsx`.

### How trains are compared

The comparison is **train to train, not row to row**:

* Each location tab is split into train entries. An entry is the headcode row plus its coupled-unit rows and note rows, such as `(via Redhill)`.
* Entries are matched by **headcode (and days run) within the same location tab**. A train that has moved to a different line, or a tab that has moved position in the workbook, is **not** treated as a change.
* **Day splits are not treated as new or changed trains.** For example, an SX train might become FSX and FO entries. Each new part is compared with the original train, ignoring the days code, and only real differences, such as a different time or platform on the FO part, are highlighted. Merges work the same way, for example FSX + FO becoming SX.
* Unit diagram numbers (DIAG) are only used to line up coupled units. Diagram changes are not checked or highlighted.
* Values are normalised before they are compared. Fonts, bold, italics, fills, spacing, case, the bracket markers on coupled units, and `5.10` vs `05.10` are all ignored, so **formatting-only edits are not reported**.

### Change types

| Change type | Detected when | Shown in the CWN as |
|---|---|---|
| Cancelled train | The headcode no longer appears anywhere in the updated CWN | The train is re-inserted **struck through and highlighted**. You can switch this off to remove it entirely. |
| New train | The headcode was not in the original CWN | The whole train entry is highlighted |
| Time change | TIME, inward departure or INWARDS time changed | The new time is highlighted, with the old time **struck through above it** |
| Location change | Destination, FROM, start/call/pass (LOC) changed, or the train was added to / removed from a location tab | New value highlighted, old value struck through. A train removed from a tab is re-inserted struck through. |
| Platform change | PL changed | New platform highlighted, old platform struck through above |
| Stock / unit change | Unit type changed, or a unit was added or removed | New value highlighted, old value struck through. Removed units are shown struck through. |
| Inbound / outbound working change | An inbound service now forms a different outbound service, or vice versa | Both affected trains are highlighted, and a note is added, e.g. *"Amended: previously formed from 1W08BT"* or *"Amended: inbound 5C02BT previously formed 2C02BT"* |
| Berthing / next-day working change | AM/PM berth changed, or a next-day working or berth line really changed (berth road or next time). Re-ordered lines and day-of-week-only differences are ignored. | New value highlighted, old value struck through |
| Days run change | DAYS changed | If nothing else about the train changed, only the days cell is highlighted, with no old value. Otherwise the new value is highlighted with the old value struck through above it. |
| Notes / routing change | A note row was added or removed | Added notes are highlighted. Removed notes are shown struck through. |

Old values are written **in the same cell**: the previous value is struck through on the line above the new one, in the cell's own font, so it reads like the rest of the sheet. The row height is increased to fit, and a column is only widened if a value would otherwise wrap. Times are always shown as `HH.MM`, or `HH+MM` for ECS moves.

For each type you can:

* **Show in CWN.** Untick to strip that change type out of the CWN entirely. For cancelled trains, unticking removes them from the CWN instead of showing them struck through.
* **Show previous value / note.** Untick to only highlight the new data. No previous values, struck-through rows or notes are added. The *Highlight only* button unticks this for every type.
* **Notes** explaining a change (e.g. *Amended: previously formed from 1W08BT*) go in a **Change notes** column just to the right of the CWN, on the row of the change they explain.
* Only cells that hold text are coloured. A new or re-inserted train is not coloured across its empty cells.
* **Include in report.** Untick to strip that change type out of the report entirely.

### Comparing two folders of CWNs (batch)

Choose **Compare two folders of CWNs (batch)** under *1. Input* (or drop two folders on the tab), then choose the folder of original CWNs and the folder of updated CWNs.
* Each updated CWN is paired with its original: the same file name first, then the same name ignoring proof, draft and version numbers (*Proof 2*, *v1.2*, *V1_2*, *D12*), dates (*14-12-2026*, *14_12_2026*, a *260918_* stamp) and words such as *final* or *CWN*, then the clearly most similar name. Underscores and hyphens count as spaces, so `260918_-_GTRTLGN_Dec26_D12_Draft_CWN_-_SX` pairs with `261002_-_GTRTLGN_Dec26_D13_Draft_CWN_-_SX`. The pairs found are shown under the folders, and you confirm the list before it starts. Files that can't be paired are listed and left out.
* Every pair gets the same options (output type, colour, report, change types) and its own comparison CWN and change report, named as usual.
* Several pairs are compared at once, one per CPU core with one core left free for the window, and only as many as fit in free memory. One file that can't be read doesn't stop the others; it is shown in the log.
* The day tickboxes are not used for folders: every day is checked.

### Checking only some days of the week

Under *2. Output*, **Days to check** lists Mon-Sun. Once both CWNs are chosen, the app reads which days they cover and greys out the others. Untick days to check and output only the trains running on the ticked days. For example, tick only *Fri* to get just the Friday trains from a Monday-Friday CWN.
* A train's days come from its DAYS cell: blank = every day the CWN covers, `MO` / `FO` / `ThFO` = those days only, `MX` / `FSX` = the CWN's days except those. The days a CWN covers come from its wording (e.g. *Mondays to Fridays* on the cover or above the headings), its file name (`SX`, `SO`, `Su`...) and the DAYS codes used. If none of these say, the note under the tickboxes says the days were judged from the DAYS codes.
* The comparison CWN then holds only those trains, the change report says which days were checked, and the default name ends with the days, e.g. `... (Fri)`.
* A train that still runs on other days but no longer on a chosen day is reported as a **Days** change ("No longer runs on the chosen day(s)"), never as cancelled.
* Every day is ticked again whenever new files are chosen, so a day filter is never left on by accident.

### Putting day variants in order

A multi-day CWN often lists the day variants of the same train (for example 1A23 MO, 1A23 TWThO and 1A23 FO) in no particular order. Choose **Put each train's day variants in order (one CWN)** choose the CWN (or drop it on the Input box) and press **Put variants in order**. A copy is saved, e.g. `Proof 2 (variants in day order).xlsx`; the CWN itself is not touched.
* **By first day run** (default): the first day each variant runs decides its place, whatever the departure times: an MO or MWO variant first, then TO, then WO, ThFO, FO, then SO and Su. Variants are put in order even when they run hours apart or either side of midnight.
* **By departure time**: the earliest-departing variant first (an FO train at 05.30 before an MO train at 06.10), then day order for variants at the same time.
* **Merge variants that are the same apart from their days** (optional), tab by tab: on each tab, two or more variants of a train with the same times, platforms, destination, activity, units, inward working and notes on that tab become one, with the days of both in its DAYS cell (MO and FO become *MFO*; MTWThO and FO in a weekday CWN become one with no days code, like any every-day train). The DAYS column is widened when a merged code needs more room. **AM / PM berths never keep variants apart**: they say where the unit starts and ends its day, not anything about this location. Where they differ, the cell shows the berth used on most days followed by a teal **▾**; click the cell to see every day's berth (Excel shows a small box listing e.g. *MTWThO: THBDTGS* and *FO: EBOUSID*, and a drop-down with the same list). The log lists each variant that was kept apart and the first thing that differs on that tab (e.g. *2C02BT (TO) kept apart from 2C02BT (MO) (platform: 7 vs 8)*). The rows of the variants merged away are removed, the rows below move up, and links to them lead to the merged variant. The copy is named e.g. `Proof 2 (variants in day order, merged).xlsx`. Three further options widen what may differ:
  * **Also when only the diagram numbers differ**: the DIAG cell shows the diagram used on most days with a **▾**; click it to see each day's diagram (e.g. *WSX: 549*, *WO: 549A*). A diagram used by one variant keeps that variant's own code.
  * **Also when they berth for the same next working**: variants whose berth lines lead to the same train next day (e.g. *Berth HE317 05.17TO* on MO, *...05.17WO* on TO, *...05.17ThO* on WO, *...05.17FO* on ThO) become one, and the berth line's day code covers them all: *Berth HE317 05.17TWThFO*. A variant berthing for a different next working (another time or train, e.g. *Berth HE317 04.49SO* on FO) stays separate.
  * **... also when that next working's diagram number differs**: berthing for the same next working on a different diagram (HE317 one day, HE318 another) still merges; the berth line shows the diagram for most days with a **▾** (*Berth HE317 ▾ 05.17TWThFO*), and clicking it lists each one with its next-day days.
* On the command line the three extra options only refine `--merge`, so `--merge-diagrams` and `--merge-berths` need `--merge`, and `--merge-berth-diagrams` needs `--merge-berths`; a flag that would be ignored stops the run with a message, before the CWN is read.
* Only the variants of the same train swap places, within the rows they already used, so every other train stays exactly where it was. Rows move whole: values, formatting, row heights, notes and coupled-unit rows. Links from other tabs are re-pointed to the rows' new positions. Nothing else is changed or removed.
* A tab with merged cells or formulas among its trains is left as it was (moving rows could break them), and the log says so.
* **A comparison CWN made by this app can be put in order too.** Its highlights, struck-through previous values and change notes move with their rows; variants merge only if their changes are shown exactly the same way, so no highlighted change is hidden. The comparison data inside it is kept, so it can still have rounds added (a new round is laid out like its updated CWN, so put that in order again afterwards).
* Put the variants in order before comparing if you want the comparison CWN to follow the same order.
* The ▾ marker is ignored when a tidied CWN is read again (compared, or put in order again).
* **Diagram numbers (DIAG, AM and PM cells) are not links** in the copy: clicking one stays on the cell, so its each-day values (the ▾ box) can be read. Tab links on headcodes are kept and follow their rows.

### Station Working Book (TRACS-RS layout)

Choose **Create a station working book from an Attune XML (TRACS-RS layout)** then the Attune XML (in the Input box, or drop it there; an Attune XML with the unit diagrams is preferred, a VPT export also works but gives no stock), the **station**, and optionally:
* **Platforms**, e.g. `10-15` for the London Bridge low level book, or `1, 2, 4A`.
* **Operator**: **TLGN** (Thameslink and Great Northern), **SNGX** (Southern and Gatwick Express) or **All GTR**. It decides which of GTR's trains the book has and its page header, file name and sheet names (e.g. *GTR(SNGX) Dec26 Station Working Book - Brighton (Southern and Gatwick Express services only)*). Each train's operator comes from the depot of the unit diagrams that work it (SNGX: BI, SU, SL; TLGN: HE, TB). Trains worked by neither operator's diagrams are only in an *All GTR* book; the run's messages list any left out. Command line: `--book-operator TLGN|SNGX|GTR` (default TLGN).
* **Timetable** for the page header and file name, e.g. *Dec23* (filled in from the XML), and **Services** for the header (blank: the operator's, e.g. *Thameslink and Great Northern services only*).
* **Sheet name**, e.g. *London Bridge LL* (default: the station and the operator in brackets, e.g. *London Kings Cross (TLGN)*), and which **sheets**: SX, SO, Su.
* **Other operators** (optional): one or more files from other operators - an **Attune XML** (preferred: it has the unit diagrams, so it gives the stock), an Attune **VPT** export (`.vpt`) or an Attune **Single Train Report (F3) print** (PDF or Word). A VPT or print has no unit diagrams, so its trains show working times and a blank stock; a print names each train's own operator (e.g. *SN* from *Greater Thameslink Railway (Southern)*). Drop `.vpt` files (or prints, while the Station book task is chosen) to add them. Their trains calling at the station are merged into the book, each marked with its operator under the stock (e.g. `[XC]`); a train or diagram ID the book already has is renamed *ID/OPERATOR*. The files must cover the same dates. Command line: `--merge OTHER.xml|.vpt|F3.pdf [...]`.
* **Other operators shown**: tick which of the operators found in those files are shown (all by default; one ticked off stays off for files added later). Command line: `--other-operators XC,SE` (needs `--merge`).
* **Several stations** at once: pick a station (and any platforms) and press **Add to list**, or type them separated by `;` with platforms in brackets, e.g. `London Kings Cross; London Bridge [10-15]; Cambridge`. Each station gets its own book (named after the station), made on several CPU cores at once; a station that cannot be found is reported and the others are still made. Command line: `--station "London Kings Cross; Cambridge"`.

The book has the TRACS-RS layout: one row per train leaving the station, in departure order **by stock day** (as in the CWN): each day starts with the first train of that day's unit diagrams, and a train worked after midnight by the previous day's diagram is at the end of that previous day, not the start of the next. Trains with no unit diagram stay on the day they run. It uses Calibri 13, the blue heading row repeated on each page, row heights fitted to the text, the page header and *page/pages* footer:

| Column | What it shows |
|---|---|
| Train ID / Origin Time / Station of Origin / Arrival Time | The train(s) the units arrive on (in their order in the departing train, front first), *Berth* when a unit starts the day in the platform, and *RP* / *FP* when the departing train is the rear / front portion of a train that divides here. For a train calling here, its own origin and arrival. |
| Train ID (Stock) | The departing headcode and one line per unit, front first, e.g. `(387/1)` |
| Origin Time, Origin, Destination | Of the departing train |
| Departure Time (Platform) | e.g. `05 02 (9)` |
| Calling points | Every later passenger stop with its public arrival time, the destination in capitals; *Empty to ...* for empty stock; *The train divides at Purley / The front 5 coaches call at: ... / The rear 5 coaches call at: ...*; and *Runs Monday and Friday only* (etc.) where a row is not the same on every day of the sheet. |

Passenger trains (classes 1, 2 and 9) show public times as `HH MM`; other trains show working times as `HH+MM`. Checked against the TRACS-RS London Bridge 10-15 book from the same timetable: every train's inward working, attaching and dividing trains, stock, berthing and *RP* / *FP* portions came out in the same form; the differences were from the example being an earlier version of that timetable (a minute here, a platform there) and TRACS-RS's own location names (see below).

**The best input data.** One **Attune diagram XML export of the timetable, including the unit diagrams for every day the book covers** (Monday to Sunday for SX, SO and Su sheets). It holds everything the book needs: every train's times, public times, platforms and stops, and the unit diagrams - which units work each train (front to rear), the train each unit arrives on, where trains attach and divide, and where units stable. Export it from the same plan as the book, with **all operators' trains** you want shown (e.g. EMR at Bedford). The app warns if a day's unit diagrams are missing (the stock and inward workings are blank on those days). Seats and coach counts (for *the front 5 coaches*) come from the fleet data. Locations are named as in the XML; TRACS-RS uses its own location names (e.g. *Selhurst TRSMD* where Attune has *Selhurst T&R.S.M.D*, and sometimes a TIPLOC such as *STWTBS*), so names can differ slightly from older books.

Command line: `stationbook --xml PLAN.xml --station "London Kings Cross" [--platforms 10-15] [--book-operator TLGN|SNGX|GTR] [--operator "title text"] [--timetable Dec23] [--services "..."] [--label "..."] [--sheets SX,SO,Su] [--merge OTHER.xml|.vpt|F3.pdf ...] [--other-operators XC,SE]`.

### Berthing charts

Under *Berthing charts* on the Stock Tools tab (drop XMLs and charts on that box):

* **Create a berthing chart from an Attune XML**: where every unit berths each night at the out-berth platforms and sidings. Choose the **Attune XML** (an export with every day's unit diagrams). The chart is laid out in the app's **built-in layout** (taken from the SNGX Dec 26 Proof 2 chart: 26 sheets, 131 berths, with each sheet's siding locations, capacities and notes); or choose an earlier chart under **Layout from chart (optional)** to follow that one instead. Its sheets, berths, capacities and notes are kept, the units come from the XML, and the old formulas, counting rows (*Start1* ... *Finish1*, *\*4 377\** rows) and damaged formatting are left out. *Issue on cover* (e.g. *Proof 1*) goes on the cover with the XML's dates. A new chart starts without highlights.
* **Layout**: the siding names and capacities are shaded light blue as on the original charts, and notes about the sidings (*NO ATTACH /DETACH Allowed*, *CE*, *4 car MAX*) are in **red bold**; long notes get a full-width row under their siding location. Every berth's box on a sheet is the same height (enough for the fullest berth on that sheet) and every day column the same width, whether or not stock is there. A darker line separates the nights and a thin one each night's FINISH and START, and a **dark blue line** separates the siding locations on a sheet (e.g. Brighton's platforms and Wall Siding; Three Bridges' Back Road, Up Horsham Siding, Up Siding North and Tilgate).
* **Show unit counts for each siding location** (option): under each siding location, the number of units of each type (e.g. *4 377*, *4 387*, *12 700*) every night's FINISH and START, and a **Cars** row against the location's capacity, filled red where there are more cars than it holds.
* **Location notes**: **Show location notes on the chart** (on by default) puts each location's notes on the chart; untick it (or `--no-notes`) to leave every note off. **Data > Berthing chart notes...** (or *Edit notes...*) changes them for a timetable: choose the **timetable** (the current one and the next five, e.g. *May 26*, *Dec 26*, *May 27* ...) and the **location** (every berth of the built-in layout), then edit the note beside its name (shown where the berth has no capacity) and its notes, one per line (*A | B* for the two columns; a long note goes across the day columns). *Remove notes* leaves that berth without notes for the timetable, *Back to built-in* uses the layout's own again and *Copy from previous timetable* starts from the timetable before. Every chart made for that timetable (from the XML's start date) uses them; a berth not changed keeps its notes. They are kept in `berth_notes.json` in the settings folder.
* **STP charts**: attach the **STP XML** as well. Each day's STP diagrams replace the LTP ones, and STP trains are shown **in bold on a lavender fill**.
* **Add a round of changes to a berthing chart**: the chart, the **original XML** it was made from and the **updated XML** (for an STP chart, the LTP and STP XMLs separated by `;`). The chart is remade from the updated XML, every cell that differs is filled in the chosen colour, earlier highlights are kept, and a change report lists each change. The cover's *Updates highlighted in ...* line follows the colour.
* **Compare two berthing charts**: every unit or time in the newer chart that differs from the older one is highlighted, with a change report. Spacing slips (`(4 387) 00 45`), the old `L` marker and `12700` / `12 700` are not differences.

Each row is one unit's stay: its arrival in the night's **FINISH** column and its departure in the next **START** column (`02+02` an empty move, `0500` a passenger train), **Berth** on any day it stays put, and **RP** when it leaves as the rear portion of another train, attached to by a unit that moved onto it that day. Coupled units sit on consecutive rows in brackets, front first, with the time on the first row; the latest arrival is at the top. 387/2 (Gatwick Express) are in red, 387/3 (Southern) in green, and Thameslink 700s end `TLK`. The depot sheet (Lovers Walk) lists each unit type's arrivals and departures in time order.

Which XML location each berth is comes from the **berth list** (*Edit berth locations...*): sheet, berth as written on the chart, TIPLOC and the platform or road codes Attune uses (e.g. Brighton *Plat 7* = BRGHTN 7 / 7F, Eastbourne *No 3 Siding* = EBOUSID S3). Units berthing on a platform or road the sheet has no berth for are listed at the bottom of that sheet, and everything that needs checking is on the chart's **Notes** sheet. Command line: `TrainPlanningTools.exe berthing --xml LTP.xml [STP.xml] [--layout CHART.xlsx] [--counts] [--no-notes]`. The built-in layout can be remade from a newer chart with `python -m rstools.berthing.layout CHART.xlsx` (for a new release).

### Platform workings

The platform workings sent to Victoria, London Bridge and Brighton (one workbook per station: a Cover and a tab for each day, with the Thameslink trains at London Bridge and Brighton) work in the same tasks as CWNs:

* **Compare two CWNs or platform workings**, **Compare two folders (batch)** and **Add a new round to an earlier comparison** read them by their headings (Train, Time, Ln, Plat, Destination, cars, Stock, Op, Time, From, Pos, Ln, Due, Train). Trains are matched by headcode within each day's tab. As well as the changes listed above, a change of **line** (Ln), **number of cars** or **operator** (Op) is reported, and so is each line of a day's **Berthing Arrangements** (Platform 14, NO 2 CARRIAGE SIDING ...), shown highlighted with the old text struck through. The cover's *Updates highlighted in ...* line names the colour of each round. *Days to check* picks day tabs. Supplement numbers (*Supp 1*, *Supplement No 2*) are ignored when folders are paired.
* **Add berthing arrangements to platform workings** makes the *Berthing Arrangements* section under each day, which the CWN export does not make. Choose the workings (and, optionally, the Attune XML); a copy is saved as `... (berthing added).xlsx`, and the file itself is not touched.
  * **Platforms**: every unit that berths at a platform (the *Berth BI151 05.50TO (3)* lines) is added up by platform and by the train it works next, e.g. *12 377 for 05 50 TO*. Platforms 15 and 15F are one platform; longest wait first. The next day's tab is checked: the train must leave that platform from *Berth* (if the berthed unit leaves as the rear portion it reads *for RP 06 20 TO*), and a unit berthed for more than a night is added from the tab it leaves on. Anything that does not match is in the log as *CHECK*.
  * **Sidings** (Victoria and Battersea Pier carriage sidings, Brighton Wall Siding): units stand there from when they arrive until a train takes them out, carried across the days of the week; each is matched to the first train that leaves the siding (*8 377 for 05+28 TO*), looking on to the days after if none leaves the next day. The working does not say which road (No 1 / No 2, Rec / 2) a unit is on: give the **Attune XML** and the road comes from it; without one, groups are put on the roads in order and the log says *check the road*.
  * **Wording** follows each station: Victoria writes Sunday as *SUN*, London Bridge adds *TLK* to 700s (*8 700 TLK for 09 10 SuO*) and joins two lines on a platform with *&*, Brighton leaves *TLK* out. Platforms and sidings with nothing on them say *EMPTY*.
  * If a tab already has a hand-made section, it is replaced and every line that differs is in the log (*DIFFERENT: Monday Platform 14: was ..., now ...*), so the hand-made lines can be checked.
  * Command line: `workings-berthing --workings WORKINGS.xlsx [--xml PLAN.xml ...] [--out FOLDER] [--name NAME]`.

### Add new comparisons to previously generated comparison CWN

Every comparison CWN stores a hidden data sheet containing the clean data it was built from. To add a further round:

1. Choose **Add new comparisons to previously generated comparison CWN**.
2. Select the earlier comparison CWN as the first file, and the latest CWN as the updated file.
3. Choose a **different colour** for the new amendments. The app picks one automatically if you leave the colour that was already used.

The new output contains the earlier amendments in their **original colour** and the latest amendments in the **new colour**. If a value changed in both rounds, both old values are shown struck through above the current value. The report has a *Round* column and a colour key. You can repeat this for as many rounds as you need.

The first file can be a full comparison CWN or an ACWN.

### Change report contents

* **Summary.** Run details, the colour key for each round, counts by category, and counts by location tab.
* **All Changes.** One line per change, filterable: Tab, Train, Category, Field, Was, Now, Details. *Details* only says what the other columns don't (e.g. *now formed from 1W10BT (previously formed from 1W08BT)*, or a cancelled train's time and destination). A *Round* column is added when the report covers more than one round.
* **Changes by Train.** Each affected train with its change types, tabs and details.
* **New and Cancelled Trains.** One list in time order, with a Status column.

## Stats Pack

### Input files

You need **two files from the same plan**:

| File | Where it comes from |
|---|---|
| **Attune XML** | The rolling stock diagram export (`diagramExchange`) from Attune. LTP, STP and draft diagrams can all be read; where a train has an STP version for a day it is used instead of the LTP one. |
| **TRENT diagram print** | The TRENT **VehicleLayout29** unit diagram print, saved as Word (`.docx`): TIPLOCs, full headcodes (e.g. `1F93BT`), LTP/STP, platforms and the miles of each service. It covers SNGX and TLGN diagrams. Several VL29 prints can go in **one box** (*Browse* lets you pick several; dropping several onto the box adds them all), e.g. the LTP print with a week's STP print; a diagram in two prints is read once. Other TRENT layouts (VehicleLayout23 - also the TLGN unit diagram print - 11 and 05) are refused with a message saying to use VehicleLayout29. |

> **The Attune XML must be exported from the same plan as the TRENT diagram print.** The TRENT print gives the diagrams, formations and mileage; the XML adds calling points, passes, public times and seconds. If the two don't match, the app warns you and lists the trains it could not find in the XML. A train leaving after midnight in a diagram is found under the next day in the XML, as Attune files it. **Unit reports** can be made from the TRENT print alone (leave the XML blank).

### Using the Stats Pack tab

| Step | What to do |
|---|---|
| Task | **Stats packs**: **Create a stats pack**, **Compare two plans** (an original and an updated XML + TRENT print), or **Compare two stats pack files**; **Reports**: **Unit reports**, **Capacity report**. Only what the task needs is shown below. |
| 1. Input | Choose the files with *Browse*, or **drag and drop** them onto the boxes or anywhere on the tab: each file goes to the right box by its type (`.xml`, `.docx`, `.xlsx`). Dropping two XMLs or two TRENT prints switches to *Compare two plans*, with the older file as the original; dropping two stats packs switches to *Compare two stats pack files*. |
| 2. Options | For unit and capacity reports: which reports, the period, and comparing two timetables |
| 3. Output | Where to save, the name and the format |
| 4. Days, operators and fleets | Tick the **diagram days** (MO, TO, WO, ThO, FO, SO, Su), the **operators** and the **fleets**. Days missing from the chosen TRENT print or XML are listed straight away. **SNGX** is diagrams from depots **BI, SU and SL**; **TLGN** is depots **HE and TB** (any other depot counts under the operator of its stock in the fleet data, or *Other*). Each operator has a row of its fleets (SNGX: 171/7, 171/8, 377/x, 387/2, 387/3; TLGN: 379/0, 387/1, 700/0, 700/1, 717/0); ticking an operator ticks its fleets. Fleets that aren't in the TRENT print are greyed out, and MAINT is unticked by default. |
| Output choices | Choose **one workbook with the totals for the ticked days, then every day's tabs** (`MO Fleet`, `MO Service Miles`...), **one workbook with the totals only**, or **a separate workbook for each day**. A single ticked day always gives a single-day pack laid out like the TRACS-RS one. Leave the name blank for `Stats pack for DEC26` (comparisons: `DEC26 vs MAY27`). |
| 5. Run | Press **Create stats pack** (or *Compare plans* / *Compare stats packs*), then *Open output* or *Open folder*. Your choices (mode, days, operators, fleets, output type and folder) are remembered for next time. |

If a ticked day isn't in the TRENT print or the XML, you're told which ones before the pack is written. Days missing from the TRENT print are left out. Problems reading either file (wrong TRENT layout, damaged XML, a file open elsewhere) are shown as a message, and anything unusual is listed as a warning in the log.

Values the app can't work out (for example a fleet with no capacity data, or an unknown coupled diagram) are shown as `???`, as TRACS-RS does, and carry through to the totals.

### Comparisons

* **Compare two plans** builds both stats packs with the same days, operators and fleets, then writes the updated plan's pack with every difference highlighted.
* **Compare two stats pack files** reads two stats packs (made by this app or by TRACS-RS) and compares them in the same way.

In both, changed cells are **amber**, rows only in the updated pack are **green**, and rows only in the original pack are added at the bottom of each tab in **red, struck through**. A **Differences** tab at the front has:

* a **summary of key figures**, original vs updated and the change: trains, train miles (loaded / empty / total), unit and vehicle miles, diagrammed and wheel-turning time, diagrams, and units and vehicles in use - the mileage impact of a plan at a glance;
* the number of differences on each tab;
* every difference with the old value, the new value and the change (e.g. `+12.40` miles or `+0:35:00`).

Comparison options (under *4. Output*): **Flag mileage increases over 10 miles** (on by default; change the number as needed), **Summary of key figures** (on by default), **Changed tabs only** (leave out tabs with no differences) and **Changed rows only** (on each tab, only rows that changed, plus totals) - the last two make large comparisons much smaller and quicker to review.

### Unit reports (washes and CETs, depot returns / swaps, captive units, fuel check)

Choose **Unit reports** under *Task*, tick the reports you want, the days, operators and fleets, then **Create unit report** (`Unit report for DEC26`). Choose the period: **Whole week** (each unit is followed from day to day), **Show each day separately** (each diagram, and the totals by fleet for every day with a total for each day and for all the days) or **Entire timetable** (only the totals by fleet, all the ticked days together).

* **Washes** and **CETs** are separate reports with their own tabs (*Washes by Unit*, *Washes by Fleet*, *CETs by Unit*, *CETs by Fleet*, or *by Diagram* for each day separately). A unit followed through the week lists its diagrams (e.g. `MO BI105 > TO BI112 > ...`) and the **most days in a row without a wash**. A unit should not go **more than 3 days without a wash**: the *Washes by Unit* tab says which units do, and so do the log and the *Notes* tab. A summary by fleet shows the washes per unit and how many units get no wash (or no CET). The *Inferred Links* tab lists every link made by matching where a unit stabled to where a diagram starts: where it stabled, what it forms next, how it matched and why it had to be inferred. Tabs are in A-Z order.
* **Depot returns / swaps**: every diagram classed as a **Return** (starts and ends at the same depot, e.g. Lovers Walk to Lovers Walk), a **Swap** (e.g. Lovers Walk to Selhurst), *Leaves depot*, *Back to depot* or *Away from depot*, with a summary per day and a table of depot pairs.
* **Captive units**: units that never start or end a diagram at a depot all week, so they can't get back to one. Per day, it lists the diagrams that neither start nor end at a depot.
* **Fuel check (171s)**: every diesel unit (171/7, 171/8, and any fleet with a diesel power type in the fleet data) followed through the ticked days, checking it is fuelled **at least once every 48 hours**. Each unit shows its fuels, its longest gap between fuels (h:mm, from / to), and *OK*, *Over 48 hours* or *No fuel*; problems are listed first. A fuel's time is the arrival just before the FUEL line in the TRENT print. A unit followed for the whole week is taken to repeat weekly, so the gap from its last fuel to its first fuel the next week counts too; for a unit followed for part of the week, the time before its first fuel and after its last is measured from the start of its first diagram / to the end of its last (*Part week*), so check those across the week boundary. The check always looks across the ticked days, even with *Each ticked day on its own*, and is only as exact as the next-day links (see below).

How units are followed: each diagram's WASH / CET / FUEL lines and start and end locations come from the TRENT print; the **next-day working** of each diagram comes from the note at the end of its unit diagram in the Attune XML (e.g. `BI20 04+29ThO (F)`). For **exact** results the XML must contain the unit diagrams for **every day** you tick. For a day the XML doesn't cover, or a diagram that ends `Stabld`, the unit is matched to a diagram on the same fleet starting where it stabled (same place, then the same depot, then the same station area); those links are shown as `>?` and counted under *Linked by* as *inferred*, and the *Notes* tab says which days were inferred.

**Lovers Walk, Stewarts Lane and Selhurst end a unit's cycle.** Those depots do whatever the units need, so a unit stabling there could form anything the next day: no next-day working is inferred from them, and the unit's cycle ends there (shown as the end of its chain). A next-day working the XML or TRENT print states is still followed.

Which locations are depots: any location named *T&RSMD*, *TMD*, *EMUD*, *Depot*, *Shed* or *Traincare*, grouped by depot (so every road at Selhurst counts as Selhurst), plus the depot list in **Data > Edit depot list**: add a TIPLOC with its depot name, or leave the depot blank to mark a location as not a depot.

**Next-day numbers, berths and limits (3.35.0)**
* Where the XML and TRENT print give no next-day number, a unit is linked to the next day's diagram only if it is the **only** one it could form (same fleet, starting where it stabled, best match first: same place, same depot, same station area); it is marked *inferred* with the reason *next-day number missing*. If more than one could be formed, or another unit could form the same one, the unit is **not followed further**: it is listed on **Next-Day Checks** with the candidates. A unit that stands (berths) all day is followed to the diagram that leaves where it stands, on the days after; if it stands somewhere other than where it arrived (a different siding), or the diagram it forms starts somewhere else, that is flagged there too.
* **CETs by Unit**: *Days in service without a CET (most)* counts only days the unit works a passenger train (class 1, 2 or 9), and the limit is 3 days. **Fuel check**: a gap over 48 hours counts only if the unit moves for two hours or more on two or more days of it (*Days running in the gap*); otherwise it says *Over 48 hours, but mostly stationary*.
* **Possible Washes, CETs, Fuel** (whole-week reports): a stop at a location where the TRENT print does that activity (FUEL: diesel units only), at least as long as the shortest stop where it is done there (20 / 30 / 30 minutes for a WASH / CET / FUEL where that is not known), at which the unit does not do it. Each unit also has a *Could be added at* note. Choose *Every unit*, *Units over a limit only* or *Off* under the unit report options (`--possible every|over|off`). Check that the activity can really be done there before adding it.

### Output formats

Every Stats Pack output (stats packs, comparisons and unit reports) can be saved as **Excel** (the default), **PDF** or **Word**: choose under *Save as* in *4. Output*. PDF and Word use A4 landscape pages with the heading row repeated on each page and the same highlighting; very wide tabs are split into parts. A whole stats pack is long as a document (hundreds of pages per day) - choose *totals only*, fewer days or *Changed rows only* for something shorter. The Stock Tools change report can also be PDF or Word (*Create change report as*); the highlighted CWN itself is always Excel.

### Fleet data

Each fleet's operator, seats, vehicles per unit, fleet size and unit length (for the Fleet tab, the per-vehicle figures and formation lengths) come from a built-in table. Press **Edit fleet data...** to open your own copy (`fleet.csv` in the settings folder) in Excel; changes are used from the next run. New classes and columns from later versions are added to your copy automatically, and blank cells are filled from the built-in table, without changing anything you have entered.

The built-in table has no unit length for **379/0** or **717/0** (they aren't in the TRACS-RS pack it comes from), so their formation lengths show as `?` until you add them in *Edit fleet data*. The **379/0** seats are 20 First Class and 189 Standard Class (fixed seats; its 10 tip-up seats are not counted), with standing room for 136.

### Output files

The pack is written directly as a lightweight `.xlsx` (shared strings, a small set of styles, no formulas), so even a whole week opens quickly in Excel.

### Comparing two timetables (unit and capacity reports)

Tick **Compare two timetables (original and updated XML + TRENT print)** under the unit or capacity report options, and choose the original and updated XML and TRENT print. The report is made for both timetables and saved as one comparison:
* **Comparison Summary**: for each report, how many rows are in both timetables, how many changed, and how many are only in one of them.
* Summary tabs (*Capacity Summary*, *Capacity by Hour*, *Washes and CETs by Fleet*, *Depot Moves by Day*, *Depot Moves by Depot*) list **every figure side by side**: Original, Updated, Change and Change %.
* Detail tabs (*Capacity by Train*, *Washes and CETs by Unit* / *by Diagram*, *Depot Moves by Diagram*, *Captive Diagrams* / *Units*) list **only what changed**, plus rows found in only one timetable (*Only in the original* / *Only in the updated*). Trains are matched by day and headcode; diagrams by day and diagram number.
* Command line: add `--old-xml ORIGINAL.xml --old-trent ORIGINAL.docx` to a `--unit-reports` or `--seats-...` run.

### Capacity report

Choose **Create a capacity report: by headcode group, corridor or station to station** under *Task*, with the Attune XML and the TRENT print. Choose the trains in one of three ways:
* **Service group**: a headcode group such as **1F**, **1W** or **2F** (the first two characters of the headcode). The drop-down lists every passenger headcode group in the chosen XML, with its main routes and number of trains, e.g. *1F   Eastbourne - London Victoria; London Victoria - Ore (73 trains)*.
* **Corridor**: one of our main routes (Brighton Main Line, the London approaches via Balham and via Forest Hill, Crystal Palace, Tulse Hill, Sutton and Mole Valley, Epsom Downs, Caterham, Tattenham Corner, the Oxted lines to Uckfield and East Grinstead, Redhill - Tonbridge, the Arun Valley, West and East Coastway, Portsmouth, Littlehampton, Bognor Regis, Seaford, Marshlink and the West London Line; for TLGN the Thameslink Core, Midland Main Line, East Coast Main Line, Kings Cross - Finsbury Park, Cambridge Line, Fen Line, Hertford Loop, Northern City Line, Thameslink via London Bridge, Wimbledon Loop, Catford Loop to Sevenoaks and London Bridge - Rainham), then **one direction or both** in the box underneath, e.g. *Brighton to Southampton Central*. Every passenger train running along the route counts, whatever its headcode; its direction is the order in which it reaches the route's stations.
* **Station to station**: any two stations on the network (every station in the XML where trains stop; type in a box to narrow the list). Counts the trains that stop at the first station and later at the second. Seats are the **smallest** formation between the two, since that limits the journey.

Then:
* **Whole week** gives one row per ticked day, the week total and the average per day; **Each ticked day on its own** leaves out the week figures. Untick days in *3.* to report only some days.
* **Only trains between** two times (24-hour) **arriving at**, **departing** or **arriving or departing** a station, e.g. *07:00 and 10:00, arriving at London Victoria* for the morning peak. For station to station, the times are the departure from the first station. Without it, the whole day is counted.
* **Show: Seating capacity / Standing room**: tick either or both. Seating capacity is First Class, Standard Class and total seats; standing room is the standing capacity; with both ticked, total capacity (seats + standing) is shown too, and the per-hour tab adds up whichever is chosen. All from the fleet data (*Edit fleet data*), added up over every unit in the formation.
* In a time window the formation at that station is used; otherwise the formation with the most seats while the train is on the route (station to station: the smallest between the stations). Empty stock moves are never counted.
* Output (Excel, PDF or Word): **Capacity Summary** (per day, week total and daily average), **Capacity by Hour** (a column per day), **Capacity by Train** (every train with its times, formation and seats) and **Notes** (exactly which trains were counted, and any stations or fleets that could not be found).

**The corridor list.** The XML and TRENT print don't record corridors, so each corridor is a list of its stations **in route order** (which sets the two directions). Check and correct the built-in list under *Data > Edit corridors* (or the button under the seats options); it opens in Excel, and the drop-downs update once you save it and come back to the app. If you never edited the list from 3.6 - 3.9, it is replaced by the new one (with the TLGN routes) automatically (the old copy is kept as `groups.csv.old`). Each row has:

| Column | Meaning |
|---|---|
| Type | `Corridor` (a `Service group` row with a name such as `Gatwick Express` adds your own service group to the headcode list) |
| Name | As shown in the drop-down |
| Route stations | Stations (names as in Attune, or TIPLOCs) separated by `;`, **in route order**; other spellings of one station can be given with `\|`, e.g. `London Blackfriars\|Blackfriars`. A train is on the corridor if it calls at or passes at least *Minimum route stations* of them |
| Must also call or pass one of | Optional: the train must also call at or pass one of these, e.g. the stations only on this branch, so trains on a shared trunk line are not counted |
| Not via | Optional: trains calling at or passing any of these are left out |
| Fleets | Optional: only trains with one of these fleets in the formation; `-387/2` leaves that fleet out |
| Headcodes (start with) | Optional: e.g. `1W; 1G`; `-2T` leaves those headcodes out |
| Minimum route stations | Usually 2 |

## Timing Tools

Choose the **Task** at the top (the list is grouped: *Timetable checks*, *Train prints and lists*, *Section 4 and Planning Rules*). Under **1. Input** choose its files (or drag and drop them on that section, or anywhere on the tab: the comparison type and the boxes are picked from the files), then press **Compare** (or F5). The **Section 4 check** has its own boxes: the Attune XML, Network Rail's Section 4 PDF(s) and, optionally, VPTs (see [Section 4 check](#section-4-check)). Output can be Excel (default), PDF or Word.

### Check the GTR timetable against the Network Rail timetable

* **Inputs:** the GTR timetable check workbook (sheets such as *OT SNGX TT Checks K - OUT SX*) and the Network Rail timetable workbook (sheets such as *OUT_K_D26_SX_...* with their *_Notes* sheets). If they are chosen the wrong way round the app swaps them and says so.
* **Network Rail is the reference.** Only GTR operators (SN, TL, GX) are compared; other operators (e.g. LO) are counted as out of scope in *Audit Totals*. Only equivalent sections are compared (OUT/RTN x SX/SO/SuO).
* Times are read as HHMM whatever the footnote marks (`0634a`, `06a34`, `a0634`, `05 10`); blank location cells under a station mean the same station; passing / placeholder cells (`.....`, `. .`) are not times; GTR-only extra timings are ignored.
* **Matching** is one-to-one using all the information - times at shared locations (arrival and departure), headcode, calling pattern, start/end and days - never the headcode alone. Confidence 80%+ is a confident match; 50-79.9% is "possible - review" unless the match is unambiguous; below 50% is not a match.
* **Output** (`[NR timetable] Consolidated TT Comparison.xlsx`, e.g. `K_D26 Consolidated TT Comparison.xlsx`) uses the approved template: *Summary* (per section plus an all-sections total), *Issues* (matched trains only: time mismatch, time/location missing, arrival shown instead of departure and vice versa, with whether the rest of the train agrees), *Missing Trains* (whole NR trains missing from GTR, and isolated GTR gaps in an otherwise matched regular pattern), *Headcode Mismatches* (same timings, different headcode), *Service Group Review* (groups such as `9Rxx` when 5 or more trains, otherwise individual headcodes), *Match Audit* (every NR train, its match, confidence and status) and *Audit Totals* (NR timing cells in scope = compared + not compared; never "Complete" while any cell is not compared). Empty sheets say *None identified*.

### Check a timetable against train prints or an Attune train list

* **Half minutes**: a timetable that shows half minutes (`0634½`, `0634H` or 30 seconds in an Excel time) is a working timetable, so prints and lists are compared with it **to the half minute** using their working times (passing times included). Times are rounded to whole minutes **only** when one side is a public timetable (Network Rail / passenger) without half minutes: then the half-minute side is rounded the public way (departures down, arrivals up), and the *Notes* say so.
* **Check a timetable against train prints**: the reference is one or more Attune **Single Train Report** prints (PDF or Word). Each train's **public** arrival and departure times are checked against the timetable (GTR or Network Rail layout), using exactly the same matching rules, confidence levels and output as timetable against timetable. Passing points, working-only stops (signals, sidings) and empty-stock trains have no public times and are not compared (they are listed in *Audit Totals*). Only times the timetable has a row for are checked, so a table that shows one time at a station is not reported as missing the other.
* **Check a timetable against an Attune train list**: the reference is an Attune train list (heading row found automatically; columns such as *TrainID / SignalID, Days Pattern, Origin Loc, Origin Time, Destination Loc, Destination Time*). A list only has each train's origin departure and destination arrival, so only those two times are checked - use train prints to check every stop. Working half minutes become public times (departures round down, arrivals round up). Empty-stock and other non-passenger trains (headcode class 0, 3-8, or an Attune category starting with E) are left out. Location codes (TIPLOCs) are turned into station names from a built-in list plus every code seen in train prints read on your PC.
* Each train goes into the section(s) its days run in (SX / SO / SuO), in the direction (OUT / RTN) where the timetable has it (or whose table lists its stations in calling order). If the timetable clearly shows a train in another section - for example an after-midnight train on the next day's sheet, with the same headcode and times - it is compared there rather than reported missing, and a note says so.
* Output: `[reference] vs [timetable] Consolidated TT Comparison.xlsx`, with the headings naming the sides (e.g. *Print headcode* / *GTR headcode*).

### Compare two sets of train prints (PDF or Word) or Attune VPT exports

* **VPT exports** (`.vpt`, Attune's *Voyager plan train export*) can be used on either side, in any mix: **VPT against VPT**, **VPT against Attune *Single Train Report* prints** and **prints against a VPT**. A VPT is a plain text file, so it is read in about a second and exactly (no page layout to read): each train's ID, first and last dates, days run, and every location with its working times (arrival, departure or passing), platform, line and allowances. VPT against VPT compares all of that. Against a print, which lays out lines, dwells and allowances in its own way and has public times and activities that a VPT does not, only the **calls, working times, platforms, days run, train ID and dates** are compared (the report says so). *Passenger times only* against a print leaves out the stops that only the VPT has. The XML is still used wherever unit diagrams are needed (stats packs, unit reports, berthing charts, station books) and for the Section 4 check, which needs the remarks, RAR and MAINT diagrams that are in the XML only.
* Choose one or more files for each side (hold Ctrl in the file window). Each train is found by its heading line (headcode with a UID, or the word *Train* / *Headcode*); a heading repeated on the next page continues the same train. Page numbers, print dates and repeated column headings are ignored.
* Attune *Single Train Report* prints are read column by column (working, passing and public times, dwell, activity, platform, line, allowances and every heading field such as *Days Pattern* or *Timing Load*), so a change is named exactly, e.g. *Public departure time changed* or *Platform changed*. Other print layouts are read from their text.
* Trains are paired by headcode, UID and days (then train ID and days, headcode, days and first time), and compared location by location, so an added or removed call is reported once instead of shifting every line. Reported: trains added / removed, arrival / departure / passing times changed, added or removed, other call details (platform, line, path, activities) and heading details.
* **Passenger times only** (tickbox; command line `--passenger-only`): passing times and calls without a public time (timing points, working-only stops) are left out, for prints where one side does not show the intermediate timing points. The report's *Notes* say so.
* **Side by side, like the timetable comparison**: in the *Live View* and on the report's **Side by Side** sheet, each train is laid out a row per location and time (*Arr* / *Dep* / *Pass*) with both prints' times next to each other, then the print's own details for that call: public times, platform, line, activity codes, dwell and allowances (a value that differs shows as `old → new`). The train's **days run**, train ID, UID, dates, class, power type, timing load and other heading details are at the top. The report's sheet lists every train that changed, was added or was removed.
* **Speed**: Attune *Single Train Report* PDFs are read with PDFium, about ten times quicker than before (thousands of trains in well under a minute), with big files spread over several CPU cores. PDFium places every value by its position on the page, so narrow columns such as the allowances are read exactly; other PDFs are read as before. Scanned (image-only) PDFs cannot be read - save the print from the planning system as PDF or Word.

### Compare two Attune train list exports (Excel or CSV)

* The heading row is found automatically (extra title rows and column order don't matter). Trains are paired by UID, days, STP and start date when there is a UID column, otherwise by headcode, days and origin departure time. Without a UID, a retimed train is still paired (and its new time reported as a change) when it is the only train left on each side with its headcode, days and origin; where two or more are left, they are listed as added and removed rather than guessed. An LTP row and its STP twin with the same key keep to their own stage.
* Every column present in both lists is compared; times compare as HHMM (`05:10`, `0510` and an Excel time are equal) and numbers as numbers. Output: *Summary*, *Changes by Train*, *Trains Added*, *Trains Removed* and *What Was Compared* (which columns were compared and how trains were paired).

### Compare two sets of Section 4 documents (PDF)

* Choose the original and the updated Network Rail **Section 4** PDFs (several on each side for several routes). Each possession row is paired by **section number, night and what is blocked** (a section often has several possessions for a night, one for each line blocked, so the number and night alone repeat; a row whose blocked line was edited is still paired by its windows) and compared: the **section and its end locations**, the **periods and their dates**, the **possession windows** (times and days), **what is blocked**, and the **remarks**.
* **Notes are compared too**: each route's **NOTES** and **Timetable Construction Notes**, and other text outside the possession tables (such as the track patrolling plans), route by route and sentence by sentence, so an edited note shows as changed rather than as one removed and one added. Notes are read from the PDFs; a rule set saved in the app holds the possession rows only, so a comparison from saved rule sets does not include notes (the report says so).
* **Header details are not compared.** The running header and footer (version, date, page numbers, next issue date) are found by repetition and shown on *What Was Compared* for information, e.g. *Version 4.0; Date 10th July 2026*, so you can see which issues were compared.
* **Comparing two different issues** (or years): the dates always move, so possession dates are **not** compared, and dates in remarks and notes are ignored. Remarks and notes only count as changed when their **content** changed: capital letters, punctuation, spacing, abbreviations (*Jn* / *Junction*) and spelling slips do not. Times, numbers, line names and any other word still do. The same applies to the TPR comparison.
* Output: *Summary*, *Changes* (each changed item, what changed, original and updated), *Added*, *Removed* and *What Was Compared*. The **Book** column, left of *Where*, says which region the item is from (taken from the file name, e.g. `2027 EAS V4 S4 - EC.pdf` is *EC*). Tick **Also save the PDFs with the changes highlighted** to save a copy of the updated PDFs (changes yellow, additions green) and of the original PDFs (removals red), each highlight with a note saying what changed. Command line: `timetable --s4 OLD.pdf [...] --vs-s4 NEW.pdf [...] [--highlight-pdfs]`.

### Compare two sets of Timetable Planning Rules (PDF)

* Choose the original and the updated **TPR** PDFs (route TPRs, e.g. *TPR 2027 V4 EM.pdf*). **Every table** is read from its drawn grid (line-of-route tables, headways, junction margins and station planning rules, standages...) - a table carried on to the next page stays one table - and every **paragraph and note** between them.
* **Left out, and listed on *What Was Compared*:** Network Rail's **covering commentary** (the summary of changes at the front, before the rules start), the **contents pages**, the **running header and footer** (found by repetition on every page, whatever the page size; the version and date are shown for information), and any wording the issue **deleted** (green and struck through), so each document is compared as its final text. The thin change bars in the margin are not table lines.
* Sections are read from the numbered headings (e.g. *5 Running Times, Margins and Allowances > 5.3 Junction Margins and Station Planning Rules*), and a line-of-route title such as *LN3340 ALREWAS (INCLUSIVE) TO WICHNOR JN* names its table. Tables are paired by section and title (section numbers left out, so a renumbered section still pairs). **Rows are paired by lining the two versions of a table up**, not by their first column (which repeats a lot - platforms, movements - in the real tables): an inserted, deleted or edited row never shifts the others, and a row whose first cell is edited a little is still paired. Each cell is compared under its column heading; paragraphs are compared section by section, sentence by sentence.
* Tested on the six 2027 V4 route TPRs (AR, EM, KT, LNE, SX, WX) and five Section 4 PDFs: each compared with itself shows no differences, and known edits (a changed cell, an inserted row, a deleted row, an edited note) are each reported exactly once. The 399-page LNE TPR compares in under 10 seconds.
* Output as for Section 4 (including the *Book* column and the highlighted PDFs). Command line: `timetable --tpr OLD.pdf [...] --vs-tpr NEW.pdf [...] [--highlight-pdfs]`.

### Section 4 check

* **Inputs:** the Attune XML of the timetable, and Network Rail's Engineering Access Statement **Section 4 (Standard Possession Opportunities)** PDFs for the routes it runs on (e.g. *2027 EAS V4 S4 - KS*, *- EC*, *- EMR*). Add several PDFs to the box, or drop them with the XML on the Input section. Or leave the PDF box blank to check the **rule set in use**: the app has the **2027 EAS v4** Section 4 rules for Kent & Sussex, Anglia, East Coast, East Midlands and Wessex built in (13/12/2026 to 11/12/2027), so nothing needs adding. When Network Rail publishes newer Section 4 PDFs, add them once as a rule set in *Data > Rules and reference data*; that set is then used instead (the built-in set can be chosen again there). The latest rules are on [Network Rail's operational rules page](https://www.networkrail.co.uk/industry-and-commercial/information-for-operators/operational-rules/).
* The PDFs' tables are read from their drawn cells: each section (e.g. *Shepherds Lane Jn and Herne Hill 110.3*), each night (*WEEK END*, *SUN/MON*, *MID WEEK*), each period's windows (e.g. *0140 T-F to 0350 T-F* is 01:40-03:50 on Tuesday to Friday mornings) and what is blocked.
* A train **clashes** when it calls at or passes both ends of a section at a time inside a window, on a day and in a period the possession applies to (only periods the XML's dates cover). Places are matched to the XML by name (Network Rail's and Attune's spellings, e.g. *Victoria Eastern* / *London Victoria*); sections whose places are not in the XML are listed under *Places Not Checked*.
* **Remarks are checked for each train.** The REMARKS column can except some trains or limit the possession, so it is applied to each clash:
  * **excepted train types** (e.g. *Except ECS*, *Not applicable to passenger trains*, *Freight only*), from the train's class (1, 2, 9 passenger; 0, 3, 5 empty; 4, 6, 7, 8 freight);
  * **named trains** (*1A23 excepted*, *Possession to be given up for the passage of 1A09*, *6D10 to be permitted to pass*, *after passage of 5E10*);
  * **depot access** (*Access to Selhurst Depot via Norwood Jn*): the train's routing and destination are checked - it must run to or from that depot and pass the route named;
  * **dates and weeks** (*Not 24/12*, *Only 01/06 to 30/06*, *Weeks 12-20*), **lines left open** (*Fast lines open*, *Trains to be timed over the Slow lines*), **routes to be kept** and **other possessions** (*Not when ... is taken*).
  
  A clash the remarks lift goes on the **Exempt** sheet with the reason; a remark that needs checking by hand (weeks, another possession, wording the app does not recognise) keeps the clash, shaded, and says what to check (*Remarks for this train*).
* **Trains not checked** (listed on *Trains Not Checked*): trains that **run as required** (the XML's runs-as-required marking) unless they are passenger trains, and every train worked by a **MAINT** diagram.
* **VPTs (optional): running lines and other operators.** Add a **VPT of the same timetable** (*GTR VPT*) and a clash where only some lines are blocked is settled by the **line each train runs on** through the section, which the XML does not have. Each XML train is matched to its VPT train by train ID, day and the time at the section's first end. A train on a blocked line stands as an *Every line blocked* clash; a train on a line that is not blocked (e.g. the Slow line when only the Fast lines are blocked, or the Up line when only the Down is) goes to **Exempt** with the reason; where the line is not known the clash stays *Some lines: check the line used*. The line is shown in the **Line used (VPT)** column. A line code gives its direction from the first letter (D Down, U Up) and its kind from the last letters: F Fast, S Slow, M / ML Main, R Relief, L Local, Q Quarry (e.g. `SL`, `FL`, `DBF`, `UBS`, `UML`, `QL`); anything else is unknown. **Other operators** add their trains to the check (all are checked: a VPT does not say RAR or MAINT) with an **Operator** column: a **VPT** is preferred, and an Attune **Single Train Report (F3) print** (PDF or Word) also works - its *Line* column gives the running lines and each train keeps the operator the print names. Command line: `--vpt OURS.vpt`, `--other-vpt A.vpt [B.pdf ...]` (or `--other`). Drop `.vpt` files on the Section 4 check: the first goes to *Our VPT*, the rest to the other operators' box.
* **Command line:** the `section4` subcommand runs the same check (with no `--pdf`, the Section 4 rule set in use):

  ```
  TrainPlanningTools.exe section4 --xml "DEC26 LTP.xml" --pdf "2027 EAS V4 S4 - KS.pdf" "2027 EAS V4 S4 - EC.pdf"
                         --vpt "DEC26 LTP.vpt" --other-vpt "XC DEC26.vpt" --out "C:\Planning\Checks" --name "S4 check DEC26"
                         --format xlsx
  ```

  This saves *S4 check DEC26.xlsx* in that folder and prints a summary (trains in a possession window, clashes, how many the remarks lifted, trains not checked). `--format` takes `xlsx` (default), `pdf` or `docx`; `--out` must be a folder on this PC (default Downloads); `--name` defaults to a name taken from the XML. Missing files, a `--pdf` that is not a PDF and a `--vpt` / `--other-vpt` that is not an Attune VPT are reported straight away (exit code 2) before any file is read; a file that cannot be read stops the run with `ERROR:` (exit code 1). The older form `timetable --s4-check PLAN.xml [--s4 SECTION4.pdf ...] [--vpt OURS.vpt] [--other-vpt OTHER.vpt ...]` still works.
* Without a VPT, the XML has no running lines, so each clash says **Every line blocked** or **Some lines: check the line used**. Where only the Down (or Up) line is blocked, a train is taken as Down when it reaches the first-named place first, and trains the other way are left out. Midweek possessions available only some weeks show it (e.g. *8 weeks a year*).

## Saved settings, notifications and help

* **Save/Load** menu (Alt+S): *Save ... settings as...* stores the current tab's files and options under a name, e.g. *DEC26 Brighton CWN* or *AM peak seats*. Each tab keeps its own list, with as many saved settings as you like. The settings saved for the tab you are on are listed straight under it (click one to load it). Every tab also has a sub-menu listing its saved settings, where each one can be **loaded**, **loaded and run**, **replaced with the current settings**, **renamed** or **deleted** (the files themselves are never touched). If a file has been moved or deleted, the settings are loaded but not run, and the missing files are listed. Settings saved by earlier versions are kept.
* **Notification when a run finishes**: if the app is in the background when a run ends (e.g. you are working in Excel), its taskbar button flashes and a small notice appears in the bottom-right corner of the screen. Click the notice to bring the app to the front. Switch this off in *Options > Notify me when a run finishes in the background*.
* **Stopping a run**: press **Stop** beside the progress bar (or **Esc**) to stop a long run at its next step. Nothing is saved from a stopped run.
* **Help on every control**: rest the mouse on any option, button or box for a short explanation.
* **Help > Error log...**: the log of unexpected errors, to send with a support request. It opens as a preview with **file paths**, your **user and computer names** (and any email address) and **text quoted from your files** hidden; untick any of these to show it. Only what the preview shows is copied (**Copy**) or saved (**Export...**, as *error log YYYY-MM-DD.txt* on this PC, never over an existing file). **Clear log** empties it. The log only ever holds error details, never the contents of your XML, workbook or PDF files: a line long enough to be file contents is cut short when it is written.
* **File size limits**: to stop a damaged or hostile file filling the PC's memory, the app refuses files far larger than any real one: an Attune XML over 4 GB, a VPT over 1 GB, a PDF over 500 MB or 20,000 pages, an Office file that unpacks to over 2 GB (or 512 MB in one part). XML with a document type declaration (`<!DOCTYPE` / `<!ENTITY`, never in Attune or Office files) is refused too, so it cannot expand or pull in other files. If a genuine file is ever refused, raise its limit in **limits.json** in the data folder, e.g. `{"XML_MAX_BYTES": 8589934592}`: the names are `XML_MAX_BYTES`, `XML_PART_MAX_BYTES`, `VPT_MAX_BYTES`, `PDF_MAX_BYTES`, `PDF_MAX_PAGES`, `XLS_MAX_BYTES`, `CSV_MAX_BYTES`, `ZIP_PART_LIMIT`, `ZIP_TOTAL_LIMIT`, `ZIP_RATIO_LIMIT`, `ZIP_RATIO_FROM`, `META_MAX_BYTES` (the comparison data kept inside a comparison CWN), `SETTINGS_CSV_MAX_BYTES` (fleet, depot, corridor and berth lists) and `PROGRESS_MAX_BYTES` (Live View progress files) (whole numbers; anything else is ignored).

## Live View

The **Live View** tab shows any comparison in the app inside the window: CWNs, stats pack plans or files, GTR vs Network Rail timetables, train prints or an Attune list against a timetable, two sets of train prints or Attune lists, **two sets of Section 4 documents or TPRs**, the **Section 4 check** (watching the XML as you correct it), **two berthing charts** and the **unit reports of two plans**.

1. Choose what to compare and the files (or drag them onto the tab), then press **Compare** (F5).
2. Every train (or stats row) is listed on the left. *Show* filters it (differences only, all, changed, issues, added, removed / missing, unchanged, or updated by the last refresh) and *Find* searches it.
3. Click a train to see it side by side with its match on the right, with differences coloured (yellow changed, green added, red removed / missing, orange issue, grey not compared) and described underneath. **Next >** / **< Previous** (F3 / Shift+F3) step through the trains with differences.
   * **Click a row** on the right to highlight it right across, original and updated side by side, with its full values (including any too long for the column) shown in the box underneath.
   * Train prints: the train's header details (days run, IDs, dates, class, power type...) sit under a **Train Header Details** heading at the top, folded away at first. Click it (or press Enter on it) to show them or fold them again; the app remembers your choice. Folded, the heading still turns yellow and says how many details differ.
   * The **Status** names the broad kind of change: *Timing*, *TID* (train ID), *UID*, *Days run*, *Header*, *Calling points*, *Platform/line*, *Activity*... e.g. *Timing, TID change*; the notes underneath give the detail.
4. With **Refresh when a file is saved** ticked, the files are watched. Save either one (e.g. after correcting a time in Excel) and the comparison re-runs, usually within a second or two. Only the saved file is read again. The selected train stays selected, and trains changed by the save are marked `*` in bold, with *Show: Updated by the last refresh* listing just those.

5. **Passenger times only** (CWNs, timetables and train prints): hides passing times and times shown in one file only, for comparing timetables where one does not show the intermediate timing points. **Check header differences** and **Check timing differences** (timetables and train prints, both on) can be unticked to ignore one kind: those differences are shown in grey and do not make a train count as changed.
6. **Confirm each train as you check it**: click the ✔ column (or press Space, or **✔ Confirm**). *Show: Not yet confirmed / Confirmed* lists what is left, and the count under the list shows your progress. Ticks are **saved automatically** for each pair of files and come back when the same files are compared again; **Save progress...** / **Load progress...** keep them in a file of your own (e.g. to carry on tomorrow or hand over), with the files and options. If a refresh changes a train after it was confirmed, its tick comes off and it is listed under *Changed since confirmed* (marked !).

7. **Two berthing charts**: each berth with a difference is listed (under its sheet and siding location), and its cells are shown side by side, *Column / Older chart / Newer chart*: a changed unit or time in yellow, a unit only in the newer chart in green, one only in the older chart in red, and the berth's unchanged cells between them in column order so each change is seen in context. Berths with no difference are not listed. It uses the same comparison as *Compare two berthing charts*.
8. **Section 4 check**: the trains are listed under *Clashes*, *Exempt* and *Not checked*; each shows its section, period and night, possession window, times at each end, what is blocked, the line used (with a VPT), the operator (other operators' trains) and the remarks. With *Refresh when a file is saved* the check re-runs as you correct the XML.
9. **Pop out** (Ctrl+Shift+P) puts **only the results** (the train list and the details) in **their own window**, to put them on another monitor or beside your work. The task, the files and the options stay in the main window: choose them and press **Compare** (F5) there and the window shows the comparison. The selected train, the ticks and a refresh in progress all carry on. In that window **Full screen** (F11; Esc leaves it) and **Always on top** are offered, and F5 compares again. **Bring back** (or closing the window) puts the results back in the tab. The window's size and place are remembered; if that place is no longer on a screen (a monitor was unplugged), it opens on the main screen.
10. **Display options** (above the results, in the tab and in the window; remembered):
    * **Layout**: *Side by side* (the list beside the details) or *Stacked* (the list above the details, for tall or narrow windows).
    * **Changed rows only**: the details show only the rows that differ.
    * **Text A- / A+**: the list and details are made smaller or bigger, whatever the rest of the window is set to. In a window on a display with other scaling the text follows that display.
    * **Hide train list**: the details only, full width; **< Previous** / **Next >** in the toolbar move through the trains.

**Export...** saves the trains currently listed (with the filter and search applied) to Excel, PDF or Word: a *What Was Compared* sheet, a *Trains Listed* sheet (each train's result and differences in words) and a *Differences in Detail* sheet (each differing call or field, coloured as on screen).

The Live View uses exactly the same reading and matching as the other tabs, so it always agrees with their reports. For CWNs it has the same day tickboxes as the Stock Tools tab. It only reads the files; nothing is written.

## Licence

Train Planning Tools is free software under the [GNU General Public License v3.0](LICENSE): you may use, share and change it under the terms of that licence. It comes with no warranty; always check its results before relying on them.

## Third-party software

Train Planning Tools is built with open-source software (Python, Tcl/Tk, openpyxl, xlrd, pyxlsb, tkinterdnd2, ReportLab, pypdf, pypdfium2 / PDFium, Pillow and PyInstaller), each used under its own licence. The list and licences are under **Help > Third-party software and licences**, and in [`rstools/assets/THIRD_PARTY_NOTICES.txt`](rstools/assets/THIRD_PARTY_NOTICES.txt).

## Version history

**3.38.0** - other operators from F3 prints, SNGX station books, recent files by name, berthing notes per timetable

* **Station Working Book: TLGN, SNGX or All GTR.** The *Operator* box chooses whose trains the book has (by the depot of the unit diagrams working each train) and its header, file name and sheet names; the SNGX book is new. *Other operators shown* ticks which of the other operators in the added files are shown. Command line: `--book-operator`, `--other-operators`.
* **F3 prints for other operators**: an Attune Single Train Report (F3) print, PDF or Word, can now be added for other operators in the Station Working Book and the Section 4 check (and Live View), next to XMLs and VPTs. Boxes that take several kinds of file say which is preferred, and the file dialogs list it first.
* **Recent files by name**: recent-file lists show the file name (*Options > Show full paths in recent files* for the whole path); files that have been moved, renamed or deleted are shown in red with that note.
* **Tips stay off drop-down lists**: no help tip opens while a recent-files list or drop-down is open.
* **Berthing chart notes per timetable**: *Data > Berthing chart notes...* changes, adds or removes each location's notes for the current and next five timetables; *Show location notes on the chart* (on by default, `--no-notes` to turn off) on the main screen.

**3.37.0** - the window checked through: clearer wording, the same layout on every tab, quicker to use
* **Same layout on every tab**: Run, a progress bar and Stop on one row with the status underneath (the Live View's Stop button was hidden under its progress bar), **Tab** moves through the boxes in the order they are shown, and day boxes have *All / Weekdays / Weekend / None* on every tab.
* **Clearer wording**: every task in the task lists starts with what it does (*Compare...*, *Check...*, *Create...*) and its run button says the same; counts read properly (*1 train*, *2 trains*); messages say what to do next; message boxes open over the app window; tab names in the change report of platform workings are shown without their trailing space.
* **Menus**: a new **Data** menu holds the fleet data, depot list, corridors, rules and settings folder; updates and the access token are under **Help**; *Save/Load* lists each tab's settings once; **Ctrl+Tab** switches tabs; the keyboard shortcuts list is complete.
* **Help tips** show for the task chosen in each task list, and tips that had stopped showing after controls were renamed are back.
* **Live View**: choosing the same task again keeps the results; option changes made during a refresh are no longer lost; a list of thousands of trains fills without freezing the window; the saved-file check and the automatic save of confirmations no longer hold up the window; *Confirm* reads *Unconfirm* for a train already confirmed; the colour key matches the theme in use; the second pair of *Previous / Next* buttons is gone.
* **Quicker to use**: typing in a file box no longer waits on the recent-files list (whose suggestions are now only files of the box's type) or re-reads files on every key; background reads show their results at once; the window opens a little faster.
* **Logs**: warnings and errors are coloured on every tab, the log shows a hint while empty and its scroll bar only when needed.
* **Smaller fixes**: the Stats Pack name hint gave the wrong save folder; the corridor list is read again when you come back from Excel; Stock Tools notifications name the task that failed; Timing Tools refuses an output folder that does not exist (as the other tabs do) and remembers *Also save the PDFs with the changes highlighted*; a mileage figure that is not a number is queried; icons follow buttons whose text changes; Clear buttons for the TRENT print boxes.

**3.36.1** - every process run and its outputs checked: fixes
* **PDF and Word outputs** no longer start every table on a new page: short tables share a page, and a new page starts only when the next heading and its first rows would not fit (a change report goes from 7 pages to 2, a stats pack from about 100 to about 20). A wide table with nothing in it (*None identified*) is no longer split into parts.
* **Platform workings change reports** list the day tabs Monday first in every sheet, without the trailing space of the tab names.
* **Left-out change types**: when categories are switched off (or `--exclude` is used), the count of changes found now matches the report and says how many were left out.
* **Command line**: a VPT given to check a timetable is refused with the reason (it has no public times); the `--exclude` help example is a real category; `workings-berthing` reports the saved file once.

**3.36.0** - review: safety, stability, clean-up, faster Live View, tidier outputs, Stop button
* **Stop button** (and **Esc**) on every tab: a long run stops at its next step, and nothing half-written is saved.
* **Stats Pack outputs**: times and durations are now **real Excel times** (they look the same, but sort and add up; a negative difference stays as text). Every tab has frozen headings and a filter (totals stay at the bottom), and prints **landscape**, one page wide, with the headings on every page. Packs from earlier versions are still read when comparing.
* **CWN change report** in the same look as the other reports (heading colour, landscape, headings repeated on each printed page, no gridlines, a filter on *New and Cancelled Trains*).
* **Clearer names**: the Live View export's first sheet is *What Was Compared*; the Section 4 check has *Trains Not Checked* and *Places Not Checked*.
* **Live View**: remembers its last task and folder, **Ctrl+F** goes to Find, the export starts in your output folder (and, like every other output, is never saved on a network drive), the days of two CWNs come from the files already read rather than reading them again, berthing-arrangement lines only in the original are shown as removed, and an empty results pane says what to do.
* **Timing Tools** progress moves on as each file is read.
* **Clearer messages** for a workbook open in Excel, an old .xls given to Timing Tools, or a damaged file; CSV train lists saved by Excel in either encoding (CSV or CSV UTF-8) read correctly.
* **Safety**: text in .xls / .xlsb CWNs that starts with "=" stays text in the outputs; the hidden comparison data has a size limit; temporary and probe files always get new random names (an existing file is never touched); settings copies are written whole or not at all; settings lists and Live View progress files have size limits; update downloads go to a new temporary file, are size-capped, never overwrite an earlier download in Downloads, and a signed download whose signature Windows rejects is refused; the update dialog keeps working if a step fails.
* **Stability**: one thread-safe store of files already read; Windows display calls declare 64-bit handles (part of the display-move fix); Section 4 and TPR PDFs are read in a helper process, so a damaged PDF cannot close the app; closing during a Live View comparison asks first; half-finished update downloads are removed on the next start; a saved window place is enlarged to fit if the text size grew.
* **Platform workings berthing**: a section longer than the old one never overwrites what follows it, siding roads are found whatever sub-class the workings show, and an unreadable file gives a message rather than a traceback.
* **Command line**: option combinations that would be ignored are refused up front (see [Command line](#command-line-optional)); the `berthing` command and the `--capacity-*`, `--no-seating` and `--no-standing` options are documented.
* **Under the hood**: shared modules for the Attune XML readers, days, clock times, saving and output names; unused code and parameters removed; packages updated (reportlab 5.1.2, pypdf 7.2.0, charset-normalizer 3.5.3, packaging 26.4); more smoke tests of the exe; the coverage floor raised to 75%.

**3.35.0** - unit report rules, Live View output-only pop-out, moving between displays
* **Unit reports**: where there is no next-day number, a unit is followed only if it could form just one diagram (marked *inferred*, "next-day number missing"). If it could form more than one, or the same one as another unit, it is not followed further and is listed on the new **Next-Day Checks** tab. A unit that berths for a whole day is followed to the diagram that leaves where it stands, and a berth in a different place from where the unit arrived or leaves for is flagged.
* **CET**: a unit should not go more than 3 days in passenger service without a CET (days it stands, stables or only works empty trains do not count). **Fuel (171s)**: a gap over 48 hours is a problem only if the unit really runs on two or more days of it, else it says *mostly stationary*.
* **Possible extra WASH / CET / FUEL**: a *Could be added at* note on each unit and a new **Possible Washes, CETs, Fuel** tab list the stops at a location where the TRENT print does that activity, long enough (at least the shortest stop where it is done there), where the unit does not. Option on the unit reports: every unit (default), units over a limit only, or off; command line `--possible every|over|off`.
* **Live View pop-out** now holds only the results; the task, files and options stay in the main window. New display options: layout (side by side / stacked), changed rows only, text size and hiding the train list.
* **Moving between displays**: the window is rescaled for the display its centre is on, once, and left alone for a moment afterwards (no more repeated rescaling or a black area behind the window); painting is held on the contents only; and a failure while rescaling is logged and leaves the window as it was.

**3.34.0** - platform workings: compare, colours, rounds and automatic berthing arrangements
* **Platform workings** (Victoria, London Bridge, Brighton) can be compared, put in colours and added to by rounds in the CWN tasks, as single files or folders. Line, number of cars and operator changes are reported, and so are the lines of each day's berthing arrangements. Supplement numbers are ignored when folders are paired, and *Days to check* picks day tabs.
* **Add berthing arrangements to platform workings** (new task, and `workings-berthing` on the command line): makes each day's *Berthing Arrangements* from the trains in the workings, checks the next day's tab, and follows units in the sidings from arrival to the train that takes them out. The siding road can come from an Attune XML. A hand-made section is replaced and the differences are logged.
* Merged cells below the trains (the berthing section at Victoria) now move with their rows when a comparison inserts rows.

**3.33.1** - fixes from the 3.33.0 review
* **Stats Pack**: the *Task* box is no longer blank when the app starts, and the frames are numbered 1, 2, 3... with no gap when *Options* is hidden.
* **Command line**: a mistyped command (e.g. `statpack`) now says it is an unknown command and lists the real ones (exit code 2) instead of asking for `--updated`; `--help` lists the commands; `selftest --help` shows its usage.
* **Settings** are still saved when the Live View window's place cannot be.
* **File limits** now also cover older Excel `.xls` workbooks (`XLS_MAX_BYTES`) and train list `.csv` files (`CSV_MAX_BYTES`), raisable in `limits.json` like the others.
* **Release build**: builds of `main` now run one after another, so two close pushes cannot publish the same version at the same time.
* More tests: reading `.xls` and `.xlsb` CWNs, the update and rules dialogs, the new command-line messages.

**3.33.0** - `section4` command, Live View berthing cells and pop-out window, file limits, private error log, release SBOM
* **`section4` command**: `TrainPlanningTools.exe section4 --xml PLAN.xml [--pdf S4.pdf ...] [--vpt OURS.vpt] [--other-vpt OTHER.vpt ...] [--out] [--name] [--format]` runs the Section 4 check (the same as `timetable --s4-check`, which still works). Bad flags and files are reported before anything is read.
* **Live View, two berthing charts**: each changed berth now shows its cells side by side (changed, added and removed cells coloured, unchanged cells between them).
* **Live View in its own window**: *Pop out* (Ctrl+Shift+P) moves it to a window of its own (another monitor, full screen with F11, always on top), keeping everything in it; *Bring back* returns it. The window's place is remembered.
* **File limits and XML guards**: files far larger than any real one, and XML with a DOCTYPE / ENTITY declaration, are refused in plain words; truncated XML and bad characters are reported by every reader. The limits are kept in one place and can be raised in `limits.json`.
* **Help > Error log...**: preview the log with file paths, user / computer names and quoted file text hidden (each can be shown), then copy or export it. File contents are never kept in the log.
* A Live View comparison of two berthing charts that you ticked as confirmed in 3.32 or earlier shows its berths as *Changed since confirmed* once (the rows now list each cell), so tick them again.
* **Releases** now carry a CycloneDX SBOM (`TrainPlanningTools.cdx.json`), `SHA256SUMS.txt` and, where supported, a build provenance attestation. CI runs lint, type-check, tests with coverage and a dependency audit as separate jobs before the build, and CodeQL code scanning.

**3.32.0** - VPTs in the Section 4 check and station book, clearer task lists
* **Section 4 check**: add a **VPT of the same timetable** and clashes where only some lines are blocked are settled by the line each train runs on (blocked line: stands; open line: *Exempt*; unknown: *check the line used*), with a *Line used (VPT)* column. **Other operators' VPTs** add their trains to the check (*Operator* column). Also in Live View and `--vpt` / `--other-vpt`.
* **Station Working Book**: the *Other operators* box takes **VPT** exports as well as XMLs (`--merge`, `--merge-xml` still works).
* **Where a VPT is better than the XML:** only the Section 4 check's running lines. The unit reports, stats packs, berthing charts and station books need the XML's unit diagrams, and the Section 4 check's remarks, RAR and MAINT also come from the XML, so the XML stays the input for those.
* **Task lists are grouped**, each group in the order the work goes: *Stock Tools* (CWNs, Berthing charts, Station books), *Stats Pack* (Stats packs, Reports), *Timing Tools* (Timetable checks, Train prints and lists, Section 4 and Planning Rules) and the same groups in Live View (where *Compare* is now *Task*). Choosing a group heading picks its first task.
* **Input**: the files of every task are in one section called **Input** (replacing *CWN Comparison*, *Timetable Comparison*, *Utilities*, *Files* and *Berthing Charts*). Stats Pack has its report options in *2. Options*. The big page titles are gone (the tab already names the page).
* **Order**: *Changes to Include* is grouped (whole trains; timing and route; stock and workings; notes), A-Z within each group; Live View's *Show* list is grouped by result, then by checking progress; the unit report ticks go Washes, CETs, Fuel, then Depot returns / swaps and Captive units.

**3.31.0** - Attune VPT exports
* **Train print comparison and Live View** accept Attune **VPT** exports: VPT against VPT, VPT against Attune train prints, and prints against a VPT. Drop `.vpt` files on the Timing Tools tab to start a comparison; command line `timetable --prints OLD.vpt --vs NEW.vpt`. See [Two sets of train prints](#compare-two-sets-of-train-prints-pdf-or-word-or-attune-vpt-exports).

**3.30.0** - Section 4 / TPR clean-up, wash and CET reports, Live View checks
* **Fix**: "Invalid character found in sheet title". Tab names are now cleaned (no `\ / ? * [ ] :`), kept to 31 characters and never repeated, in every workbook the app writes.
* **Section 4 and TPR comparisons**: dates are no longer compared, and remarks and notes only count as changed when their content changes (not capitals, punctuation, spacing, abbreviations or spelling slips). A new **Book** column, left of *Where*, gives the region. New **Also save the PDFs with the changes highlighted** option (`--highlight-pdfs`).
* **Unit reports**: washes and CETs are separate reports; inferred links say where and why (*Inferred Links* tab); *Show each day separately* now also splits *by fleet* per day; *Entire timetable* gives the fleet totals only; units that go more than 3 days without a wash are flagged; tidier tabs (frozen headings, filters, wrapped long columns, A-Z order). `--unit-period week|days|timetable`; `washes` no longer includes CETs on the command line (add `cets`).
* **Live View**: *Check header differences* and *Check timing differences*; *Train details* is now **Train Header Details** (folded by default, no longer clipped); the Status names the kind of change (*Timing, TID change*).
* **Layout**: the Task, Compare and Show lists, and the change categories, are in A-Z order; section headings use Title Case.

**3.29.0** - location headers and a layout that fits the screen
* **Berthing chart**: on a sheet with several siding locations (for example Brighton: Platforms / Brighton Wall Siding) each location now starts with a banner row, *Location - <name>*. Charts made earlier (without banners) still open, add rounds and compare as before. Live View names the location in its *Section / tab* column (for example *Brighton - Plat 1*); saved ticks still match.
* **Layout**: every tab, in every mode, now fits a 1366 x 768 laptop screen when the window fills the screen, with no scrolling. Stock Tools, Stats Pack and Timing Tools each choose what to do from one *Task* drop-down (only that task's options are shown), the logs are shorter, and Live View's lists are lower.
**3.28.2** - small fixes
* **Berthing chart**: a unit that arrived before Saturday and leaves after Friday night is now shown leaving once, in the last SAT START column, instead of also in the first one. Column A is now wide enough for the *Other - ...* berth names and the *Unit counts - ...* headings.
* **CWN files**: an `.xlsb` workbook is checked for an oversized or booby-trapped archive before it is opened, as `.xlsx` files already were.
* **Choosing CWNs**: the days a CWN covers are read for every large CWN in one helper process, not one each, so choosing two big CWNs is quicker to settle.
* **Section 4 rules**: rebuilding the built-in Section 4 rule set now also writes its small summary file, so the header can still say which rules are in use.
* **Section 4 check**: running the check again on an unchanged timetable XML reuses the XML already read.
* **Command line**: `reorder` stops with a message when `--merge-diagrams` or `--merge-berths` is given without `--merge`, or `--merge-berth-diagrams` without `--merge-berths`.
* **Updates**: a new version saved to Downloads goes to wherever Windows keeps that folder, even when it has been moved or renamed.

**3.28.1** - Section 4 and TPR comparisons follow the real 2027 V4 documents
* **Section 4**: each route's **NOTES** and **Timetable Construction Notes** (and other text outside the possession tables) are now compared; possession rows are paired by section number, night **and what is blocked**, so a section with several possessions a night no longer mis-pairs after an insertion; the issue's version and date are shown for information.
* **TPR**: the covering commentary, contents pages and running header / footer (found by repetition, including landscape pages) are left out instead of being read as tables and titles; sections follow the numbered headings; table rows are paired by lining the versions up; deleted (green, struck-through) wording is ignored.
* Both readers also handle the pages Network Rail turns through 90 degrees (Section 4) and the thin change bars in the margin (TPR).

**3.28.0** - Section 4 and TPR comparisons, Section 4 remarks, stock-day station books, Live View checking
* **New: compare two sets of Section 4 documents** and **two sets of Timetable Planning Rules** (Timing Tools, Live View and command line): times, dates, locations and notes / every table row and paragraph; headers are not compared.
* **Section 4 check reads the remarks**: excepted train types, named trains, depot access (routing and destination checked), dates, weeks and lines; lifted clashes on a new *Exempt* sheet, remarks to check by hand flagged. Runs-as-required trains (unless passenger) and trains on MAINT diagrams are left out (*Skipped*). New command line: `timetable --s4-check`.
* **Unit reports**: no next-day working is inferred from Lovers Walk, Stewarts Lane or Selhurst; the unit's cycle ends there.
* **Station books follow the stock day** (each day starts with its diagrams' first train) and can **merge other operators' Attune XMLs**.
* **Live View**: *Passenger times only*; **confirm each train** with ticks that are saved automatically and can be saved / loaded; new comparisons (Section 4 and TPR documents, Section 4 check, berthing charts, unit reports); CWNs now ignore spacing as the report does and show Start/Call/Pass changes.
* **Train prints**: *Passenger times only* for the report too (`--passenger-only`).
* **Put days in order**: clicking a diagram number no longer jumps to another tab.
* **Stats pack**: class 701/5 removed from the built-in fleet data (and from your fleet table if you had not changed it).

**3.27.7** - neater berthing chart notes, no MAINT
* **Long notes stay inside their berth's box.** A long note about a berth (e.g. "If No 2 Carriage Siding has more than 4 car berthed access to No 3 Siding is blocked", "OUT OF USE UNTIL FURTHER NOTICE") is now written across the day columns of that berth's own box, in red bold on pale yellow, instead of on full-width rows between two siding locations. The boxes on a sheet stay the same height, grown only as far as the longest set of notes needs.
* **MAINT is left off the berthing chart.** Maintenance moves are no longer berthed, and a location that only had MAINT units (such as "Other - HORSHAM platform/road 2") is no longer listed.

**3.27.6** - berthing chart night lines
* **The thicker line in a berthing chart is now between one day's FINISH and the next day's START** (between the nights), and the thin line between a day's own START and FINISH, instead of the other way round.

**3.27.5** - symmetrical app icon
* **The app icon is now symmetrical**, like the real front of a Class 387 (the offset in 3.27.4 came from the angle of the reference photo): central gangway door, a windscreen either side, and a headlight and marker lamp in each yellow panel.

**3.27.4** - app icon drawn from the real train front
* **The icon now follows the real front of a Class 387**: arched roof with the yellow hood and orange line, the gangway door left of centre, a narrow left and a wide right windscreen, a single lamp on the left and twin lamps on the right in the yellow panels, and the blue valance with the coupler cover. It is used for the window icon, header logo, exe and README.

**3.27.3** - new app icon
* **A cleaner app icon**: a flat, front-on electric-unit cab (blue body, yellow hood and door, dark windscreens, headlights, red / white side stripes) on a light tile, drawn with a few bold shapes so it stays clear at taskbar size. The window icon, header logo and README logo all use it.

**3.27.2** - automatic releases, small tidy-ups
* **Releases are published automatically** when a new version is pushed to `main`; pushes that keep the same version only build.
* Small internal tidy-ups (an unused parameter removed, a few older code idioms modernised). Nothing changes in how the app works.

**3.27.1** - berthing chart cells
* **Trains in a berthing chart are left-aligned** in each night's box instead of centred, as on the original charts. A long entry still shrinks to fit rather than spilling over.

**3.27.0** - merging by location, click-to-see values, lean outputs, local saving, a quicker window
* **Merging is decided by what happens at the location**: AM / PM berths no longer keep a train's variants apart (as promised: a train that differs only where its units berth still merges). Diagram numbers and next-day workings still follow their tick boxes.
* **Values that differ by day are shown as the value for most days and a ▾** instead of small day codes squeezed into the cell: click the cell to see each day's value. The DAYS column widens when a merged day code needs it.
* **The log says why variants stayed apart**, with the first thing that differs on that tab.
* **Comparison CWNs made by the app can be put in order** (highlights and struck-through values move with their rows).
* **No more unused formatting**: formatting a CWN carries past its last train (to the last column or far down the sheet) is trimmed from every output, so Excel's *Check Performance* finds none and the files are smaller and open faster.
* **Outputs are saved on this PC only**, to Downloads by default; network and shared drives are refused.
* **Dropping a file on a box replaces what is there**, on every tab, and a file dropped elsewhere replaces the one in the box it belongs in when every box is full.
* **A quicker, steadier window**: it opens fully drawn and sized (no resizing or restyling in view), buttons have their icons from the start, the tabs no longer check for work several times a second while idle, the Windows light / dark setting is checked when you switch back to the app instead of every five seconds, text size changes repaint once, and the window opens where it was last time.
* **The progress bar shows real progress and no longer flickers**: putting variants in order, station books and berthing charts report each step instead of a spinning bar, reading and saving a CWN report each tab, and the bar never jumps back during a run. Live View's bar stays in place.
* **Fewer drop-down arrows**: file and station boxes list recent files or suggestions when clicked or typed in; the report format and capacity-report directions are radio buttons.
* Old code removed: settings migration from CWN Compare 1.x and Rolling Stock Tools 2.x, the old exe name in the updater, and unused helpers.

**3.26.0** - berthing charts: built-in layout, original-style formatting and unit counts
* **Built-in layout**: a new berthing chart no longer needs a chart to copy the layout from. Leave *Layout from chart* blank and the app's own layout is used, taken from the SNGX Dec 26 Proof 2 chart (26 sheets, 131 berths, with their capacities and notes; no trains). Choosing a chart still lays the new one out like it. The layout is listed under *Options > Rules and reference data*.
* **Looks like the original**: siding names and capacities on light blue; notes about the sidings in red bold (long ones on a full-width row under their location).
* **Siding locations separated**: a dark blue line between the different siding locations on a sheet (e.g. Victoria's platforms, Victoria Sidings and Battersea Pier Sidings).
* **Unit counts for each siding location** (new option): the units of each type every night, as on the original charts, plus a Cars row against the location's capacity, red where it is over.
* **Same-size boxes**: every berth's box on a sheet is the same height and every day column the same width, even with no stock; units that would not fit shrink to fit rather than spilling into the next box.
* **More berths found**: Tilgate No 1–5 (Three Bridges), Victoria Sidings 1–2 and Battersea Pier No 1–2 were read as notes; they are now berths, so their units are placed (626 units on the week tested, up from 600). Units the XML gives no road for at a location with several roads (e.g. Tilgate) fill its berths in turn, and units on a platform not on the sheet are listed in their own place at the bottom.

**3.25.0** - merging variants: diagrams and berths
* **Merging works tab by tab**, as before: a train whose variants differ only where they berth at the end of the day still merges on every tab where its variants are the same.
* **Also when only the diagram numbers differ** (new option): the merged DIAG cell shows each diagram number with its days in small type (e.g. *959* <sub>MO</sub> / *959B* <sub>MSX</sub>).
* **Also when they berth for the same next working** (new option): variants that berth for the same train next day merge, and the berth line's day code is changed to cover them all (MO to ThO berthing for *HE317 05.17* become one *FSX* variant berthing *HE317 05.17TWThFO*). A berth for a different next working is kept separate.
* **... also when that next working's diagram number differs** (new option): both diagram numbers are shown in the berth line, each with its days in small type.
* Tested on the Dec 26 D12 SX CWN: 24 variants merged with all options on; every tab keeps the same trains, the same days each train runs and the same other cells. Also `--merge-diagrams`, `--merge-berths` and `--merge-berth-diagrams` on the command line.

**3.24.0** - highlighted-only CWNs, variants in day order, merging variants
* **New output type: Full CWN with new or changed items highlighted only.** The updated CWN as it is, with anything new or changed highlighted and none of the original versions: no previous values struck through, no change notes and no cancelled trains put back (they are still listed in the change report). The *Show previous value / note* column is greyed out while it is chosen. Also `--highlight-only` on the command line.
* The existing type is now called **Full CWN with changes highlighted and noted**, to say what it adds.
* **Day variants in order, first day first**: the first day a variant runs now always decides its place. Variants of a train that depart more than four hours apart, or either side of midnight (e.g. a ThFO at 23.50 and an MWO at 00.10), were treated as separate trains and left where they were, so a ThFO variant could stay above an MWO one. They are now put in order like any others; a headcode used for two different trains on the same day is still kept apart.
* **Merge variants that are the same apart from their days** (new option under *Put each train's day variants in order*): variants of a train that are identical on a tab apart from their days become one, e.g. MO and FO become *MFO*, and variants covering every day of the CWN become one with no days code. Rows below move up and links follow. Also `--merge` on the command line.

**3.23.0** - Section 4 rules built in
* **2027 EAS v4 Section 4 built in**: the Section 4 check now has Network Rail's Engineering Access Statement 2027 Version 4 Section 4 (Standard Possession Opportunities) for **Kent & Sussex, Anglia, East Coast, East Midlands and Wessex** built in, like the Timetable Planning Rules: 5,848 possession rows in 702 sections, 13/12/2026 to 11/12/2027. Leave the PDF box blank and they are used, with nothing to add first. It is also quicker, as the PDFs do not have to be read each time (about 4 s instead of 6 s for a week).
* **Newer rules still added the same way**: Section 4 sets you add in *Options > Rules and reference data* are used instead of the built-in one; *Use this set* switches back. The built-in set cannot be removed. Sets added before are kept, and the one in use stays in use.
* **Tidier line of route names** in the Section 4 report: notes printed next to a route title (*Published on behalf of Transport for London*, *(see also SW183)*, *Please refer to...*) are no longer part of it, titles that wrap or run into the next line are read whole, and a route whose table starts part way down a page is named correctly (e.g. *EA1110 THORPE-LE-SOKEN TO WALTON-ON-NAZE* rather than the route above it). The clashes found are unchanged.
* The exe's build self-check also confirms the built-in rules are inside it.

**3.22.0** - built with a newer Python: faster and supported for longer
* **Python 3.14**: the app is now built with Python 3.14.6 instead of 3.12. Python 3.12 is past its bug-fix years and now only gets security fixes; 3.14 gets fixes until 2030.
* **Faster**: in testing, a CWN comparison ran about 18% faster and a full week's stats pack about 28% faster. The outputs are exactly the same.
* **Self-check**: the build's self-check of the exe now also opens a window and loads drag and drop, as well as reading an Attune print.
* Nothing else changes: same look, same settings, still no installation or admin rights.

**3.21.3** - no more resizing the window after moving between displays
* **Nothing cut off**: after moving to a display with other scaling, the window grows if its content needs more room (never beyond the display), and is moved back fully onto the display if it now sticks out past an edge. It used to keep only its physical size and stay where it was, so a window near the edge could end up partly off the screen, or too small for the content.
* **Smaller minimum size on small screens**: the window's minimum size never exceeds the display it is on (a large minimum on a small, high-scaling laptop screen could force part of the window off it).
* **Checked again once drawn**: a moment after the rescale the app looks at where the window really is and moves it back onto the display if any part is off an edge (Windows can delay or adjust a move made during the rescale).
* **One step, when you let go**: while the window is still being dragged, the rescale waits; it happens once the mouse button is released, in one go, instead of resizing and relaying out the window under the mouse mid-drag.

**3.21.2** - quicker when moving between displays (again)
* **Images drawn ahead**: a few seconds after the app opens, it asks Windows which scaling each connected display uses (e.g. 200% on a 4K laptop, 100% on a 1440p monitor) and draws the icons, tick boxes and radio buttons for those displays in spare time. Moving the window to another display then only has to lay it out again.
* **Images kept**: icons and tick boxes drawn for a display are kept, so moving back and forth never draws them twice.
* **Sizes only**: a scaling change now re-applies only the sizes that depend on it (tick boxes, arrows, scrollbars, icons) instead of the whole theme.
* Measured (median of five runs): the first move to a display with other scaling 262 ms -> 169 ms; later moves 177 ms -> 143 ms. What remains is the window being laid out at the new size.

**3.21.1** - a cleaner, more professional look; sturdier with damaged files; lighter PDF and Word packs
* **One flat look in every theme**: light mode on Windows now uses the same flat style as dark and high contrast (it used the old Windows 'Vista' controls), so every theme matches.
* **Less text on screen**: tips and longer notes (drag-and-drop tips, what each comparison checks, the default output name and folder, notes about the files) now show as one short line - an info icon with *Tips*, *What is checked*, *Default name and folder*... - and the full text appears when the mouse rests on it or it is clicked. Each tab's one-line description stays.
* **No empty gaps**: notes that have nothing to say in the chosen mode no longer leave blank space in their section.
* **Icons**: Run, Browse, Add and Open buttons and the four tabs have small icons, drawn by the app at the display's scaling in the theme's colours (greyed when a button is not available).
* **Status bar** along the bottom of the window: the last result from any tab (time, what finished and its summary, or what failed), with *Open output* and *Open folder* links.
* **Damaged files**: a CWN tab that cannot be read (a damaged file) is now left out of both sides of the comparison, with a warning, instead of its trains showing as changed. Train lists and timetables with a damaged sheet, a stats pack with a damaged text table, and an Attune XML with no trains (for a berthing chart) now stop with a plain message saying what is wrong. Live View refuses a CWN with no location tabs and names the file. Messages show file names rather than full paths.
* **Stats packs as PDF and Word**: a full week as PDF (about 4,700 pages) is made in about 75 s instead of about 130 s, using about half the memory (0.6 GB instead of 1.2 GB); as Word it uses 0.4 GB instead of 1.2 GB. The documents are page-for-page identical.
* **Stress tested**: 78 damaged or hostile files (empty, truncated, random bytes, renamed Word files, XML bombs and external entities, damaged sheets) through every tool, with no hangs, crashes or unexplained errors; inputs 3 to 5 times the real size (a 39,000-train CWN in 26 s, a 47,800-train list in 25 s) with change counts matching a cell-by-cell check exactly; every output reopened cleanly from a 261-character accented folder path, with cells starting =, +, - or @ kept as text; and 2,000 tab and mode switches, 200 theme switches, 100 display scaling switches and 60 Live View loads without any growth in windows, images, timers or memory.
* (3.21.0 was not published: its build check expected the full-size layout on a short-screen test machine. Fixed.)

**3.20.4** - review fixes: Live View highlights, print reader, drop-down, berthing smoke test
* **Live View, CWNs**: unit, note and next-day working lines are highlighted the way the comparison judges them. Lines that only moved (units listed in another order, next-day workings re-ordered or with only a different day code) are no longer shown as changed; only the line that really differs is.
* **Live View, two plans**: warnings from building each plan (e.g. a fleet missing from the fleet table) are now shown, as in the stats pack comparison. A comparison CWN without its stored data now gives a plain message instead of an error.
* **Attune train prints**: a location line with a time printed on to the station name is still left out, but the run now says so (with examples) so those calls can be checked by eye. The same train heading twice on one page now reads as two trains; a heading repeated at the top of the next page is still the same train continuing.
* **Station drop-down**: opens above the box when there is no room below it on the screen.
* **Attune XML**: washes, CETs, fuel and notes inside another diagram's coupled entry are never counted for this diagram (none were in the real XML checked), and a location without a code is ignored.
* **Build**: the release build now also makes and compares a berthing chart with the built exe, proving the berthing tools and berth list are bundled.

**3.20.3** - full check: list pairing, fleet warning, sharper tick boxes
* **Retimed trains in Attune train lists**: without a UID column, departure time is part of how trains are paired, so a train retimed by a minute used to show as one train removed and one added. It is now paired and its new time reported as a change, but only when it is the only train left on each side with its headcode, days and origin; where two or more are left they are still listed as added and removed, never guessed. An LTP row and its STP twin with the same key now keep to their own stage if the export is re-sorted. *What Was Compared* says how many were paired this way.
* **Train list report**: the *Changes by Train* sheet no longer has an empty UID column when neither list has UIDs.
* **Stats pack fleet warning**: a fleet in the TRENT print that is not in the fleet table (e.g. MAINT) makes the vehicle figures and totals show as ??? (as TRACS-RS does). The run now says which fleet and how to add it, once for the whole pack.
* **Tick boxes and radio buttons**: in dark, high contrast (and light off Windows) they are now drawn for the display's scaling, with a proper tick and a dot in proportion. At 150-200% they used to have thin, faint marks. Disabled boxes show their ticks greyed rather than blank.
* **Checked, no change needed**: every input compared with itself gives no differences; known edits to real CWNs, train lists, timetables and berthing charts each give exactly the expected change (and formatting-only edits none); comparisons are symmetric; .xls copies read identically; outputs, all tabs, modes and themes were reviewed at 100% and 200%.
* Removed one unused piece of berthing code.

**3.20.2** - quicker when moving between displays
* **Rescaling starts sooner**: the app now notices a display with different scaling while the window is being moved and rescales a moment after (it used to wait until the window had been still for 0.3 s).
* **One clean repaint on Windows**: painting is held while the text, spacing and window size change, then the window is redrawn once, instead of visibly redrawing piece by piece.
* **Less work each time**: the display check only watches the main window (it ran for every widget, several hundred times per rescale and per resize step), and a scaling change keeps the theme's colours instead of recolouring every control. Measured: about 20% less time per rescale, and window resizing is lighter too.

**3.20.1** - rules indicator, pairing and build fixes
* **Rules in use** (new): the header shows which Timetable Planning Rules and Section 4 rule set the app is using, e.g. *Rules: TPR 2027 (v4) · Section 4: 2027 EAS v4*. It turns orange with *(check)* when a set is past its last date or no Section 4 set has been added; click it to open Rules and reference data.
* **Next-day workings (Stock Tools)**: after matching by berth road and unit position, a left-over line is paired with another only when it cannot be a guess (one each, neither with a unit position). Two unrelated lines are no longer shown as one *changed from ... to ...*.
* **Comparing two folders of CWNs**: only real dates are ignored when pairing files. Unit numbers (*377001*), impossible dates (*20261399*) and runs of numbers that are part of a name stay, so different CWNs are not mistaken for the same one; *v2 12 car* keeps its *12*.
* **Command line**: a wrong `--between`, `--at` or `--direction` is reported the same way as every other mistake (the check no longer ends the program from inside).
* **Building it yourself** (`build_windows.bat`) now matches the release build: it checks for Python 3.12, starts from a clean environment each time, stops if the version file step fails and finishes with a smoke test of the exe. The one deliberate difference (a ready-made PyInstaller bootloader instead of compiling it) is explained in the file.

**3.20.0** - berthing charts
* **Berthing charts** (new, Stock Tools tab): make SNGX's berthing chart from an Attune XML in the layout of an earlier chart, tidied (one font, consistent borders, no old formulas or counting sections); STP charts from an LTP and an STP XML with STP trains in bold on lavender; add a round of changes to a chart from the original and updated XML, highlighted in a colour with earlier highlights kept; and compare two charts. Each unit's arrival, departure, *Berth* days, *RP* (rear portion attached to that morning) and coupled formations come from the XML's diagrams and next-day workings; 387/2 in red and 387/3 in green. A change report comes with each round and comparison, and a Notes sheet lists anything to check.
* The berth list links each berth on the charts to its TIPLOC and platform / road and can be edited in Excel (*Edit berth locations...*).

**3.19.3** - fewer pop-ups, folder pairing and --between fixed
* **Hover help trimmed**: no pop-ups on the menu bar (*Options*, *Save/Load*, *Help*), and none that only repeat a control's own words (e.g. *Clear*, *Swap files*, *Open report*, *Start (F5)* on run buttons, the day, class and operator tick boxes, *All days* / *Weekdays*, *The Attune diagram export (.xml) of the original plan*). Pop-ups that add something - formats, examples, what a blank box means, what is copied or never overwritten, the fuel-check rule, what each change type covers - are kept (64 of 145).
* **Comparing two folders of CWNs**: versions and dates written with underscores or hyphens are now ignored when pairing files (they were kept, because a regular expression treats an underscore as part of a word). *BTN_CWN_v1.2* pairs with *BTN_CWN_v2.0*, *..._14_12_2026* with *..._02_01_2027*, and GTR's draft files *260918_-_GTRTLGN_Dec26_D12_Draft_CWN_-_SX / SO / Su* with their *D13* versions (none of the three paired before). A number that is part of the name, such as *Line 2*, still keeps files apart.
* **Command line `--between`**: checked before the timetable is read, with a plain message for each mistake - one time only (*--between 07:00*), a time after 24:00, `--between` without a capacity report, `--at` or `--direction` without `--between`, `--at` missing for a service group or corridor, or `--at` given for station to station. Before, most of these were ignored (a full stats pack was made instead of the capacity report) or failed only after reading the plan.
* **Time windows end at 24:00**: a time such as 24:30 is refused, in the app and on the command line (it was read as 00:29 and counted the wrong trains).

**3.19.2** - next-day workings never paired with an unrelated one
* **Stock Tools**: when several next-day working lines change, each is now paired with the same berth road, then the same unit position *(n)*. Lines for different unit positions are reported as one removed and one added, never as an unrelated *changed from ... to ...* (before, the first left-over line was used, which could cross units (1) and (2)).
* **Unit reports**: where an XML has both LTP and STP versions of a diagram, an STP *Stabld* now also replaces the LTP plan's next-day working (before, the superseded LTP link was kept and the unit was followed into an unrelated diagram - 34 links in the week 37 XML).
* **Unit reports**: a unit is never followed into a diagram another unit already works. When a unit's note skips a stabled day and that day's stabling diagram (same fleet, same place) forms the same diagram, the unit is followed through it, e.g. *MO SU852 >? TO SU860 > WO SU861*. Any other clash in the plan is listed in the notes. In week 37, 76 diagram-days had been counted in two units at once; now none are, so wash, CET, fuel and unit totals for the affected units are lower and correct (e.g. 171/8 units 19 to 16, washes 65 to 58).

**3.19.1** - error log in the Help menu, pinned build
* **Help > Open error log** (new): opens the log of unexpected errors to send with a support request, or says that none have been recorded.
* **Pinned build**: every package used to build and test the exe now has an exact version (`packaging/build-requirements.txt`, the set 3.19.0 was built with), as does Python itself (3.12.10), so building the same version again gives the same app. `requirements.txt` still lists the minimum versions for running from source.
* Fixed an intermittent build failure in the display-scaling test, and a font set-up fault that only affected a second app window opened in the same process (seen in tests, not in normal use).

**3.19.0** - pre-release audit: steadier, quicker, safer and portable
* **Portable**: settings, recent files, rule sets, fleet data and the error log now live in a **TrainPlanningTools-data** folder beside the exe, so copying the exe and that folder takes everything with it. Nothing is written to the registry. If the exe's folder cannot be written to, `%LOCALAPPDATA%\TrainPlanningTools` is used as before. The first time the folder is made, the settings already saved in `%LOCALAPPDATA%` are copied into it (the originals are left alone).
* **Files open in Excel, read-only folders and full disks** now get a plain message on every tab, including the Station Working Book and *Put day variants in order*, which showed a raw error before. Unexpected errors are all recorded the same way, in `error.log` in the settings folder.
* **No more pauses when dropping files**: Timing Tools now reads only a workbook's sheet names to tell timetables from train lists (about 1 ms instead of up to half a second per file), and checks dropped PDFs for Section 4 only while every file could still be one.
* A stats pack that is compared is closed as soon as it has been read, so it is never left locked. Timers are stopped when the app closes.
* **Security**: text in a CWN that starts with `=` stays text in the highlighted CWN and in reordered CWNs, even on rows the app moves; it can no longer become a live formula. The minimum PDF reader version (pypdf 6.21.4) now includes all its published security fixes. Every output was checked against 3.18.0 and is identical.
* Housekeeping: the build checks code style (ruff) and types (mypy) before the tests; `build_windows.bat` builds the current app again; leftover code removed; PDF reader notices no longer printed.

**3.18.0** - sharp on every display
* **No more blurry window on high-resolution screens**: the app now tells Windows it handles each display's own scaling, so Windows no longer stretches it. Text and controls are drawn sharply on a 4K laptop at 200% as well as on a 1440p monitor at 100%.
* **Moving between displays**: drag the window to a display with different scaling and, once it settles there, the text, spacing, tick boxes, drop-down arrows, scrollbars, table columns, hover help and logo are redrawn for that display, and the window keeps the same physical size (kept within that display). Nothing is recalculated while the window stays on displays with the same scaling, so moving it costs nothing.
* Hover help, typing suggestions and the finished-in-the-background notice now appear on the display the app is on (they could jump to the main display before).
* The compact layout is chosen from the display's scaled height (a 4K laptop at 200% counts as 1080 lines high).

**3.17.1** - clearer wording
* **Shorter, plainer text throughout**: tab descriptions, notes, tips and hover help no longer explain things planners already know or how the app works inside (e.g. *trains, not Excel rows*, how trains are matched, *hold Ctrl in the file window*, *using several CPU cores*, what a CET or an ACWN is). Each tab's description is now one line, e.g. *Compares an original and an updated CWN, and produces a highlighted CWN and a change report.*
* **Layout fixes**: the capacity report's group, corridor and station boxes and the note under *Service group* now fit their section; the Live View colour key and its *< Previous* / *Next >* / *Export...* buttons are no longer cut off on smaller windows.

**3.17.0** - rule sets and the new-timetable reminder
* **Platform length check removed** from the Station Working Book: Attune already checks platform lengths, and selective door opening is used throughout the network. Its built-in platform table and code are gone; unit lengths stay in the fleet table.
* **Options > Rules and reference data** (new): shows the Network Rail rules built into the app (the Timetable Planning Rules 2027 headcode descriptions used for service groups) and the **Section 4 rule sets** you have added, with a link to Network Rail's rules page for the latest versions: https://www.networkrail.co.uk/industry-and-commercial/information-for-operators/operational-rules/
  * **Add Section 4 rule set...** reads the Section 4 PDFs once and keeps only what the check needs, compressed, in your settings folder (all five 2027 v4 route PDFs, 23 MB, become a 133 KB rule set). The app itself does not grow.
  * **Use this set** chooses the set in use; **Remove** deletes a set (the PDFs are not touched).
* **Section 4 check**: the PDF box is now optional. Leave it blank to use the rule set in use (the tab says which). If the rules do not cover the timetable's dates, the report and log say they may be out of date and give the download link.
* **New-timetable reminder**: the first time a timetable from **Dec 27** onwards is opened (an Attune XML on the Stats Pack, Station Working Book or Section 4 check), the app reminds you to check the latest Section 4 and Timetable Planning Rules are loaded, says which are in use and whether the built-in rules are out of date for that timetable, gives the download link and offers to open *Rules and reference data*. Each timetable is reminded once.

**3.16.0** - Stock Tools, Timing Tools and the Section 4 check
* **Tabs renamed**: *CWN Tools* is now **Stock Tools** and *Timetable Comparison* is now **Timing Tools** (tab, heading, window title, messages and help).
* **Stock Tools is in two sections, each with its own files and drop area**:
  * **1. CWN comparison** (compare two CWNs, add a new round, compare two folders) with the original and updated CWN boxes;
  * **Utilities** (put day variants in order, Station Working Book) with one box that takes the CWN or the Attune XML.
  
  Dropping CWNs or folders on the comparison section puts them there; dropping a CWN on Utilities picks *day variants in order*, and an XML picks *Station Working Book*. The section not in use has its title greyed. Typing in a section's box picks that section.
* **New: Section 4 check** (Timing Tools > Utilities, with its own Attune XML and Section 4 PDF boxes and drop area). It reads Network Rail's Engineering Access Statement **Section 4 (Standard Possession Opportunities)** PDFs. Each route's tables are read from their drawn cells, so a possession that covers several periods applies to each. Tested on the 2027 v4 Kent & Sussex, East Coast, Anglia, East Midlands and Wessex PDFs: 6,000+ possession rows. It then lists every train in the XML that runs over a section (calls at or passes both its ends) inside a possession window, on a night and in a period the possession applies to. Only the periods the XML's dates cover are checked.
  * The report (Excel, PDF or Word) has *Summary*, *Clashes*, *By Section*, *Not Checked* (places in the PDFs that aren't in the XML, mostly other operators' lines) and *What Was Compared*.
  * Each clash shows the section, period, night, window, how often it's available (e.g. *8 weeks a year*), what is blocked, the train, and its times at both ends on the day they fall.
  * The Attune XML has no running lines, so a clash is marked **Every line blocked** (shaded, listed first) or **Some lines: check the line used** (e.g. only the slow lines are blocked). Where only the Down or only the Up line is blocked, trains in the other direction are left out.
* **Fleet table**: 379/0 unit length 80.77 m (as the 387), 717/0 121.7 m, and 171/8 corrected to 70.86 m (3-car). Existing fleet tables get these where the cells were blank or still held the old shipped 171/8 length; lengths you entered yourself are kept.

**3.15.0** - Network Rail planning rules
* **Platform length check in the Station Working Book**: the app now carries the usable length of every platform in Network Rail's Timetable Planning Rules 2027 (Sussex, Kent, Wessex, Anglia, East Midlands and LNE: 2,994 platforms at 1,186 stations). Each departure's formation (unit lengths from the fleet table) is checked against its platform, and departures longer than the platform (by more than 3 m) are listed in the run's messages with the rules' own notes, e.g. *9V12ET 06 49 platform 1: 162 m on a 149 m platform*. Check these for selective door opening. Fleets with no unit length in the fleet table (currently 379/0 and 717/0) are named so their lengths can be added.
* **Fixed: units counted twice in Station Working Books** made from an XML holding both the LTP and the STP version of a unit diagram for the same day (e.g. a week's STP + LTP export). The stock column showed each unit twice (e.g. `(700/0)` `(700/0)` for one 8-car) and some departures were listed twice. Only the STP version is now used where both run, as in Attune; the same rule now applies to the next-day workings in unit reports.
* **Service groups described as in the planning rules**: the capacity report's headcode groups now use Network Rail's own descriptions from the Timetable Planning Rules headcode tables (e.g. *1A London Victoria and Brighton (fast)*, *9T Bedford and Gatwick Airport / Three Bridges / Brighton via London Bridge and Quarry Lines*), with both meanings where SNGX and TLGN share a code (e.g. *1C SN: London Victoria / London Bridge and Portsmouth via Horsham; GN: King's Cross and Cambridge (semi-fast)*). With an XML, the train count is added. The description is also on the report's notes.
* **Station names matched more reliably** between Network Rail's and Attune's spellings: *London Victoria (Central)* / *(Eastern)* against *London Victoria (C)*, *St Leonards Warrior Square* against *St. Leonards Warrior Sq*, *Junction* / *Jn*, *King's* with a curly apostrophe, and names in brackets (*Kensington (Olympia)*). This also helps corridors and station boxes.

**3.14.0** - TRENT VehicleLayout29 prints only
* **The Stats Pack and Live View take the TRENT VehicleLayout29 print only**, to keep the input simple: VL29 has everything the app uses (TIPLOCs, full headcodes, LTP / STP, platforms and miles) for SNGX and TLGN. The file boxes are now labelled *TRENT VL29 print(s)*. A VehicleLayout23 (or TLGN unit diagram) print, VL11 or VL05 print is refused with a message saying to use VL29. Several VL29 prints still go in one box, e.g. the LTP print with a week's STP print.

**3.13.1** - easier station and group boxes
* **Suggestions as you type**: typing in a station box (capacity report stations, the time-window station and the Station Working Book station) lists the matching stations just below it. Names starting with what you've typed come first, then names with a word starting with it (e.g. *bri* finds Brighton, then London Bridge). Use Down / Up and Enter (or click) to take one, and Escape to close the list.
* **Type over any box**: the capacity report's *Service group* and *Corridor* boxes used to be pick-only. You can now type in them too, with the same suggestions. Type any headcode group (e.g. `1F`, `9J`), or enough of a corridor's name to pick it out. Station names not in the list are kept as typed.
* **Service groups before an XML is chosen**: the list used to be empty, apart from the last group used, until an Attune XML was read. It now shows a built-in list of every SNGX and TLGN headcode group (62, e.g. 1A-2Z and 9A-9Z) with their main routes. Choosing the XML replaces it with that timetable's own groups and train counts.

**3.13.0** - week 37 (timetable change) data
* **Week STP prints**: VehicleLayout23, 11 and 05 don't print LTP / STP, so a diagram running for a week or less is now taken as **STP**. When the LTP print and a week's STP print are loaded together, the STP version is used, as it already was with VL29. A stats pack or unit report made from a week's STP print only is named by its railway week (e.g. *Stats pack for STP wc 12 Dec 2026*) instead of *DEC26*.
* **More TRENT locations**: Edenbridge, Polegate, Polegate shunt signal 1373, North Pole turnback siding and North Pole signal VC818 (full and short names), found in the week 37 prints.
* **Attune train list exports**: the *Work Dep*, *Work Arr* and *Stage* (LTP / STP) columns are now recognised, so trains are paired by headcode, days, departure time and origin, with no duplicate pairings. Bus replacement IDs (e.g. `BHQ200`) are kept instead of being dropped. The record-keeping columns (*Last Update*, *Last Updated By*, *Lock Id*, *Update Id*, *Edited?*) are no longer reported as changes; *What Was Compared* lists them.
* **CWN Tools**: comparing a single-day CWN (no day codes on its trains) with a CWN whose trains carry a day code (e.g. the LTP SX CWN against a week's WO CWN) no longer reports a days change on every train.
* **Station Working Book**: fixed a crash when a unit left a dividing train where the train doesn't stop (seen with the week 37 XML).
* A TRENT diagram whose printed mileage total doesn't match its moves (TRENT's own total sometimes counts miles that no printed move carries, e.g. BI 9003 in week 37) is now explained as such in the warning.

**3.12.0** - every TRENT print layout
* **All four TRENT unit diagram print layouts are read**: VehicleLayout29 (still the best: TIPLOCs, LTP/STP, miles), VehicleLayout23 (the same layout as the TLGN print), and now **VehicleLayout11** and **VehicleLayout05**, which used to be rejected. Checked against the full Dec 26 prints of every GTR train: all four layouts give the same 2,369 diagrams with the same trains, times, units and miles.
* **Built-in table of every GTR location in TRENT** (210 TIPLOCs, with TRENT's full and short names), so station names in VL23, VL11, VL05 and the TLGN print become TIPLOCs, as in VL29. Depots, captive units, XML matching and the stats pack then work exactly as with VL29.
* **Several layouts together**: put **VehicleLayout29 and VehicleLayout23** in the same box and VL23's *Forms (Next Day)* links are added to VL29's diagrams, so unit reports follow units exactly even without an XML (72 units fully linked from the Dec 26 prints, against 17 from VL29 alone). A diagram in two prints is read once, from the more complete layout.
* **With the XML, 4-character headcodes become full train IDs** (e.g. `2L98` -> `2L98GR`), so a VL23 / VL11 / TLGN stats pack lists and counts trains as a VL29 one does, including trains that keep the same four characters but change ID when they reverse (e.g. 5Y47GS -> 5Y47GT).
* Fixes found by comparing the layouts:
  * the TLGN print (and VL23) lost **which units were coupled on each train** (positions such as `10(1)/1(2)` weren't recognised), so TLGN formations, coupled-unit counts and capacity were wrong;
  * activity times printed with half minutes (`06+09½`) were dropped;
  * a train leaving after midnight now matches the XML version that runs on the following day when two versions share a headcode.
* Unit reports made from a TRENT print alone show station names (from the built-in lists), and their note explains how to get exact next-day links.

**3.11.2** - polish
* **Clearer messages**: every "choose a file" / "file not found" / "output folder does not exist" message now uses the same wording on every tab, and messages about TRENT prints name both the SNGX and TLGN prints.
* **CWN Tools**: the heading follows what you're doing (*Carriage Working Notice Comparison*, *Day Variants in Order* or *Station Working Book*), and in station mode the third section is called *Stations and output*.
* **This guide**: the introduction lists the tabs in the app's order, includes station working books, unit and capacity reports, and links straight to the Releases page.

**3.11.1**
* **New home**: the app is now published in this public repository, [Albinoboy64/Train-Planning-Tools](https://github.com/Albinoboy64/Train-Planning-Tools), under the GPL-3.0 licence. *Check for updates* looks here from this version on (no token needed). Copies of 3.11.0 or earlier must be replaced by hand once: see [Updates](#updates).
* **379/0 seats and standing room** are in the fleet data (20 First Class, 189 Standard Class, 136 standing), so capacity reports count the 379s. Your own copy of the fleet data is updated automatically unless you entered your own figures.

**3.11.0**
* **Live View**
  * **Click a row to highlight it right across**: the original and updated values side by side, on every kind of comparison, with the row's full values in the box underneath.
  * Train prints: the **train details fold away** under a *▼ Train details* heading (remembered). Folded, the heading still flags how many details differ.
* **Several Station Working Books in one run**: *Add to list* (or `;` between stations), one book per station, made on several CPU cores.
* **Compact layout on smaller screens** (e.g. a 1366 x 768 laptop): smaller header, tighter spacing, and the long descriptions and tips kept in the hover help, so every tab fits without scrolling. Larger screens are unchanged.
* **TLGN stats packs** give the XML's TIPLOCs in the location-code columns (they showed TRENT station names), also where TRENT and Attune name a place differently.
* **Location names**: the built-in list now covers every GTR location in the Dec 26 plan (591, was 95), for Attune train lists that use codes.
* **Safety and stability**
  * The fast PDF reader (PDFium) runs only in helper processes: a damaged or hostile PDF can no longer close the app, and a reader that hangs is stopped and the file read the slower way.
  * Update checks and downloads can no longer hang on an unexpected reply from GitHub or a cut connection, and leave no half-downloaded file.
  * The app only ever opens folders and documents, never a program.
  * Every background task catches its own errors, so a tab is never left stuck on "running".
* **Help > Third-party software and licences**. Outputs made by the app name *Train Planning Tools* as their author, and personal details were removed from the timetable template's file properties.
* Quicker *Put day variants in order* (only the rows that move are rewritten); unused code removed.

**3.10.0**
* **TLGN data**: the Stats Pack now reads the **TLGN unit diagram print** as well as SNGX VehicleLayout29: station names, 4-character headcodes, running mileage (turned into miles per move), stabling TIPLOCs named, and the *Forms (Next Day)* / *Off (Previous Day)* links used to follow units from day to day. Several TRENT prints go in one box (TLGN has one per day type) on the Stats Pack and Live View tabs and on the command line (`--trent "SX.docx;SO.docx;SU.docx"`). **Unit reports can be made without an XML.** The depot list knows Hornsey, Three Bridges and Bedford Cauldwell by TIPLOC and by name, and the capacity report has the TLGN routes (Thameslink Core, Midland Main Line, East Coast Main Line, Kings Cross - Finsbury Park, Cambridge Line, Fen Line, Hertford Loop, Northern City Line, Thameslink via London Bridge, Wimbledon Loop, Catford Loop to Sevenoaks, and London Bridge - Rainham), each in either direction. A corridor station can list other spellings (`London Blackfriars|Blackfriars`). TLGN CWNs (with no heading over the day code column) are compared, reordered and reported like SNGX ones.
* **Sunday trains in the Attune XML**: the second character of Attune's day mask is Sunday. It was read as no day, so Sunday trains and unit diagrams were missed (e.g. Sunday station working book sheets came out empty). Trains leaving after midnight in a diagram are now also found under the next day in the XML, so their calling points and seconds come from the XML (28 of a TLGN Saturday's trains before, 2 now).
* **Train print comparison much faster**: see *Speed* under [Two sets of train prints](#compare-two-sets-of-train-prints-pdf-or-word-or-attune-vpt-exports). Pairing thousands of trains is also quicker. Empty-stock trains whose heading has no space before the train ID (`EE5C90BV`) are read.
* **Train prints side by side like the timetable comparison**, with activity codes, platforms, allowances and the train's days run and details at the top, in the Live View and on the report's new **Side by Side** sheet. The timetable comparison in the Live View also shows both trains' days at the top.
* **Half minutes kept**: timetables and Attune prints / lists are compared to the half minute unless one side is a whole-minute public timetable (see *Half minutes* under [Timetable Comparison](#check-a-timetable-against-train-prints-or-an-attune-train-list)).
* Fix: comparing a CWN containing cells moved without a style (e.g. by another program) could stop with *'NoneType' object has no attribute 'fontId'*.

**3.9.0**
* **Station Working Book** (new on the CWN Tools tab): a TRACS-RS style station working book from an Attune XML - every train leaving a station (or a group of its platforms), with its inward working(s), stock, platform and calling points, dividing and attaching trains, berthing and day notes, on SX / SO / Su sheets. See [Station Working Book](#station-working-book-tracs-rs-layout). Command line: `stationbook`.
* **Capacity report** (was *Seats report*): new **Seating capacity** and **Standing room** tick boxes choose which figures are shown (both: total capacity too). Tabs are now *Capacity Summary*, *Capacity by Hour* and *Capacity by Train*. Command line: `--capacity-group` / `--capacity-corridor` / `--capacity-from` / `--capacity-to` (the `--seats-...` names still work), `--no-seating`, `--no-standing`.
* **Live View**: *Ignore trains in the source that are not in the files compared with it* (e.g. when a print covers part of a timetable), and *Check for differences* - untick to put each train side by side with its match for checking by eye, with nothing flagged; trains in only one file are still listed so nothing is missed. Both apply straight away, without reading the files again.
* **Drag and drop goes where you drop it**: a file dropped on a box now goes in that box on every tab (Live View used to fill the boxes in order). Several train prints dropped on a prints box are all added.
* **Several train prints in one comparison**: on the Timetable Comparison and Live View tabs, a train print box has **Add...** (adds prints, from any folder, to the ones already there) and **Clear**.
* **Focus outlines like Windows**: the dotted outline on tabs, tick boxes and buttons now only appears when you move around with the keyboard (Tab), and disappears when you use the mouse, as in other Windows programs.

**3.8.3** - safety and security review
* **No formulas from input files**: text copied from an input (a CWN destination or note, an Attune list cell, a train print) is always written to outputs as text. Before, a cell starting with `=` became a live Excel formula in the output, which a deliberately crafted file could use to run a command when the output was opened.
* **Updates are only installed when verified**: the downloaded program must match the SHA-256 checksum GitHub publishes (or the one in the release notes), must be a Windows program, and must come over a secure (https) link; otherwise nothing is installed. Before, a release without a checksum was installed unchecked. The fallback update script now handles folder names containing `%`, gives up after 2 minutes if the app does not close, and uses a uniquely named temporary file.
* **Oversized "zip bomb" files are refused**: an Excel or Word file that would unpack to an unrealistic size is not opened, instead of filling the PC's memory. (The XML reader was also checked against entity-expansion and external-file attacks; it already refuses both, and tests now keep it that way.)
* **Stray control characters no longer break outputs**: an invisible control character in an input (e.g. from a PDF print) made Word outputs unopenable and could stop Excel outputs being written; such characters are now dropped.
* **Output names stay in the chosen folder**: a typed output name containing `\`, `/`, `..` or a reserved Windows name (CON, NUL...) is turned into a plain file name, so nothing can be saved elsewhere.
* The error log is kept under about 1 MB.
* What the app does on the PC, checked line by line: it only ever deletes or replaces its own files (temporary files while saving, and its own previous version after an update); it never runs other programs except opening your outputs and folders, and starting its own new version after an update; it only contacts GitHub (for updates); and existing outputs are never overwritten.

**3.8.2**
* **The logo survives updates**: after the app updates itself (or a new exe is copied over the old one), it tells Windows the icon has changed, so desktop and Start menu shortcuts, pinned taskbar buttons and Explorer show the new logo straight away instead of a cached old or blank one. The window always shows the logo, even if its icon file cannot be read. Tests now check that every logo file ships and that the build embeds the icon.

**3.8.1**
* **New logo**: a front-on Class 387 Electrostar in the blue, red and white Great British Railways livery (yellow gangway door and warning panel, red / white cab-side stripe) on a sky-blue badge - in the window header, the taskbar, the exe and the README. The header logo is now drawn at its own size (sharper than before) and grows with *Options > Text size*.

**3.8.0**
* **Fuel check (171s)** (new unit report): each diesel unit followed through the week, checking it is fuelled at least every 48 hours, with its longest gap between fuels and units needing attention listed first. Command line: `--unit-reports fuel`.
* **Seats report by headcode group**: *Service group* now lists every headcode group in the XML (1F, 1W, 2F...), with their main routes and number of trains.
* **Corridors for every main route, in either direction**: 23 corridors covering the routes we run, each with *A to B*, *B to A* or *both directions*. Corridors that share a trunk line (e.g. the Oxted lines to Uckfield and East Grinstead) now only count trains that use their own section. Command line: `--corridor-direction forward|reverse|both`.
* **Seats from station to station**: any two stations on the network, counting trains that stop at both in that order, with the smallest formation between them. Command line: `--seats-from STATION --seats-to STATION`.
* An unedited corridor list from 3.6 / 3.7 is brought up to date automatically.

**3.7.0**
* **Compare two timetables in unit reports and seats reports**: tick *Compare two timetables* and choose the original and updated XML + TRENT print. The output shows every summary figure side by side (original, updated, change, change %) and, for trains, units and diagrams, only what changed and what is in one timetable only. See [Comparing two timetables](#comparing-two-timetables-unit-and-capacity-reports).
* **Save/Load menu** (was *Saved*): save as many named settings as you like on each tab, and load, load and run, replace, rename or delete each one from its tab's sub-menu. Settings saved by earlier versions are kept.
* Fixes and polish: options are read before a Stats Pack run starts rather than from the background task (this could crash on Windows); *Check for updates* waits for runs on every tab, not just two; stats-pack-only output options are hidden for unit and seats reports instead of greyed out; "Please choose the ... file" messages keep names such as *Attune XML* and *CWN* in capitals; a time window ending at 24:00 is shown as 24:00; *Put day variants in order* no longer saves an identical copy when everything is already in order; damaged saved settings can no longer cause an error. A new test checks that every module of the app imports.

**3.6.0**
* **Seats report** (new on the Stats Pack tab): seats, standing and total capacity of every passenger train in a service group or on a corridor (both chosen from drop-downs), per day or for the week with a daily average, optionally only trains arriving at / departing a station between two times (e.g. 07:00-10:00 into London Victoria). Excel, PDF or Word, with per-day, per-hour and per-train tabs. The service groups and corridors are an editable list (*Options > Edit service groups and corridors*), starting from a draft Southern / Gatwick Express list to check. See [Seats report](#capacity-report). Command line: `statspack ... --seats-group NAME` or `--seats-corridor NAME`, with `--between 07:00-10:00 --at STATION --direction arriving|departing|both`.

**3.5.0**
* **CWN Compare is now CWN Tools**, as it also puts day variants in order.
* **Accessibility**: *Options > Text size* (Small / Normal / Large / Extra large, or Ctrl + / Ctrl - / Ctrl 0) resizes every label, button, log and table in the window, and a **High contrast** theme (white on black, yellow buttons and focus, cyan selection) that *Follow Windows* also picks when Windows high-contrast mode is on. Outputs are unchanged.
* **Fonts**: the app now uses the same fonts as Windows 11 itself (Segoe UI Variable, falling back to Segoe UI on Windows 10) for all text, and Cascadia Mono (or Consolas) for logs. Some headings and notices previously used fixed fonts that ignored the theme.
* Fix: *Put day variants in order* no longer mixes two different trains that share a headcode on a tab (for example an ECS headcode used in the morning and the evening): each train's variants are ordered among themselves.
* Live View table columns and wrapped text now size themselves from the text size instead of fixed pixel widths.

**3.4.0**
* **Put each train's day variants in order** (new on the CWN Compare tab): saves a tidier copy of a multi-day CWN with each train's variants listed MO first, then in day order to FO (then SO, Su), or by departure time first. Nothing in the CWN is changed or removed, and links between tabs follow the rows. See [Putting day variants in order](#putting-day-variants-in-order). Also on the command line: `reorder CWN.xlsx [--by-time]`.
* **Consistent names**: every app tab and heading uses capital letters (*Timetable Comparison*, *Live View*), and step 1 on the CWN Compare tab is now *What to do*.
* **Clearer output tab names**, all in capitals: change report *By Train* is now *Changes by Train*; train print and train list comparisons have *Changes by Train*, *Trains Added*, *Trains Removed*, *How Trains Were Paired* (was *Match audit*) and *What Was Compared* (was *Audit*); unit reports have *Washes and CETs by Unit* / *by Diagram* / *by Fleet*, *Depot Moves by Diagram*, *Depot Moves by Day* (was *Depot moves summary*), *Depot Moves by Depot* (was *Depot pairs*), *Captive Diagrams* and *Captive Units*; the Live View export has *Comparison Details* (was *About*), *Trains Listed* and *Differences in Detail*.

**3.3.0**
* **CWN output**: notes explaining a change are now in a **Change notes** column to the right of the CWN, beside the change, instead of in extra rows underneath. Only cells holding text are coloured, so new and re-inserted trains are no longer coloured across empty cells.
* **Change report**: *Details* on *All Changes* only gives information the other columns don't (no repeated train names or "changed from ... to ..."). The *Cancelled Trains* and *New Trains* sheets are merged into one *New and Cancelled Trains* sheet in time order. With a single round, the repeated *Round* column and round colours are left out, and categories with no changes are not listed.
* **Unit reports**: on *Depot moves*, diagrams that start and end away from any depot are listed after the returns, swaps and depot departures / arrivals. Empty tabs say *None* instead of showing an empty table.

**3.2.3**
* **Faster timetable comparisons** (about twice as fast on the K_D26 tables: 1.6 s to 0.7 s), with identical results. Each train is now scored only against trains that share a time or its headcode (others can never match), and output sheets are formatted column by column instead of cell by cell.
* Faster train print, Attune list and Live view exports, for the same reason.
* Code clean-up: a duplicated file-opening helper and unused imports removed.

**3.2.2**
* Fix: saving into a deep folder (e.g. a long OneDrive / SharePoint path) could fail with "No such file or directory" when the full path went over Windows' 260-character limit. Files are now written under a short temporary name and saved using Windows' long-path form, and files in such folders can be read too.
* Output names are shortened (at a word break) where needed, so the full path stays within the 218 characters Excel can open. If the folder alone is too deep for that, the full name is kept, and you are told the file was saved but Excel may not open it there, so you can pick a shorter *Save to folder*.
* Timetable comparison outputs no longer replace an existing file of the same name: ` (2)`, ` (3)`... is added, as on the other tabs.

**3.2.1**
* Fix: the Live view stopped with "Can't get local object 'cwn.<locals>.model_of'" when comparing large CWNs (big files are read on several CPU cores, and one reader could not be passed to the helper processes). Any reader that can't run in a helper process is now read in the app instead, and a new test checks the multi-core path for every Live view comparison.

**3.2.0**
* **Compare two folders of CWNs (batch)**: every updated CWN is paired with its original by file name and all pairs are compared in one go, several at once (one per CPU core, as memory allows). Drop two folders on the CWN tab, or use `--original-folder` on the command line. See [Comparing two folders of CWNs](#comparing-two-folders-of-cwns-batch).
* **Saved comparisons** (*Saved* menu): save a tab's files and options under a name and run them again in one click.
* **Live view export**: save the trains listed, with their differences, to Excel, PDF or Word.
* **Notification** when a run finishes while the app is in the background: the taskbar button flashes and a notice appears in the corner of the screen (*Options* to switch off).
* **Help on every control**: rest the mouse on any option, button or box for a short explanation. Clearer wording throughout (e.g. *Add a new round to an earlier comparison CWN*, *ACWN (amended trains only)*), and day tickboxes read Mon-Sun on every tab.
* Fix: running a CWN comparison could reset the saved GitHub access token and the update-check setting.
* Code clean-up (unused code removed) and new tests for batch pairing, saved settings, help text and the Live view export.

**3.1.0**
* **Live view** (new tab): browse any comparison in the app train by train, side by side with differences coloured and described, and see changes as soon as a file is saved. See [Live view](#live-view).
* **CWN Compare: check only some days.** Tick the days to check and output. Only trains running on those days are compared and written, and days the CWNs don't cover are greyed out. Command line: `--days FO`. See [Checking only some days of the week](#checking-only-some-days-of-the-week).
* Tables follow the light / dark theme. Ctrl+4 opens the Live view.
* Faster re-runs: a file that has not changed since it was last read is not read again.

**3.0.2**
* **Smaller and faster to start**: the exe went from 26.0 MB to 15.9 MB (39% less to unpack on every start). Image codecs, a font engine, unused fonts and chart modules that came with the PDF library are no longer included. PDF and Word output are unchanged.
* **Fewer antivirus / SmartScreen triggers**: *Check for updates* now swaps the exe directly (Windows allows a running program to be renamed) instead of running a helper script, which some antivirus tools treat as suspicious; the script is only a fallback, e.g. on network shares. Release notes now show the exe's SHA-256 hash for IT allow-listing.
* Fix: after an update the new version could start sharing the old version's unpacked files, which are removed when the old one closes; it now always starts on its own. Settings are saved before the new version starts.
* **Safer saving**: PDFs and settings files are now written in full before they replace the old file (Excel and Word files already were), so a crash, power cut or full disk can never leave a damaged output or settings file.
* **Keyboard shortcuts**: Ctrl+1 / 2 / 3 switch tabs, F1 opens the user guide, and *Help > Keyboard shortcuts* lists them all.
* Command-line CWN comparisons print a clear error instead of a Python traceback for an unreadable file.

**3.0.1**
* **Train prints against a timetable** and **Attune train list against a timetable** (new on the Timetable comparison tab): the print or list is the reference and the timetable is checked by the same rules, into the same template. See [Train prints or an Attune train list against a timetable](#check-a-timetable-against-train-prints-or-an-attune-train-list).
* The **Options / Help bar** now follows the theme (dark or light), including its drop-down menus.
* Attune **Single Train Report** prints are now read column by column for print-against-print comparisons too, so changes are named precisely. This also fixes two problems with that layout in 3.0.0: trains with the same ID on different days (e.g. FO and FSX) were merged, and heading fields were read as calling points.
* Fewer false positives in every timetable comparison: a station where the other table shows only one of the two times is no longer reported, and a missing arrival is no longer reported as "Departure time shown instead of arrival" when the departure shown is the train's own correct departure.
* More day codes understood (e.g. `TThO`, `WFO`, `MWFX`), and large PDF prints are read on several CPU cores.
* Command line: `timetable --base-prints PRINT.pdf --check TIMETABLE.xlsx` and `timetable --base-list LIST.xlsx --check TIMETABLE.xlsx`.

**3.0.0**
* **Renamed to Train Planning Tools.** Settings, fleet data and the depot list from Rolling Stock Tools are copied across automatically; *Check for updates* in 2.1.5 / 2.1.6 finds this release.
* **New Timetable comparison tab**: GTR timetable against the Network Rail timetable, written into the approved *Consolidated TT Comparison* template (with tidier formatting: borders, coloured results, totals, percentages, print settings); plus **train print** (PDF / Word) and **Attune train list** (Excel) comparisons. See [Timetable comparison](#timing-tools).
* Large inputs are read on several CPU cores at once.
* Command line: `TrainPlanningTools.exe timetable ...`.
* Fix: the built-in depot list was missing from the 2.1.6 exe, so unit reports only recognised depots by name. Every data file the app needs is now bundled automatically, and a missing or locked depot list no longer stops a run.
* Code clean-up and new tests for the timetable comparisons.

**2.1.6**
* **Unit reports** (new on the Stats Pack tab): **washes and CETs per unit**, **depot returns / swaps** and **captive units**, for the whole week (units followed with the Attune next-day workings) or for each day. See [Unit reports](#unit-reports-washes-and-cets-depot-returns--swaps-captive-units-fuel-check).
* **PDF and Word**: every Stats Pack output, and the CWN change report, can be saved as PDF or Word as well as Excel (still the default).
* **Options > Edit depot list** to tell the app which locations are depots.
* Command line: `--format pdf|docx`, `--unit-reports washes,depots,captive` and `--per-day` for stats packs; `--report-format` for CWN Compare.
* Tidier code: one output layer writes Excel, PDF and Word for every Stats Pack output; unused code removed; new tests for the unit reports and documents.

**2.1.5**
* **Options menu**: *Theme* (Follow Windows / Light / Dark), *Check for updates...*, *Check for updates when the app starts*, *GitHub access token...*, *Edit fleet data...* and *Open settings folder*. A *Help* menu links to this guide, opens the error log and shows the version.
* **Update directly from GitHub**: *Options > Check for updates* shows what's new, downloads the new exe, checks it against GitHub's SHA-256 checksum, then closes, swaps the file and reopens on the new version - no browser and no admin rights. If the exe's folder can't be written to, the new version is saved to *Downloads* instead. When the app starts it quietly looks for a newer release and shows *Update available* at the top right.
* **Faster on multi-core PCs**: workbooks are compressed on all CPU cores but one (so the PC stays responsive), CWN outputs are compressed once instead of twice, and comparing two stats pack files reads both at the same time on two cores. A full-week stats pack is written about 25% faster and a full-week pack comparison about 25% faster on a 4-core PC; faster PCs gain more.
* **Excel-safe output**: every output was checked against the rules Excel applies when opening a file (cell and row order, text over 32,767 characters, overlapping merges, sheet names, numbers, column widths, shared strings). The writer now also guards against over-long text and impossible numbers.
* Release notes on GitHub now list what changed in that version (taken from this history).
* Tidier code: unused helpers removed, shared helpers renamed for clarity, new tests for the ZIP writer, updater and naming.

**2.1.4**
* **New logo**: a Class 377 cab in Southern green on a navy badge - in the window header, the taskbar and the exe.
* **Mileage flags** in stats pack comparisons (on by default): any train, unit or formation mileage that goes up by more than **10 miles** (the threshold can be changed) is highlighted in red on its tab and listed under *Mileage increases* on the *Differences* tab. A new row with more than that mileage counts as an increase. Vehicle miles aren't flagged, because they are unit miles times the cars.
* **Clearer default names**:
  * CWN comparisons: today's date and the two CWNs, shortened - e.g. `19-11-2026 DEC26 Proof 1 vs Proof 2` (words such as *CWN* and copy numbers are left out, and a shared start is shown once). Adding a new round to an earlier comparison uses its newest side, e.g. `P2 vs P3`.
  * Stats packs: `Stats pack for DEC26` (the timetable, from the TRENT print's start dates; a single-day pack adds the day, e.g. `Stats pack for DEC26 WO`).
  * Stats pack comparisons: `DEC26 vs MAY27`; when both are the same timetable, the shortened file names.
  * Each tab shows the name it will use under the *Output name* box.
* The window opens at a size that shows everything, and each tab scrolls if the window (or screen) is too small, so nothing can be cut off.
* Clearer *Differences* tab: rows are named the way they appear on the tab (e.g. `1A02BI / 05:40:00`, diagram `1` rather than `1.0`), and the TRACS-RS "None" column group is no longer shown in column names.
* More robust: damaged or hand-edited settings files are ignored instead of stopping the app; output names are kept short enough for Windows' path limit.
* **Dark mode**: a *Theme* setting (now in the *Options* menu) - *Follow Windows* (default, and it keeps following Windows if you switch), *Light* or *Dark*. Dark mode also darkens the Windows title bar.
* **Comparisons**: the *Differences* tab now starts with a **summary of key figures** (miles, time, trains, diagrams, units and vehicles - original, updated and the change) and the number of differences per tab. New options **Changed tabs only** and **Changed rows only** cut large comparisons down to what changed.
* **CWN Compare**: new option (on by default) to ignore differences only in spacing or punctuation in destinations, routing and notes, e.g. `(via  Redhill.)` vs `(via Redhill)`. Capital letters were already ignored; times, platforms, headcodes and units are always compared exactly.
* **Recent files**: every file box has a drop-down of the last files used.
* **Open when finished**: tick to open the output automatically when a run finishes (both tabs).
* Small fixes: a zero change shows as `0`, and an unknown figure as `???`, in comparisons.

**2.1.3**
* Stats packs are written faster (a full week about 20% quicker): each cell is formatted and measured for its column width in a single pass.
* The fleet data is read once per session and again only when the file changes (e.g. after *Edit fleet data*), instead of on every refresh and run.
* CWN Compare tab: the run log stays visible at the smallest window size and now scrolls; the explanation of the change-type columns moved into tooltips on the column headings.
* Messages that referred to the old app name now refer to Rolling Stock Tools.

**2.1.2**
* The app window opens faster: the Excel library and the comparison engine are loaded the first time they are needed, not at start-up (importing the window now takes about 0.06 s instead of 0.7 s).
* The app reopens on the tab you used last. **F5** or **Ctrl+Enter** runs the current tab, the cursor shows when the app is busy, and closing the window during a run asks first.
* The stats pack layout data is about four times smaller (each cell style is stored once), with identical output.
* Tidier code: unused functions, fields and settings removed; the two stats pack comparisons share one routine.

**2.1.1**
* Fixed: formations showing `?` (e.g. `377/4+?`). TRENT lists coupled units by diagram number only, and the app assumed they were from the same depot, so a BI unit coupled to a Selhurst one (e.g. SU312, a 377/3) was not found. Coupled diagrams are now matched across all depots (preferring the unit that works the same train at the same time), and diagrams running on from another day are found too. Car counts and formation lengths for those trains, and the vehicle counts at stops, are now correct as well.

**2.1.0**
* **TLGN** is now depots **HE and TB** (SNGX stays BI, SU and SL). A diagram from any other depot counts under the operator of its stock, or *Other*.
* The TLGN stock (**379/0, 387/1, 700/0, 700/1, 717/0**) is in the fleet data with its operator, and the fleet tick boxes are grouped by operator. Ticking an operator ticks its fleets, and fleets not in the TRENT print are greyed out.
* The fleet data has a new **Operator** column and adds missing power types and unit lengths (387/1, 377/7, 700/0, 700/1, 717/0). Your own copy is upgraded automatically, it still loads if Excel re-saved it in Windows encoding, and the built-in table is used if your copy can't be read.
* **Drag and drop** now works on the Stats Pack tab (it never registered before): drop files on a box or anywhere on the tab, and each goes to the right box. Dropping works anywhere on the CWN Compare tab too.
* Days missing from the chosen TRENT print or XML are shown as soon as the files are chosen. Settings are remembered between sessions. The Run button names what it will do, the log scrolls and is colour-coded, the time taken is shown, and options that don't apply to the chosen mode are greyed out.
* Each file is read once: choosing it reads it in the background, and *Run* reuses that.
* Draft (provisional) trains in the XML are used before LTP and after STP.
* Long labels wrap properly at the smallest window size.

**2.01**
* Trains are now matched between the TRENT print and the XML far more reliably, so the "not found in the XML" warning only appears for real differences:
  * times a minute or two apart (TRENT rounds seconds and can show public times) are matched;
  * depot moves where TRENT and Attune use different TIPLOCs (e.g. Littlehampton) are matched on time;
  * a train that carries on after a reverse, stable, wash or CET line is kept as one move, and a line without a time no longer hides the arrival time;
  * TRENT note lines such as `*(Hand Bash Then via WM)*` are no longer read as locations;
  * only trains on the selected diagrams are reported, and a day missing from the XML is reported once rather than train by train.
* A reversal no longer splits a train into two Formation Data parts.
* Output: data cells no longer wrap onto two lines. Columns are widened to fit their contents and headings, and each input file has its own row on the Glossary.
* New output choice: **totals only**, as well as **totals + every day's tabs** and **a workbook for each day**.
* Comparing two stats pack files is about twice as fast; writing packs is faster.
* Fixed: asking for a combination with no diagrams now gives a clear message.

**2.00**
* Renamed to **Rolling Stock Tools**. CWN Compare is unchanged and is now the first tab.
* New **Stats Pack** tab: builds the rolling stock stats pack from an Attune XML and the TRENT VehicleLayout29 print, for any combination of days, operators (SNGX / TLGN) and fleets, as one merged workbook or a file per day. Compares two plans or two stats packs, highlighting every difference.
* Command-line stats packs (`TrainPlanningTools.exe statspack ...`).
* Checks that each TRENT diagram's service miles add up to its printed mileage total, and warns if part of the print could not be read.
* Settings from CWN Compare 1.x are read once and then saved in the new `RollingStockTools` folder.

**1.06**
* Fixed: with links between tabs off (the default), struck-through re-inserted rows and old/new values in former link cells could still show link styling (blue underline). Links are now removed before any highlighting is written.
* Next-day working lines with a space before the day code (e.g. `06+16 MO`) are now recognised correctly. Only real day codes are treated as days, so a word after a time is never mistaken for one.
* Faster and tidier code: each train's sort time and each tab's train lookup are worked out once instead of repeatedly, and removed trains are placed without re-scanning the tab. More regression tests were added.

**1.05**
* Fixed: when several day variants of a train (e.g. MO, TO, WO, ThO) were merged into one entry with the same change, the old value was shown struck through once per variant (e.g. platform `7` four times above `6`). The change is now reported once, and the old value appears once.

**1.04**
* **Day variants are matched to their own variant.** A MO entry is compared with the MO entry, FO with FO, and so on. This works even when the variants are listed in a different order, and for berthing entries whose variant only shows in the next-day working day code. Labels show the variant, e.g. *"2C02BT (FO)"*.
* **Day-of-week-only differences in next-day berthing are no longer flagged.** For example, `Berth BI150 08+56SO` becoming `08+56SuO` after day variants were re-ordered. A different road or time is still flagged.
* **The output CWN opens much faster in Excel.** The ~76,000 clickable headcode links between tabs are left out by default; the headcode text stays, shown as normal text. Tick *Keep links between tabs* (or use `--keep-links`) to keep them. Rows also carry the "spans" loading hint that Excel writes in its own files. The full output is now 1.65 MB, against 2.7 MB for the source CWN.
* **The exe is about 40% smaller** (9.7 MB, down from 16.1 MB), with no loss of functionality.

**1.03**
* Next-day workings and berth lines (e.g. `Berth BI149 06+10MO (2)`) are compared as a set for each train. Lines in a different order, units swapping between lines, and day letters written in another order (e.g. `FThO` vs `ThFO`) are no longer highlighted. Only a real change is flagged, such as a different road, next departure time or days, or a working added or removed.
* Days variants: when a split or merge happens (e.g. SX becoming FSX + FO, or the reverse), a variant whose details differ is highlighted and labelled with its days, e.g. *"2C02BT (former FO variant): Time changed…"*. An identical split or merge is not highlighted.
* About a third faster: the two CWNs are read at the same time, and parsing is roughly 5× faster. "Add new comparisons" no longer needs to load the earlier comparison file at all.
* More robust: a tab that can't be read is skipped with a warning instead of stopping the run. Unexpected errors are saved to `%LOCALAPPDATA%\CWNCompare\error.log`. Clearer messages are shown when an output file is open in Excel or a folder is read-only.

**1.02**
* Output CWNs open much faster in Excel. Text is stored in a shared-string table like Excel's own files, the forced recalculation on open has been removed, and the hidden comparison data is about 9× smaller. The full output is now smaller than the source CWN.
* The exe has an icon and publisher/version details, is built to avoid false antivirus alerts, and supports automatic code signing.

**1.01**
* Drag and drop files onto the app.
* Diagram (DIAG) changes are no longer checked or highlighted.
* A days-only change highlights just the DAYS cell, with no old value.
* Day splits and merges (e.g. SX becoming FSX + FO) are not treated as new or modified trains.
* Old values are shown struck through on their own line above the new value, in the sheet's own formatting. Times are always shown as `HH.MM`, or `HH+MM` for ECS moves.
* Fixed Excel asking to repair the output file.
* Links between tabs are kept pointing at the right rows.

**1.0.0**
* First release.

## Command line (optional)

```
TrainPlanningTools.exe --original OLD.xlsx --updated NEW.xlsx [--acwn] [--name NAME] [--out FOLDER]
               [--colour FFFF00] [--highlight-only] [--exclude PLATFORM,BERTHING] [--no-report] [--keep-links]
               [--exact-text] [--report-format xlsx|pdf|docx]
TrainPlanningTools.exe --previous EARLIER_COMPARISON.xlsx --updated NEWEST.xlsx --colour 92D050
TrainPlanningTools.exe --original OLD.xlsx --updated NEW.xlsx --days MO,FO        (Monday and Friday trains only)
TrainPlanningTools.exe reorder CWN.xlsx [--by-time] [--merge [--merge-diagrams] [--merge-berths [--merge-berth-diagrams]]] [--name NAME] [--out FOLDER]    (day variants in order)

TrainPlanningTools.exe statspack --xml PLAN.xml --trent VehicleLayout29.docx [--days MO,TO,WO] [--operators SNGX,TLGN]
               [--fleets 377/4,387/3] [--output totals_days|totals|days] [--name NAME] [--out FOLDER]
TrainPlanningTools.exe statspack --xml NEW.xml --trent NEW.docx --old-xml OLD.xml --old-trent OLD.docx
TrainPlanningTools.exe statspack --xml PLAN.xml --trent VL29.docx --capacity-group 1W
               [--capacity-corridor NAME --corridor-direction forward|reverse|both]
               [--capacity-from STATION --capacity-to STATION] [--no-seating] [--no-standing]
               [--between 07:00-10:00 --at "London Victoria" --direction arriving] [--per-day]
               (capacity reports; the older --seats-group / --seats-corridor / --seats-from / --seats-to still work)
TrainPlanningTools.exe statspack --old-pack OLD.xlsx --new-pack NEW.xlsx
               [--no-summary] [--changed-tabs-only] [--changed-rows-only] [--flag-miles 10] [--format xlsx|pdf|docx]
TrainPlanningTools.exe statspack --xml PLAN.xml --trent VehicleLayout29.docx --unit-reports washes,cets,depots,captive,fuel [--possible every|over|off]
TrainPlanningTools.exe statspack --trent "TLGN_SX.docx;TLGN_SO.docx;TLGN_SU.docx" --unit-reports washes,depots,captive   (no XML needed)
               [--unit-period week|days|timetable] [--format xlsx|pdf|docx]

TrainPlanningTools.exe timetable --gtr GTR.xlsx --nr NR.xlsx [--format xlsx|pdf|docx] [--name NAME] [--out FOLDER]
TrainPlanningTools.exe timetable --prints OLD.pdf [OLD2.docx ...] --vs NEW.pdf [NEW2.docx ...]
TrainPlanningTools.exe timetable --lists OLD.xlsx --vs NEW.xlsx
TrainPlanningTools.exe timetable --base-prints PRINT.pdf [PRINT2.pdf ...] --check TIMETABLE.xlsx
TrainPlanningTools.exe timetable --base-list ATTUNE_LIST.xlsx --check TIMETABLE.xlsx
TrainPlanningTools.exe timetable --prints OLD.pdf --vs NEW.pdf --passenger-only
TrainPlanningTools.exe timetable --s4 OLD_S4.pdf [...] --vs-s4 NEW_S4.pdf [...]       (two sets of Section 4 documents)
TrainPlanningTools.exe timetable --tpr OLD_TPR.pdf [...] --vs-tpr NEW_TPR.pdf [...]   (two sets of TPRs)
TrainPlanningTools.exe section4 --xml PLAN.xml [--pdf SECTION4.pdf ...] [--vpt OURS.vpt] [--other-vpt OTHER.vpt|F3.pdf ...]
               [--out FOLDER] [--name NAME] [--format xlsx|pdf|docx]                   (Section 4 check)
TrainPlanningTools.exe timetable --s4-check PLAN.xml [--s4 SECTION4.pdf ...]           (the same, older form)
TrainPlanningTools.exe stationbook --xml PLAN.xml --station "London Kings Cross" [--book-operator TLGN|SNGX|GTR]
               [--merge OTHER_OPERATOR.xml|.vpt|F3.pdf ...] [--other-operators XC,SE]
TrainPlanningTools.exe berthing --xml LTP.xml [STP.xml] [--layout CHART.xlsx] [--counts] [--no-notes] [--issue "Proof 2"]
               [--name NAME] [--out FOLDER]                                         (make a berthing chart)
TrainPlanningTools.exe berthing --chart CHART.xlsx --original OLD.xml --updated NEW.xml [--colour Green|RRGGBB]
               [--issue "Proof 3"] [--counts]                                        (add a round of changes)
TrainPlanningTools.exe berthing --compare OLD_CHART.xlsx NEW_CHART.xlsx [--colour Yellow|RRGGBB]  (compare two charts)
TrainPlanningTools.exe workings-berthing --workings WORKINGS.xlsx [--xml PLAN.xml ...] [--out FOLDER] [--name NAME]   (berthing arrangements for platform workings)
TrainPlanningTools.exe --original OLD_WORKINGS.xlsx --updated NEW_WORKINGS.xlsx    (platform workings are compared like CWNs)
```

Option combinations that would be ignored are refused before any file is read (for example `--acwn` with `--highlight-only`, an unknown `--exclude` category, `berthing --compare` with `--layout`, `--old-pack` with `--xml`, or `--name` with several stations), so a script never silently gets a different output from the one asked for. A run that fails exits with code 1 and an `ERROR:` line.

## For developers

* Source code is in `cwn_compare/`:
  * `model.py` parses CWN tabs into train entries, driven by the column headings (platform workings too, with the berthing section kept apart from the trains).
  * `workings_berthing.py` makes the berthing arrangements of platform workings.
  * `compare.py` matches trains and classifies changes.
  * `writer.py` highlights the output, adds struck-through values and builds the ACWN.
  * `report.py` builds the change report.
  * `meta.py` stores the hidden data used for cumulative rounds.
  * `gui.py` is the desktop interface (the window and the Stock Tools tab).
* The Stats Pack is in `rstools/statspack/`:
  * `trent.py` reads the TRENT VehicleLayout29 and TLGN unit diagram prints, `attune.py` the Attune XML.
  * `model.py` joins them into diagrams, trains and formation parts for one day.
  * `stats.py` builds each tab's rows (and the weekly totals), `xlsxw.py` writes the workbook using `layout.json` (the TRACS-RS layout and styles).
  * `compare.py` compares packs and reads packs back from Excel; `engine.py` runs each mode; `gui_tab.py` is the Stats Pack tab.
  * `fleet_default.csv` is the built-in fleet table.
* The Live View is in `rstools/live/`: `adapters.py` turns each comparison into items (one per train / row), `gui_tab.py` is the tab, `popout.py` moves it into its own window and back (Tk's `wm manage` / `wm forget` on the plain frame holding it) and keeps the window's place on a screen. CWN days are in `cwn_compare/days.py`.
* **Berthing charts** are in `rstools/berthing/`: they show where every unit berths each night, made from Attune XML unit diagrams in the layout of an existing chart (or the built-in one).
  * `xmlread.py` reads the parts of the XML a chart needs (train platforms, unit diagrams); `stays.py` works out each unit's overnight stay (the end of one diagram to the start of the next);
  * `mapping.py` is the berth list (sheet, berth label, TIPLOC, platform / road codes; `berth_locations_default.csv`); `layout.py` reads a chart (cover, berths, capacities, notes, units) and holds the built-in layout (`default_layout.json.gz`, remade with `python -m rstools.berthing.layout CHART.xlsx`);
  * `chart.py` puts the stays on the chart's rows; `writer.py` writes the workbook; `compare.py` compares two charts cell by cell (`diff()` returns `(changes, marked)`: a `Change` per difference - sheet, berth, column, kind *Changed* / *Added* / *Removed*, old and new text - and the rows to highlight) and carries earlier highlight colours; `engine.py` runs the make / add a round / compare modes.
  * Tests: `tests/test_berthing.py` (synthetic XMLs and charts: making, updating, comparing and the built-in layout), the Live View berthing tests in `tests/test_live.py` (changed, added, removed and unchanged cells) and the berthing smoke tests of the exe.
* Shared helpers in `rstools/`: `attune_xml.py` (walking an Attune XML safely, times, plan types, location names; used by the Stats Pack, station book and berthing readers), `days.py` (day names and codes), `clock.py` (times as text), `filecache.py` (one thread-safe store of files already read, kept while unchanged), `isolate.py` (PDFium runs in a helper process), `cancel.py` (the Stop button), `xlsave.py` (saving workbooks so Excel opens them quickly; shared fills), `fsutil.py` (output folders, unique names, atomic writes, `save_output`), `naming.py` (output names), `stationbook.py`, `docexport.py` (PDF and Word outputs) and `dropping.py` (drag and drop).
* Parser safety is central: `rstools/limits.py` holds every input size limit (overridable in `limits.json`), and `rstools/safexml.py` checks XML files and Office XML parts before they are parsed. `rstools/errorlog.py` writes, redacts and exports the error log.
* The Timing Tools is in `rstools/timetable/`: `parse.py` reads the timetable grids, `compare.py` matches trains and finds issues, `output.py` fills `template.xlsx`, `prints.py` / `attune_print.py` and `trainlist.py` handle train prints and Attune lists, `vpt.py` Attune VPT exports, `base.py` turns a print or list into the reference timetable, `section4.py` / `s4remarks.py` / `s4lines.py` / `s4compare.py` the Section 4 check and comparison, `tpr.py` / `tprcompare.py` the TPRs, `doccompare.py` the document comparison output, `pdfgrid.py` / `pdfmark.py` read PDF tables and highlight PDFs, `xlstyle.py` is the shared report look (headings, filters, page set-up), `engine.py` runs them and `gui_tab.py` is the tab.
* Run from source with `pip install -r requirements.txt`, then `python TrainPlanningTools.py`.
* **Checks** (all run in CI, and all must pass before finishing a change), with the pinned packages from `packaging/build-requirements.txt` (`pip install --no-deps -r packaging/build-requirements.txt`):
  * lint: `ruff check .`
  * type-check: `mypy` (settings in `pyproject.toml`: Python 3.14, Windows)
  * tests: `python -m pytest -q tests`. They generate synthetic CWNs, TRENT prints, XML, VPTs and PDFs, so no real data is needed. The window tests need a display (on Linux, run under `xvfb-run`).
  * coverage: `python -m pytest -q tests --cov --cov-report=term-missing` (for `cwn_compare` and `rstools`; the run fails under the `fail_under` floor in `pyproject.toml`, 75%; raise it as coverage grows).
  * dependency audit: `pip install -r packaging/audit-requirements.txt`, then `pip-audit --strict --disable-pip --no-deps -r packaging/build-requirements.txt`.
* **CI** (`.github/workflows/build-windows.yml`) runs separate jobs: **lint** and **typecheck** (Ubuntu), **test** with coverage (Windows, Python 3.14.6; `coverage.xml` is attached to the run) and **audit**; only when all four pass does **build** make the exe, run the smoke tests, make the SBOM and checksums and release; then **promote** merges into `main`. `.github/workflows/codeql.yml` runs **CodeQL** static analysis (security queries) on every push, pull request and weekly; results are under the repository's *Security* tab.
* The Windows exe is built by `.github/workflows/build-windows.yml` on every push, using PyInstaller and `packaging/TrainPlanningTools.spec`. The spec explains what is left out to keep the exe small. To build it locally on Windows, run `build_windows.bat` (needs Python 3.14 installed for the current user): it makes a clean virtual environment with the pinned packages, runs lint, type-check, the tests with coverage, builds the exe, runs smoke tests of the built exe (every subcommand and major mode: CWN comparisons, stats packs and unit / capacity reports, station books, timetable and train print checks, Section 4 and TPR comparisons, the Section 4 check, VPT comparison, berthing charts, day variants in order and `selftest`) and makes and checks the SBOM. It runs the same list of smoke tests as the CI build (every subcommand and major mode, including `selftest`). A new subcommand or mode needs a smoke test in both.
* **Release files and verification.** Each release has `TrainPlanningTools.exe`, `TrainPlanningTools-portable.zip`, **`TrainPlanningTools.cdx.json`** (a CycloneDX 1.6 SBOM made by `packaging/make_sbom.py`: the app, Python and every runtime package pinned in the `# the app` section of `build-requirements.txt`, with `pkg:pypi` purls; `packaging/check_sbom.py` fails the build if any pin is missing or differs, and `tests/test_release.py` checks the same) and **`SHA256SUMS.txt`** (SHA-256 of the exe, zip and SBOM; check one with `Get-FileHash TrainPlanningTools.exe`). Where the repository's plan supports it, a **build provenance attestation** is made for the exe, zip and SBOM (`gh attestation verify TrainPlanningTools.exe --repo OWNER/REPO`); where it does not, that step is skipped with a warning. Nothing from the data folder, settings, tokens or planning files is packaged: the spec bundles only the app's own assets under `rstools/`, and `tests/test_release.py` fails if any other kind of file (XML, workbooks, Word, PDF, VPT, logs) appears there.
* **Automatic merge to main and release.** Every push builds the portable exe (lint, type-check, tests, exe, smoke tests; the exe and zip are attached to the run as an artifact). When a `claude/**` branch builds green, the workflow's `promote` job merges it into `main` (a fast-forward, or a merge commit if `main` has moved on; a conflict stops it with a message), then builds `main` and publishes the portable exe and zip as a GitHub release `vX.Y.Z`. A version is released once: bump `__version__` in `cwn_compare/__init__.py` for a new release.
  * It needs **Settings > Actions > General > Workflow permissions** to allow GitHub Actions to write to the repository (*Read and write permissions*), and **no branch protection rule on `main`** that blocks pushes (or a rule that lets GitHub Actions bypass it).
  * GitHub's own token cannot change files in `.github/workflows`, so a change to the workflow itself must be merged by hand (a pull request) once. To lift that limit and have the push to `main` start the build by itself, add a repository secret **`AUTO_MERGE_TOKEN`**: a fine-grained personal access token for this repository with *Contents* and *Workflows* read and write.
* Real CWN workbooks, TRENT prints and XML exports are git-ignored, so they are never committed.
