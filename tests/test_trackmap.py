"""Track map view: a track diagram PDF read into its layout, the units standing at a place through the day, and where
they are drawn (synthetic map and XML only - real track diagrams are never committed)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("pypdfium2")
pytest.importorskip("reportlab")

PLATS = {"1": 300, "2": 250, "4": 200, "7": 150}       # platform -> track height (from the top of the page)


def make_map(path):
    """One page drawn as route track diagrams are: platform roads as thin blue bands ending at buffer stops on the
    right, joined on the left by a crossover; 'Plat n' labels just above each; the page name and station name."""
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=(842, 595))
    blue, red = Color(66 / 255, 48 / 255, 146 / 255), Color(199 / 255, 46 / 255, 31 / 255)
    for plat, top in PLATS.items():
        y = 595 - top
        c.setFillColor(blue)
        c.rect(480, y, 290, 0.7, fill=1, stroke=0)               # the road, 480 -> 770
        c.setStrokeColor(red)
        c.setLineWidth(0.72)
        c.line(440, y - 20, 480.3, y)                            # a crossover joins its left end
        c.setFillColor(Color(0, 0, 0))
        c.setFont("Helvetica", 5)
        c.drawString(735, y + 4, f"Plat {plat}")
    c.setFont("Helvetica", 14)
    c.drawString(720, 560, "Test 25")
    c.setFont("Helvetica", 12)
    c.drawString(650, 520, "BRIGHTON")
    c.showPage()
    c.save()


@pytest.fixture
def world(tmp_path, monkeypatch):
    import test_berthing as tb
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    trains, diagrams = tb.base_plan()
    (tmp_path / "plan.xml").write_text(tb.xml(trains, diagrams))
    make_map(str(tmp_path / "map.pdf"))
    return tmp_path


def test_a_track_map_is_read_into_its_layout_and_kept_small(world):
    from rstools.trackmap.pdfmap import find_pages, import_map, load_map, stored_maps
    name = import_map(str(world / "map.pdf"))
    assert name in stored_maps()
    pages = load_map(name)
    page = find_pages(pages, "Brighton")[0]
    assert page.title == "Test 25" and "BRIGHTON" in page.headings
    roads = [t for t in page.tracks if t.kind == "running"]
    assert len(roads) == 4 and all(abs(t.pts[0][1] - t.pts[-1][1]) < 1.5 for t in roads)      # level lines
    assert {lb.text for lb in page.labels} >= {"Plat 1", "Plat 2", "Plat 4", "Plat 7"}
    assert not any(f.endswith(".pdf") for f in os.listdir(world / "appdata" / "TrainPlanningTools-data" / "trackmaps")
                   ) if (world / "appdata" / "TrainPlanningTools-data").exists() else True   # the PDF is not copied


def test_units_are_drawn_on_their_platform_from_the_buffer_stop(world):
    from rstools.trackmap.engine import build
    from rstools.trackmap.pdfmap import import_map, load_map
    name = import_map(str(world / "map.pdf"))
    page = load_map(name)[0]
    view = build(name, page.index, str(world / "plan.xml"), "Brighton", 0)
    night = view.at(3 * 3600)                   # BI1 came in at 02:02 and forms BI10 (one unit, drawn once);
    by = {u.stand.unit: u for u in night.units}  # BI40 on P7 from the night before
    p1 = [u for u in night.units if abs(u.a[1] - PLATS["1"]) < 2]
    assert [u.stand.unit for u in p1] == ["BI10"] and p1[0].stand.was == "BI1" and p1[0].stand.arrived_as == "5H73BV"
    assert p1[0].a[0] > 760                                     # at the buffer stop end
    assert abs(by["BI40"].a[1] - PLATS["7"]) < 2
    morning = view.at(5 * 3600 + 15 * 60)                       # BI5 has come in behind BI40 on P7
    p7 = sorted((u for u in morning.units if abs(u.a[1] - PLATS["7"]) < 2), key=lambda u: -u.a[0])
    assert [u.stand.unit for u in p7] == ["BI40", "BI5"]
    assert p7[0].b[0] > p7[1].a[0] - 1                           # one behind the other, not on top
    assert p7[1].stand.arrived_as == "5U01BS" and p7[1].stand.leaves_as == "1U04BS"
    assert all(u.stand.unit not in ("BI40", "BI5") for u in view.at(7 * 3600).units)        # gone as 1U04
    assert 5 * 3600 + 10 * 60 in view.events()                   # stepping stops when a train arrives


def test_a_place_not_on_the_page_is_listed_not_guessed(world):
    from rstools.trackmap.occupancy import place_locations
    from rstools.trackmap.scene import label_for
    from rstools.trackmap.pdfmap import Label
    assert place_locations({"BRGHTN": "Brighton", "BRGHWS": "Brighton Wall Siding", "BRGH280": "Brighton Signal T1280",
                            "HOVE": "Hove"}, "Brighton") == ["BRGHTN", "BRGHWS"]
    labels = [Label("WALL SIDING", 0, 0), Label("DEPARTURE ROAD", 0, 0), Label("Plat 7", 0, 0)]
    assert label_for(("BRGHWS", "S2"), "Brighton Wall Siding", "Brighton", labels).text == "WALL SIDING"
    assert label_for(("BRGHRC", ""), "Brighton Reception Road", "Brighton", labels) is None    # not just 'road'
    assert label_for(("BRGHTN", "7F"), "Brighton", "Brighton", labels).text == "Plat 7"         # front of P7


def test_the_window_opens_with_the_kept_maps(world, monkeypatch):
    tk = pytest.importorskip("tkinter")
    from rstools.trackmap.pdfmap import import_map
    from rstools.trackmap.window import TrackMapWindow
    import_map(str(world / "map.pdf"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        win = TrackMapWindow(root)
        assert win.map_var.get() == "map"
        win._close()
    finally:
        root.destroy()


def make_strip_map(path):
    """A page as the strip-diagram books (East Midlands, LNE) store it: turned (/Rotate 90), the tracks thick strokes
    coloured by track circuit, a black crossover, 'Platform n' labels and the station's 'STANOX : TIPLOC' code."""
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=(595, 842))
    c.setPageRotation(90)
    c.setStrokeColor(Color(1, 0.85, 0))
    c.setLineWidth(2.5)
    for x in (300, 330, 370, 400):
        c.line(x, 100, x, 500)                                  # shown level, 100 -> 500 across the page
    c.setStrokeColor(Color(0, 0, 0))
    c.line(300, 90, 330, 70)
    for x, size, text in ((290, 6, "Platform 1"), (340, 6, "Platform 2"), (450, 5, "54321 : TESTPL"),
                          (500, 12, "Test Town")):
        c.saveState()
        c.translate(x, 300)
        c.rotate(90)
        c.setFont("Helvetica", size)
        c.drawString(0, 0, text)
        c.restoreState()
    c.showPage()
    c.save()


def test_a_turned_strip_diagram_page_is_read_level_and_found_by_its_tiploc(tmp_path):
    from rstools.trackmap.pdfmap import Label, MapPage, find_pages, page_from_dict, read_page_layout
    from rstools.trackmap.scene import anchor_of, label_for
    make_strip_map(str(tmp_path / "strip.pdf"))
    page = page_from_dict(read_page_layout(str(tmp_path / "strip.pdf"), 0))
    roads = [t for t in page.tracks if t.kind == "running"]
    assert len(roads) == 4 and all(abs(t.pts[0][1] - t.pts[-1][1]) < 1 and t.length > 350 for t in roads)
    assert any(t.kind == "points" for t in page.tracks)          # the black crossover
    assert "TESTPL" in page.codes
    other = MapPage(1, 842, 595, "", page.tracks, [Label("Elsewhere", 0, 0)])
    assert find_pages([other, page], "Anywhere", ["TESTPL"]) == [page]    # by its code, whatever it is called
    anchor = anchor_of(page, "Anywhere", ["TESTPL"])
    assert anchor == page.codes["TESTPL"]
    lb = label_for(("TESTPL", "2"), "Anywhere", "Anywhere", page.labels, anchor)
    assert lb is not None and lb.text == "Platform 2"


def test_platform_labels_of_the_right_station_on_a_page_of_several():
    from rstools.trackmap.pdfmap import Label, MapPage
    from rstools.trackmap.scene import anchor_of, label_for
    labels = [Label("NORBURY", 160, 210, 6), Label("P1", 161, 257), Label("P2", 155, 296),
              Label("THORNTON HEATH", 436, 217, 6), Label("P1", 409, 258), Label("P2", 404, 296)]
    page = MapPage(0, 842, 595, "", [], labels)
    anchor = anchor_of(page, "Thornton Heath")
    hit = label_for(("THTH", "1"), "Thornton Heath", "Thornton Heath", labels, anchor)
    assert (hit.x, hit.y) == (409, 258)
    assert label_for(("THTH", "1"), "Thornton Heath", "Thornton Heath", labels) is None   # no anchor: not a guess
    assert label_for(("VIC", "8"), "London Victoria (C)", "London Victoria (C)", [Label("Plat 8", 0, 0)]).text \
        == "Plat 8"


def test_place_names_as_maps_write_them_and_the_locations_of_a_place():
    from rstools.trackmap.occupancy import place_locations
    from rstools.trackmap.pdfmap import place_variants
    assert place_variants("London Victoria (C)") == ["london victoria", "victoria"]
    assert "london bridge" in place_variants("London Bridge (E)") and "bridge" not in place_variants("London Bridge")
    assert place_variants("Selhurst T&R.S.M.D")[-1] == "selhurst"
    assert place_variants("Welwyn G.C.C.S.D.")[-1] == "welwyn garden city"
    locs = {"STRHAM": "Streatham", "STRHCOM": "Streatham Common", "STRHHL": "Streatham Hill",
            "STRHSDG": "Streatham Down Sidings", "STRHJN": "Streatham North Jn"}
    assert place_locations(locs, "Streatham") == ["STRHAM", "STRHSDG"]      # not the stations sharing its name


def test_a_depot_shows_only_how_many_units_are_there():
    from rstools.trackmap.occupancy import Stand
    from rstools.trackmap.pdfmap import Label, MapPage, Track
    from rstools.trackmap.scene import match_roads, scene
    page = MapPage(0, 842, 595, "", [Track("running", [(100, 100), (400, 100)])],
                   [Label("SELHURST", 300, 60, 8), Label("Selhurst T&RSMD", 700, 300), Label("Plat 1", 380, 95)])
    keys = [("SELHRST", "1"), ("SELHDEP", "GUL"), ("SELHDEP", "YD1")]
    roads = match_roads(page, keys, {"SELHRST": "Selhurst", "SELHDEP": "Selhurst Depot Gullet Road"}, "Selhurst",
                        depots={"SELHDEP": "Selhurst"})
    assert roads[("SELHDEP", "GUL")].depot and roads[("SELHDEP", "GUL")].pts == [(700, 300)]
    stands = [Stand(f"U{i}", "377", "SELHDEP", road, 0, 3600, "", "", (f"U{i}",)) for i, road in
              enumerate(("GUL", "GUL", "YD1"))] + [Stand("U9", "377", "SELHRST", "1", 0, 3600, "", "", ("U9",))]
    sc = scene(stands, roads, 600, {"377": 4})
    assert sc.counts == [("Selhurst", (700, 300), 3)]             # one total for the depot, no units drawn there
    assert [u.stand.unit for u in sc.units] == ["U9"]


def test_coverage_lists_each_place_and_is_saved_without_overwriting(world):
    from rstools.trackmap.engine import coverage, save_coverage
    from rstools.trackmap.pdfmap import import_map
    import_map(str(world / "map.pdf"))
    rows = coverage(str(world / "plan.xml"), 0)
    brighton = next(r for r in rows if r.place == "Brighton")
    assert brighton.placed >= 1 and brighton.map_name == "map" and brighton.page == "Test 25"
    out = world / "out"
    out.mkdir()
    first = save_coverage(rows, str(out), 0)
    second = save_coverage(rows, str(out), 0)
    assert first != second and os.path.isfile(first) and os.path.isfile(second)


def test_the_window_searches_every_map_and_draws_depot_totals(world, monkeypatch):
    tk = pytest.importorskip("tkinter")
    import shutil
    from rstools.trackmap.engine import ALL_MAPS
    from rstools.trackmap.pdfmap import import_map
    from rstools.trackmap.scene import Road
    from rstools.trackmap.window import TrackMapWindow
    shutil.copy(world / "map.pdf", world / "second.pdf")
    import_map(str(world / "map.pdf"))
    import_map(str(world / "second.pdf"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        win = TrackMapWindow(root)
        assert win.map_var.get() == ALL_MAPS
        win.xml_var.set(str(world / "plan.xml"))
        win.place_var.set("Brighton")
        win._find_pages()
        for _ in range(100):                         # the pages are found off the window's thread
            root.update()
            if win.page_box.cget("values"):
                break
            import time
            time.sleep(0.05)
        pages = list(win.page_box.cget("values"))
        assert any(p.startswith("map:") for p in pages) and any(p.startswith("second:") for p in pages)
        from rstools.trackmap.engine import build
        win.view = build("map", 0, str(world / "plan.xml"), "Brighton", 0)
        win.view.roads[("BRGHDEP", "")] = Road(("BRGHDEP", ""), "Brighton depot", [(100, 100)], depot=True)
        win._draw_page()
        win._draw_units()                            # depot badges draw with the units
        win._close()
    finally:
        root.destroy()
