<img src="packaging/logo.png" alt="Train Planning Tools logo" width="96" align="right">

# Train Planning Tools

A portable Windows desktop app for GTR train planning (formerly *Rolling Stock Tools* and *CWN Compare*). It has four tabs:

* **Stock Tools** compares two **Carriage Working Notices (CWNs)**, puts a multi-day CWN's day variants in order ([see below](#putting-day-variants-in-order)) and makes **TRACS-RS style station working books** from an Attune XML ([see below](#station-working-book-tracs-rs-layout)). A comparison produces:
  1. **A comparison CWN.** This is the updated CWN with every amendment highlighted in a colour you choose. Tabs that contain changes are highlighted too.
  2. **A change report.** This is a separate Excel workbook summarising every change by category, by location tab and by train.
* **Stats Pack** builds the rolling stock stats pack (the same tabs and figures as the TRACS-RS stats pack), **unit reports** (washes and CETs, depot returns and swaps, captive units, the 171 fuel check) and **capacity reports** from an Attune diagram XML and the TRENT unit diagram prints (SNGX and TLGN). It can also compare two plans, or two stats packs, to show the mileage and other effects of a new plan. See [Stats Pack](#stats-pack).
* **Timing Tools** checks a timetable against the Network Rail timetable, Attune **train prints** or an Attune **train list** (each as the reference) and writes the approved *Consolidated TT Comparison* workbook. It also compares two sets of train prints (PDF or Word) and two Attune train list exports (Excel). See [Timing Tools](#timetable-comparison).
* **Live View** shows any of these comparisons inside the app, train by train, and refreshes as you save the files. See [Live View](#live-view).

## Running it (no admin rights needed)

1. Download `TrainPlanningTools.exe` (or `TrainPlanningTools-portable.zip`, which also contains this guide) from the latest release on the [Releases](https://github.com/Albinoboy64/Train-Planning-Tools/releases) page.
2. Save `TrainPlanningTools.exe` anywhere you can write to, such as your Desktop, Documents or a network drive.
3. Double-click it. Nothing is installed, and no admin rights or Python are needed.

### "Windows protected your PC" / unknown publisher

Windows shows this warning for any downloaded program that isn't **digitally signed** with a code-signing certificate. The app itself can't switch the warning off. The exe carries its name, version, publisher ("GTR Train Planning") and icon in *Properties → Details*, and its start-up code is built specially to avoid false antivirus alerts. The publisher only shows as verified once the exe is signed.

Updates installed with *Options > Check for updates* never show this warning: the app downloads them itself, so they don't carry the "downloaded from the internet" mark. Only the first download from the browser does.

Ways to stop the warning, from quickest to most complete:

1. **Unblock it once.** Right-click `TrainPlanningTools.exe` (or the zip, *before* extracting it), choose **Properties**, tick **Unblock**, then **OK**. Windows won't warn again for that copy.
2. **Run it from a GTR network share.** Programs on an internal file share don't carry the "downloaded from the internet" mark, so SmartScreen doesn't prompt. Unblock it once, copy it to the shared drive, and the team runs it from there.
3. **Ask IT to allow it.** IT can publish the exe through Company Portal / Intune, or allow it by its file hash or publisher. Each release's notes on GitHub give the exe's SHA-256 hash for this.
4. **Sign it (removes "unknown publisher" for good).** Get a code-signing certificate, either from GTR/Govia IT or from a public certificate authority such as DigiCert or Sectigo. Then add two repository secrets on GitHub: `SIGNING_CERT_PFX_BASE64` (the `.pfx` file, base64-encoded) and `SIGNING_CERT_PASSWORD`. Every build is then signed and time-stamped automatically. To base64-encode the certificate in PowerShell, run
   `[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx")) | Set-Clipboard`.
   A certificate from an internal GTR certificate authority is trusted on GTR-managed PCs. A public one is trusted everywhere. A brand-new public certificate can still show a SmartScreen notice until it builds up reputation.

Your option choices, theme, recent files, rule sets, fleet data and the error log are kept in a **TrainPlanningTools-data** folder beside the exe, so the app is portable: move or copy the exe and that folder together. If the exe's folder cannot be written to, they are kept in `%LOCALAPPDATA%\TrainPlanningTools` instead (nothing is written to the registry). The first time the data folder is made, settings already saved in `%LOCALAPPDATA%` are copied into it. *Options > Open settings folder* shows where they are. Press **F5** or **Ctrl+Enter** to run the current tab. *Options > Theme* switches between *Follow Windows*, *Light*, *Dark* and *High contrast*.

**Accessibility.** *Options > Text size* makes all text in the app *Small*, *Normal*, *Large* or *Extra large* (also **Ctrl +**, **Ctrl -** and **Ctrl 0**); boxes, columns and tables grow with it. *High contrast* is white text on black with yellow buttons and focus outlines and cyan selections (the Windows high-contrast colours), and *Follow Windows* switches to it automatically when Windows high-contrast mode is on. Both only change the app window, not the outputs. The app uses the Windows fonts: Segoe UI Variable (Windows 11) or Segoe UI for text and Cascadia Mono or Consolas for logs.

### Updates

*Options > Check for updates...* finds the latest release, shows what's new and installs it in place (the app closes and reopens on the new version). The repository is public, so no account or token is needed. (For a private copy of the repository, add a read-only access token once in *Options > GitHub access token...*: on GitHub go to *Settings > Developer settings > Personal access tokens > Fine-grained tokens*, give it access to that repository only with *Contents: Read-only*, and paste it in. The token is stored encrypted for your Windows login (DPAPI) and is only ever sent to GitHub.)

**Upgrading from 3.11.0 or earlier:** those versions look for updates in the app's previous repository, which is now private, so they report that GitHub did not allow access. Download **TrainPlanningTools.exe** from this repository's [Releases](https://github.com/Albinoboy64/Train-Planning-Tools/releases) once and replace the old exe; your settings are kept, and updates work from the app again after that.

## Using the app (Stock Tools tab)

| Step | What to do |
|---|---|
| 1. CWN comparison | **Compare two CWNs**, **Add a new round to an earlier comparison CWN** or **Compare two folders of CWNs (batch)**, then the **Original CWN** and the **Updated CWN** (in the same section), either with *Browse* or by **dragging and dropping** the files onto this section. If you drop both files at once, the older file becomes the original. Use *Swap* if they end up the wrong way round. In "add a new round" mode, the first file is a comparison CWN that this app made earlier. The **Utilities** section underneath has the one-file tools: **Put each train's day variants in order (one CWN)** ([see below](#putting-day-variants-in-order)) and the **Station Working Book** ([see below](#station-working-book-tracs-rs-layout)), with their own box and drop area. |
| 2. Output | **Full CWN with changes highlighted**, or **ACWN** (amended trains only, with unchanged trains and unchanged tabs removed). Pick the highlight colour, the output folder and the output name. If you leave the name blank, today's date and the two CWN names are used, e.g. `19-11-2026 Proof 1 vs Proof 2`. *Keep links between tabs* keeps the clickable headcode links; it's off by default because they make the file much slower to open in Excel. |
| 3. Changes to include | For each change type, choose whether it is **shown in the CWN**, whether the **previous value / note** is shown, and whether it is **included in the report** |
| 4. Run | Press **Run comparison**, then use *Open output CWN*, *Open report* or *Open folder* |

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
* **Show previous value / note.** Untick to only highlight the new data. No old values, struck-through rows or notes are added. The *Highlight only* button unticks this for every type.
* **Notes** explaining a change (e.g. *Amended: previously formed from 1W08BT*) go in a **Change notes** column just to the right of the CWN, on the row of the change they explain.
* Only cells that hold text are coloured. A new or re-inserted train is not coloured across its empty cells.
* **Include in report.** Untick to strip that change type out of the report entirely.

### Comparing two folders of CWNs (batch)

Choose **Compare two folders of CWNs (batch)** under *1. CWN comparison* (or drop two folders on the tab), then choose the folder of original CWNs and the folder of updated CWNs.
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

A multi-day CWN often lists the day variants of the same train (for example 1A23 MO, 1A23 TWThO and 1A23 FO) in no particular order. Choose **Put each train's day variants in order (one CWN)** under *Utilities*, choose the CWN (or drop it on Utilities) and press **Put variants in order**. A copy is saved, e.g. `Proof 2 (variants in day order).xlsx`; the CWN itself is not touched.
* **By day** (default): the MO variant first, then the variants in day order through to FO, then SO and Su. A variant that runs on fewer days comes first when two start on the same day (MO before MTWThO).
* **By departure time**: the earliest-departing variant first (an FO train at 05.30 before an MO train at 06.10), then day order for variants at the same time.
* Only the variants of the same train swap places, within the rows they already used, so every other train stays exactly where it was. Rows move whole: values, formatting, row heights, notes and coupled-unit rows. Links from other tabs are re-pointed to the rows' new positions. Nothing is changed or removed.
* A tab with merged cells or formulas among its trains is left as it was (moving rows could break them), and the log says so.
* Put the variants in order before comparing if you want the comparison CWN to follow the same order.

### Station Working Book (TRACS-RS layout)

Choose **Station Working Book (TRACS-RS layout, from an Attune XML)** under *Utilities*, then the Attune XML (in the Utilities box, or drop it there), the **station**, and optionally:
* **Platforms**, e.g. `10-15` for the London Bridge low level book, or `1, 2, 4A`.
* **Operator** and **Timetable** for the page header and file name, e.g. *GTR(TLGN)* and *Dec23* (the timetable is filled in from the XML), and **Services** for the header, e.g. *Thameslink and Great Northern services only*.
* **Sheet name**, e.g. *London Bridge LL* (default: the station and the operator in brackets, e.g. *London Kings Cross (TLGN)*), and which **sheets**: SX, SO, Su.
* **Several stations** at once: pick a station (and any platforms) and press **Add to list**, or type them separated by `;` with platforms in brackets, e.g. `London Kings Cross; London Bridge [10-15]; Cambridge`. Each station gets its own book (named after the station), made on several CPU cores at once; a station that cannot be found is reported and the others are still made. Command line: `--station "London Kings Cross; Cambridge"`.

The book has the TRACS-RS layout: one row per train leaving the station, in departure order (trips after midnight at the end of the day, as in TRACS-RS), with Calibri 13, the blue heading row repeated on each page, row heights fitted to the text, the page header and *page/pages* footer:

| Column | What it shows |
|---|---|
| Train ID / Origin Time / Station of Origin / Arrival Time | The train(s) the units arrive on (in their order in the departing train, front first), *Berth* when a unit starts the day in the platform, and *RP* / *FP* when the departing train is the rear / front portion of a train that divides here. For a train calling here, its own origin and arrival. |
| Train ID (Stock) | The departing headcode and one line per unit, front first, e.g. `(387/1)` |
| Origin Time, Origin, Destination | Of the departing train |
| Departure Time (Platform) | e.g. `05 02 (9)` |
| Calling points | Every later passenger stop with its public arrival time, the destination in capitals; *Empty to ...* for empty stock; *The train divides at Purley / The front 5 coaches call at: ... / The rear 5 coaches call at: ...*; and *Runs Monday and Friday only* (etc.) where a row is not the same on every day of the sheet. |

Passenger trains (classes 1, 2 and 9) show public times as `HH MM`; other trains show working times as `HH+MM`. Checked against the TRACS-RS London Bridge 10-15 book from the same timetable: every train's inward working, attaching and dividing trains, stock, berthing and *RP* / *FP* portions came out in the same form; the differences were from the example being an earlier version of that timetable (a minute here, a platform there) and TRACS-RS's own location names (see below).

**The best input data.** One **Attune diagram XML export of the timetable, including the unit diagrams for every day the book covers** (Monday to Sunday for SX, SO and Su sheets). It holds everything the book needs: every train's times, public times, platforms and stops, and the unit diagrams - which units work each train (front to rear), the train each unit arrives on, where trains attach and divide, and where units stable. Export it from the same plan as the book, with **all operators' trains** you want shown (e.g. EMR at Bedford). The app warns if a day's unit diagrams are missing (the stock and inward workings are blank on those days). Seats and coach counts (for *the front 5 coaches*) come from the fleet data. Locations are named as in the XML; TRACS-RS uses its own location names (e.g. *Selhurst TRSMD* where Attune has *Selhurst T&R.S.M.D*, and sometimes a TIPLOC such as *STWTBS*), so names can differ slightly from older books.

Command line: `stationbook --xml PLAN.xml --station "London Kings Cross" [--platforms 10-15] [--operator "GTR(TLGN)"] [--timetable Dec23] [--services "..."] [--label "..."] [--sheets SX,SO,Su]`.

### Berthing charts

Under *Berthing charts* on the Stock Tools tab (drop XMLs and charts on that box):

* **Make a berthing chart from an Attune XML**: where every unit berths each night at the out-berth platforms and sidings. Choose the **Attune XML** (an export with every day's unit diagrams) and an earlier chart under **Layout from chart**: its sheets, berths, capacities and notes are kept, the units come from the XML, and the old formulas, counting rows (*Start1* ... *Finish1*, *\*4 377\** rows) and damaged formatting are left out. *Issue on cover* (e.g. *Proof 1*) goes on the cover with the XML's dates. A new chart starts without highlights.
* **STP charts**: attach the **STP XML** as well. Each day's STP diagrams replace the LTP ones, and STP trains are shown **in bold on a lavender fill**.
* **Add a round of changes to a berthing chart**: the chart, the **original XML** it was made from and the **updated XML** (for an STP chart, the LTP and STP XMLs separated by `;`). The chart is remade from the updated XML, every cell that differs is filled in the chosen colour, earlier highlights are kept, and a change report lists each change. The cover's *Updates highlighted in ...* line follows the colour.
* **Compare two berthing charts**: every unit or time in the newer chart that differs from the older one is highlighted, with a change report. Spacing slips (`(4 387) 00 45`), the old `L` marker and `12700` / `12 700` are not differences.

Each row is one unit's stay: its arrival in the night's **FINISH** column and its departure in the next **START** column (`02+02` an empty move, `0500` a passenger train), **Berth** on any day it stays put, and **RP** when it leaves as the rear portion of another train, attached to by a unit that moved onto it that day. Coupled units sit on consecutive rows in brackets, front first, with the time on the first row; the latest arrival is at the top. 387/2 (Gatwick Express) are in red, 387/3 (Southern) in green, and Thameslink 700s end `TLK`. The depot sheet (Lovers Walk) lists each unit type's arrivals and departures in time order.

Which XML location each berth is comes from the **berth list** (*Edit berth locations...*): sheet, berth as written on the chart, TIPLOC and the platform or road codes Attune uses (e.g. Brighton *Plat 7* = BRGHTN 7 / 7F, Eastbourne *No 3 Siding* = EBOUSID S3). Units berthing on a platform or road the sheet has no berth for are listed at the bottom of that sheet, and everything that needs checking is on the chart's **Notes** sheet. Command line: `TrainPlanningTools.exe berthing --xml LTP.xml [STP.xml] --layout CHART.xlsx`.

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
| 1. What to do | **Create a stats pack**, **Compare two plans** (an original and an updated XML + TRENT print), or **Compare two stats pack files** |
| 2. Files | Choose the files with *Browse*, or **drag and drop** them onto the boxes or anywhere on the tab: each file goes to the right box by its type (`.xml`, `.docx`, `.xlsx`). Dropping two XMLs or two TRENT prints switches to *Compare two plans*, with the older file as the original; dropping two stats packs switches to *Compare two stats pack files*. |
| 3. Days, operators and fleets | Tick the **diagram days** (MO, TO, WO, ThO, FO, SO, Su), the **operators** and the **fleets**. Days missing from the chosen TRENT print or XML are listed straight away. **SNGX** is diagrams from depots **BI, SU and SL**; **TLGN** is depots **HE and TB** (any other depot counts under the operator of its stock in the fleet data, or *Other*). Each operator has a row of its fleets (SNGX: 171/7, 171/8, 377/x, 387/2, 387/3; TLGN: 379/0, 387/1, 700/0, 700/1, 717/0); ticking an operator ticks its fleets. Fleets that aren't in the TRENT print are greyed out, and MAINT is unticked by default. |
| 4. Output | Choose **one workbook with the totals for the ticked days, then every day's tabs** (`MO Fleet`, `MO Service Miles`...), **one workbook with the totals only**, or **a separate workbook for each day**. A single ticked day always gives a single-day pack laid out like the TRACS-RS one. Leave the name blank for `Stats pack for DEC26` (comparisons: `DEC26 vs MAY27`). |
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

Choose **Unit reports** under *1. What to do*, tick the reports you want, the days, operators and fleets, then **Create unit report** (`Unit report for DEC26`). Run it for the **whole week** (each unit is followed from day to day) or for **each ticked day on its own**.

* **Washes and CETs per unit**: how many WASH, CET and FUEL lines each unit gets across the week, the most diagrams in a row without a wash, and every diagram the unit works (e.g. `MO BI105 > TO BI112 > ...`). A summary by fleet shows the washes per unit and how many units get no wash or no CET. Per day, it lists each diagram's washes and CETs.
* **Depot returns / swaps**: every diagram classed as a **Return** (starts and ends at the same depot, e.g. Lovers Walk to Lovers Walk), a **Swap** (e.g. Lovers Walk to Selhurst), *Leaves depot*, *Back to depot* or *Away from depot*, with a summary per day and a table of depot pairs.
* **Captive units**: units that never start or end a diagram at a depot all week, so they can't get back to one. Per day, it lists the diagrams that neither start nor end at a depot.
* **Fuel check (171s)**: every diesel unit (171/7, 171/8, and any fleet with a diesel power type in the fleet data) followed through the ticked days, checking it is fuelled **at least once every 48 hours**. Each unit shows its fuels, its longest gap between fuels (h:mm, from / to), and *OK*, *Over 48 hours* or *No fuel*; problems are listed first. A fuel's time is the arrival just before the FUEL line in the TRENT print. A unit followed for the whole week is taken to repeat weekly, so the gap from its last fuel to its first fuel the next week counts too; for a unit followed for part of the week, the time before its first fuel and after its last is measured from the start of its first diagram / to the end of its last (*Part week*), so check those across the week boundary. The check always looks across the ticked days, even with *Each ticked day on its own*, and is only as exact as the next-day links (see below).

How units are followed: each diagram's WASH / CET / FUEL lines and start and end locations come from the TRENT print; the **next-day working** of each diagram comes from the note at the end of its unit diagram in the Attune XML (e.g. `BI20 04+29ThO (F)`). For **exact** results the XML must contain the unit diagrams for **every day** you tick. For a day the XML doesn't cover, or a diagram that ends `Stabld`, the unit is matched to a diagram on the same fleet starting where it stabled (same place, then the same depot, then the same station area); those links are shown as `>?` and counted under *Linked by* as *inferred*, and the *Notes* tab says which days were inferred.

Which locations are depots: any location named *T&RSMD*, *TMD*, *EMUD*, *Depot*, *Shed* or *Traincare*, grouped by depot (so every road at Selhurst counts as Selhurst), plus the depot list in **Options > Edit depot list**: add a TIPLOC with its depot name, or leave the depot blank to mark a location as not a depot.

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

Choose **Capacity report: by headcode group, corridor or station to station** under *1. What to do*, with the Attune XML and the TRENT print. Choose the trains in one of three ways:
* **Service group**: a headcode group such as **1F**, **1W** or **2F** (the first two characters of the headcode). The drop-down lists every passenger headcode group in the chosen XML, with its main routes and number of trains, e.g. *1F   Eastbourne - London Victoria; London Victoria - Ore (73 trains)*.
* **Corridor**: one of our main routes (Brighton Main Line, the London approaches via Balham and via Forest Hill, Crystal Palace, Tulse Hill, Sutton and Mole Valley, Epsom Downs, Caterham, Tattenham Corner, the Oxted lines to Uckfield and East Grinstead, Redhill - Tonbridge, the Arun Valley, West and East Coastway, Portsmouth, Littlehampton, Bognor Regis, Seaford, Marshlink and the West London Line; for TLGN the Thameslink Core, Midland Main Line, East Coast Main Line, Kings Cross - Finsbury Park, Cambridge Line, Fen Line, Hertford Loop, Northern City Line, Thameslink via London Bridge, Wimbledon Loop, Catford Loop to Sevenoaks and London Bridge - Rainham), then **one direction or both** in the box underneath, e.g. *Brighton to Southampton Central*. Every passenger train running along the route counts, whatever its headcode; its direction is the order in which it reaches the route's stations.
* **Station to station**: any two stations on the network (every station in the XML where trains stop; type in a box to narrow the list). Counts the trains that stop at the first station and later at the second. Seats are the **smallest** formation between the two, since that limits the journey.

Then:
* **Whole week** gives one row per ticked day, the week total and the average per day; **Each ticked day on its own** leaves out the week figures. Untick days in *3.* to report only some days.
* **Only trains between** two times (24-hour) **arriving at**, **departing** or **arriving or departing** a station, e.g. *07:00 and 10:00, arriving at London Victoria* for the morning peak. For station to station, the times are the departure from the first station. Without it, the whole day is counted.
* **Show: Seating capacity / Standing room**: tick either or both. Seating capacity is First Class, Standard Class and total seats; standing room is the standing capacity; with both ticked, total capacity (seats + standing) is shown too, and the per-hour tab adds up whichever is chosen. All from the fleet data (*Edit fleet data*), added up over every unit in the formation.
* In a time window the formation at that station is used; otherwise the formation with the most seats while the train is on the route (station to station: the smallest between the stations). Empty stock moves are never counted.
* Output (Excel, PDF or Word): **Capacity Summary** (per day, week total and daily average), **Capacity by Hour** (a column per day), **Capacity by Train** (every train with its times, formation and seats) and **Notes** (exactly which trains were counted, and any stations or fleets that could not be found).

**The corridor list.** The XML and TRENT print don't record corridors, so each corridor is a list of its stations **in route order** (which sets the two directions). Check and correct the built-in list under *Options > Edit corridors* (or the button under the seats options); it opens in Excel, and the drop-downs update once you save and close it. If you never edited the list from 3.6 - 3.9, it is replaced by the new one (with the TLGN routes) automatically (the old copy is kept as `groups.csv.old`). Each row has:

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

The tab has two sections. Under **1. Timetable comparison** choose what to compare and its two files (or drag and drop them on that section, or anywhere on the tab: the comparison type and the boxes are picked from the files), then press **Compare** (or F5). Under **Utilities** is the **Section 4 check** with its own boxes: the Attune XML and Network Rail's Section 4 PDF(s) (see [Section 4 check](#section-4-check)). Output can be Excel (default), PDF or Word.

### GTR timetable against the Network Rail timetable

* **Inputs:** the GTR timetable check workbook (sheets such as *OT SNGX TT Checks K - OUT SX*) and the Network Rail timetable workbook (sheets such as *OUT_K_D26_SX_...* with their *_Notes* sheets). If they are chosen the wrong way round the app swaps them and says so.
* **Network Rail is the reference.** Only GTR operators (SN, TL, GX) are compared; other operators (e.g. LO) are counted as out of scope in *Audit Totals*. Only equivalent sections are compared (OUT/RTN x SX/SO/SuO).
* Times are read as HHMM whatever the footnote marks (`0634a`, `06a34`, `a0634`, `05 10`); blank location cells under a station mean the same station; passing / placeholder cells (`.....`, `. .`) are not times; GTR-only extra timings are ignored.
* **Matching** is one-to-one using all the information - times at shared locations (arrival and departure), headcode, calling pattern, start/end and days - never the headcode alone. Confidence 80%+ is a confident match; 50-79.9% is "possible - review" unless the match is unambiguous; below 50% is not a match.
* **Output** (`[NR timetable] Consolidated TT Comparison.xlsx`, e.g. `K_D26 Consolidated TT Comparison.xlsx`) uses the approved template: *Summary* (per section plus an all-sections total), *Issues* (matched trains only: time mismatch, time/location missing, arrival shown instead of departure and vice versa, with whether the rest of the train agrees), *Missing Trains* (whole NR trains missing from GTR, and isolated GTR gaps in an otherwise matched regular pattern), *Headcode Mismatches* (same timings, different headcode), *Service Group Review* (groups such as `9Rxx` when 5 or more trains, otherwise individual headcodes), *Match Audit* (every NR train, its match, confidence and status) and *Audit Totals* (NR timing cells in scope = compared + not compared; never "Complete" while any cell is not compared). Empty sheets say *None identified*.

### Train prints or an Attune train list against a timetable

* **Half minutes**: a timetable that shows half minutes (`0634½`, `0634H` or 30 seconds in an Excel time) is a working timetable, so prints and lists are compared with it **to the half minute** using their working times (passing times included). Times are rounded to whole minutes **only** when one side is a public timetable (Network Rail / passenger) without half minutes: then the half-minute side is rounded the public way (departures down, arrivals up), and the *Notes* say so.
* **Train prints against a timetable**: the reference is one or more Attune **Single Train Report** prints (PDF or Word). Each train's **public** arrival and departure times are checked against the timetable (GTR or Network Rail layout), using exactly the same matching rules, confidence levels and output as timetable against timetable. Passing points, working-only stops (signals, sidings) and empty-stock trains have no public times and are not compared (they are listed in *Audit Totals*). Only times the timetable has a row for are checked, so a table that shows one time at a station is not reported as missing the other.
* **Attune train list against a timetable**: the reference is an Attune train list (heading row found automatically; columns such as *TrainID / SignalID, Days Pattern, Origin Loc, Origin Time, Destination Loc, Destination Time*). A list only has each train's origin departure and destination arrival, so only those two times are checked - use train prints to check every stop. Working half minutes become public times (departures round down, arrivals round up). Empty-stock and other non-passenger trains (headcode class 0, 3-8, or an Attune category starting with E) are left out. Location codes (TIPLOCs) are turned into station names from a built-in list plus every code seen in train prints read on your PC.
* Each train goes into the section(s) its days run in (SX / SO / SuO), in the direction (OUT / RTN) where the timetable has it (or whose table lists its stations in calling order). If the timetable clearly shows a train in another section - for example an after-midnight train on the next day's sheet, with the same headcode and times - it is compared there rather than reported missing, and a note says so.
* Output: `[reference] vs [timetable] Consolidated TT Comparison.xlsx`, with the headings naming the sides (e.g. *Print headcode* / *GTR headcode*).

### Two sets of train prints (PDF or Word)

* Choose one or more files for each side (hold Ctrl in the file window). Each train is found by its heading line (headcode with a UID, or the word *Train* / *Headcode*); a heading repeated on the next page continues the same train. Page numbers, print dates and repeated column headings are ignored.
* Attune *Single Train Report* prints are read column by column (working, passing and public times, dwell, activity, platform, line, allowances and every heading field such as *Days Pattern* or *Timing Load*), so a change is named exactly, e.g. *Public departure time changed* or *Platform changed*. Other print layouts are read from their text.
* Trains are paired by headcode, UID and days (then train ID and days, headcode, days and first time), and compared location by location, so an added or removed call is reported once instead of shifting every line. Reported: trains added / removed, arrival / departure / passing times changed, added or removed, other call details (platform, line, path, activities) and heading details.
* **Side by side, like the timetable comparison**: in the *Live View* and on the report's **Side by Side** sheet, each train is laid out a row per location and time (*Arr* / *Dep* / *Pass*) with both prints' times next to each other, then the print's own details for that call: public times, platform, line, activity codes, dwell and allowances (a value that differs shows as `old → new`). The train's **days run**, train ID, UID, dates, class, power type, timing load and other heading details are at the top. The report's sheet lists every train that changed, was added or was removed.
* **Speed**: Attune *Single Train Report* PDFs are read with PDFium, about ten times quicker than before (thousands of trains in well under a minute), with big files spread over several CPU cores. PDFium places every value by its position on the page, so narrow columns such as the allowances are read exactly; other PDFs are read as before. Scanned (image-only) PDFs cannot be read - save the print from the planning system as PDF or Word.

### Two Attune train list exports (Excel)

* The heading row is found automatically (extra title rows and column order don't matter). Trains are paired by UID, days, STP and start date when there is a UID column, otherwise by headcode, days and origin departure time.
* Every column present in both lists is compared; times compare as HHMM (`05:10`, `0510` and an Excel time are equal) and numbers as numbers. Output: *Summary*, *Changes by Train*, *Trains Added*, *Trains Removed* and *What Was Compared* (which columns were compared and how trains were paired).

### Section 4 check

* **Inputs:** the Attune XML of the timetable, and Network Rail's Engineering Access Statement **Section 4 (Standard Possession Opportunities)** PDFs for the routes it runs on (e.g. *2027 EAS V4 S4 - KS*, *- EC*, *- EMR*). Add several PDFs to the box, or drop them with the XML on the Utilities section. Or add the PDFs once as a **rule set** in *Options > Rules and reference data* and leave the PDF box blank: the rule set in use is checked. The latest rules are on [Network Rail's operational rules page](https://www.networkrail.co.uk/industry-and-commercial/information-for-operators/operational-rules/).
* The PDFs' tables are read from their drawn cells: each section (e.g. *Shepherds Lane Jn and Herne Hill 110.3*), each night (*WEEK END*, *SUN/MON*, *MID WEEK*), each period's windows (e.g. *0140 T-F to 0350 T-F* is 01:40-03:50 on Tuesday to Friday mornings) and what is blocked.
* A train **clashes** when it calls at or passes both ends of a section at a time inside a window, on a day and in a period the possession applies to (only periods the XML's dates cover). Places are matched to the XML by name (Network Rail's and Attune's spellings, e.g. *Victoria Eastern* / *London Victoria*); sections whose places are not in the XML are listed under *Not Checked*.
* The XML has no running lines, so each clash says **Every line blocked** or **Some lines: check the line used**. Where only the Down (or Up) line is blocked, a train is taken as Down when it reaches the first-named place first, and trains the other way are left out. Midweek possessions available only some weeks show it (e.g. *8 weeks a year*).

## Saved settings, notifications and help

* **Save/Load** menu (Alt+S): *Save ... settings as...* stores the current tab's files and options under a name, e.g. *DEC26 Brighton CWN* or *AM peak seats*. Each tab keeps its own list, with as many saved settings as you like. The settings saved for the tab you are on are listed straight under it (click one to load it). Every tab also has a sub-menu listing its saved settings, where each one can be **loaded**, **loaded and run**, **replaced with the current settings**, **renamed** or **deleted** (the files themselves are never touched). If a file has been moved or deleted, the settings are loaded but not run, and the missing files are listed. Settings saved by earlier versions are kept.
* **Notification when a run finishes**: if the app is in the background when a run ends (e.g. you are working in Excel), its taskbar button flashes and a small notice appears in the bottom-right corner of the screen. Click the notice to bring the app to the front. Switch this off in *Options > Notify me when a run finishes in the background*.
* **Help on every control**: rest the mouse on any option, button or box for a short explanation.

## Live View

The **Live View** tab shows any comparison in the app inside the window: CWNs, stats pack plans or files, GTR vs Network Rail timetables, train prints or an Attune list against a timetable, and two sets of train prints or Attune lists.

1. Choose what to compare and the files (or drag them onto the tab), then press **Compare** (F5).
2. Every train (or stats row) is listed on the left. *Show* filters it (differences only, all, changed, issues, added, removed / missing, unchanged, or updated by the last refresh) and *Find* searches it.
3. Click a train to see it side by side with its match on the right, with differences coloured (yellow changed, green added, red removed / missing, orange issue, grey not compared) and described underneath. **Next >** / **< Previous** (F3 / Shift+F3) step through the trains with differences.
   * **Click a row** on the right to highlight it right across, original and updated side by side, with its full values (including any too long for the column) shown in the box underneath.
   * Train prints: the train's details (days run, IDs, dates, class, power type...) sit under a **▼ Train details** heading at the top. Click it (or press Enter on it) to fold them away or show them again; the app remembers your choice. Folded, the heading still turns yellow and says how many details differ.
4. With **Refresh when a file is saved** ticked, the files are watched. Save either one (e.g. after correcting a time in Excel) and the comparison re-runs, usually within a second or two. Only the saved file is read again. The selected train stays selected, and trains changed by the save are marked `*` in bold, with *Show: Updated by the last refresh* listing just those.

**Export...** saves the trains currently listed (with the filter and search applied) to Excel, PDF or Word: an *About* sheet, a *Trains* sheet (each train's result and differences in words) and a *Differences* sheet (each differing call or field, coloured as on screen).

The Live View uses exactly the same reading and matching as the other tabs, so it always agrees with their reports. For CWNs it has the same day tickboxes as the Stock Tools tab. It only reads the files; nothing is written.

## Licence

Train Planning Tools is free software under the [GNU General Public License v3.0](LICENSE): you may use, share and change it under the terms of that licence. It comes with no warranty; always check its results before relying on them.

## Third-party software

Train Planning Tools is built with open-source software (Python, Tcl/Tk, openpyxl, xlrd, pyxlsb, tkinterdnd2, ReportLab, pypdf, pypdfium2 / PDFium, Pillow and PyInstaller), each used under its own licence. The list and licences are under **Help > Third-party software and licences**, and in [`rstools/assets/THIRD_PARTY_NOTICES.txt`](rstools/assets/THIRD_PARTY_NOTICES.txt).

## Version history

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
* **Train print comparison much faster**: see *Speed* under [Two sets of train prints](#two-sets-of-train-prints-pdf-or-word). Pairing thousands of trains is also quicker. Empty-stock trains whose heading has no space before the train ID (`EE5C90BV`) are read.
* **Train prints side by side like the timetable comparison**, with activity codes, platforms, allowances and the train's days run and details at the top, in the Live View and on the report's new **Side by Side** sheet. The timetable comparison in the Live View also shows both trains' days at the top.
* **Half minutes kept**: timetables and Attune prints / lists are compared to the half minute unless one side is a whole-minute public timetable (see *Half minutes* under [Timetable Comparison](#train-prints-or-an-attune-train-list-against-a-timetable)).
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
* **Train prints against a timetable** and **Attune train list against a timetable** (new on the Timetable comparison tab): the print or list is the reference and the timetable is checked by the same rules, into the same template. See [Train prints or an Attune train list against a timetable](#train-prints-or-an-attune-train-list-against-a-timetable).
* The **Options / Help bar** now follows the theme (dark or light), including its drop-down menus.
* Attune **Single Train Report** prints are now read column by column for print-against-print comparisons too, so changes are named precisely. This also fixes two problems with that layout in 3.0.0: trains with the same ID on different days (e.g. FO and FSX) were merged, and heading fields were read as calling points.
* Fewer false positives in every timetable comparison: a station where the other table shows only one of the two times is no longer reported, and a missing arrival is no longer reported as "Departure time shown instead of arrival" when the departure shown is the train's own correct departure.
* More day codes understood (e.g. `TThO`, `WFO`, `MWFX`), and large PDF prints are read on several CPU cores.
* Command line: `timetable --base-prints PRINT.pdf --check TIMETABLE.xlsx` and `timetable --base-list LIST.xlsx --check TIMETABLE.xlsx`.

**3.0.0**
* **Renamed to Train Planning Tools.** Settings, fleet data and the depot list from Rolling Stock Tools are copied across automatically; *Check for updates* in 2.1.5 / 2.1.6 finds this release.
* **New Timetable comparison tab**: GTR timetable against the Network Rail timetable, written into the approved *Consolidated TT Comparison* template (with tidier formatting: borders, coloured results, totals, percentages, print settings); plus **train print** (PDF / Word) and **Attune train list** (Excel) comparisons. See [Timetable comparison](#timetable-comparison).
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
TrainPlanningTools.exe reorder CWN.xlsx [--by-time] [--name NAME] [--out FOLDER]    (day variants in order)

TrainPlanningTools.exe statspack --xml PLAN.xml --trent VehicleLayout29.docx [--days MO,TO,WO] [--operators SNGX,TLGN]
               [--fleets 377/4,387/3] [--output totals_days|totals|days] [--name NAME] [--out FOLDER]
TrainPlanningTools.exe statspack --xml NEW.xml --trent NEW.docx --old-xml OLD.xml --old-trent OLD.docx
TrainPlanningTools.exe statspack --xml PLAN.xml --trent VL29.docx --seats-group 1W
               [--seats-corridor NAME --corridor-direction forward|reverse|both] [--seats-from STATION --seats-to STATION]
               [--between 07:00-10:00 --at "London Victoria" --direction arriving] [--per-day]
TrainPlanningTools.exe statspack --old-pack OLD.xlsx --new-pack NEW.xlsx
               [--no-summary] [--changed-tabs-only] [--changed-rows-only] [--flag-miles 10] [--format xlsx|pdf|docx]
TrainPlanningTools.exe statspack --xml PLAN.xml --trent VehicleLayout29.docx --unit-reports washes,depots,captive,fuel
TrainPlanningTools.exe statspack --trent "TLGN_SX.docx;TLGN_SO.docx;TLGN_SU.docx" --unit-reports washes,depots,captive   (no XML needed)
               [--per-day] [--format xlsx|pdf|docx]

TrainPlanningTools.exe timetable --gtr GTR.xlsx --nr NR.xlsx [--format xlsx|pdf|docx] [--name NAME] [--out FOLDER]
TrainPlanningTools.exe timetable --prints OLD.pdf [OLD2.docx ...] --vs NEW.pdf [NEW2.docx ...]
TrainPlanningTools.exe timetable --lists OLD.xlsx --vs NEW.xlsx
TrainPlanningTools.exe timetable --base-prints PRINT.pdf [PRINT2.pdf ...] --check TIMETABLE.xlsx
TrainPlanningTools.exe timetable --base-list ATTUNE_LIST.xlsx --check TIMETABLE.xlsx
```

## For developers

* Source code is in `cwn_compare/`:
  * `model.py` parses CWN tabs into train entries, driven by the column headings.
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
* The Live View is in `rstools/live/`: `adapters.py` turns each comparison into items (one per train / row), `gui_tab.py` is the tab. CWN days are in `cwn_compare/days.py`.
* The Timing Tools is in `rstools/timetable/`: `parse.py` reads the timetable grids, `compare.py` matches trains and finds issues, `output.py` fills `template.xlsx`, `prints.py` / `attune_print.py` and `trainlist.py` handle train prints and Attune lists, `base.py` turns a print or list into the reference timetable, `engine.py` runs them and `gui_tab.py` is the tab.
* Run from source with `pip install -r requirements.txt`, then `python TrainPlanningTools.py`.
* Run the tests with `python -m pytest tests`. They generate synthetic CWNs, TRENT prints and XML, so no real data is needed.
* The Windows exe is built by `.github/workflows/build-windows.yml` on every push, using PyInstaller and `packaging/TrainPlanningTools.spec`. The spec explains what is left out to keep the exe small. To build it locally on Windows, run `build_windows.bat`.
* Real CWN workbooks, TRENT prints and XML exports are git-ignored, so they are never committed.
