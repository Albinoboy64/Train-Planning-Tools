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
