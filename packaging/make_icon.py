"""Generate the Train Planning Tools logo (run once; the outputs are committed).

A flat, front-on Class 387 cab on a light tile, drawn in the proportions of the real front: arched roof
with the yellow hood and orange line, central gangway door, a windscreen either side, yellow warning
panels with headlight and marker lamps, blue valance and coupler cover.
No operator logos. Drawn at 1024 px and scaled down, so it stays recognisable
from 16 px (taskbar) to the large README logo. Writes:
  packaging/TrainPlanningTools.ico     - Windows icon, 16-256 px
  rstools/assets/logo.png             - 64 px, shown in the app header (scaled to the text size)
  rstools/assets/logo_16.png / _32 / _48 - window icon on other systems, header at other text sizes
  packaging/logo.png                  - 512 px, for the README
"""
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S = 1024                                  # drawn large, then scaled down for crisp edges

TILE_TOP, TILE_BOTTOM = (244, 247, 252), (208, 219, 238)
BLUE_TOP, BLUE_BOTTOM = (40, 58, 150), (24, 36, 112)
VALANCE, VALANCE_EDGE = (28, 40, 118), (62, 80, 168)
YELLOW, YELLOW_DARK, ORANGE = (250, 190, 22), (214, 150, 0), (238, 104, 40)
GLASS, SHINE, TRAY = (18, 24, 36), (64, 78, 98), (34, 38, 46)
FRAME, FRAME_LIGHT = (84, 82, 80), (128, 126, 122)
RIM, SILVER, SILVER_DARK = (26, 28, 32), (236, 240, 244), (150, 156, 164)
WHITE_BOX, BLACK = (226, 228, 230), (14, 16, 20)

# The face is laid out in the pixel coordinates of a photograph of a Class 387 (face about 640 wide and 970
# tall, roof at y 55, skirt at y 1030) and mapped onto the tile. It is symmetrical about the centre line
# (x = 350); the photo is taken at an angle, so its left and right sides look different.
K, X0, Y0 = 0.78, 262.0, 118.0


def T(x, y):
    return (X0 + (x - 30) * K, Y0 + (y - 60) * K)


def _pts(points):
    return [T(x, y) for x, y in points]


def _spline(points, n=3, closed=True):
    """Round the corners of a polygon by cutting each one n times (Chaikin), which never overshoots the shape."""
    pts = list(points)
    for _ in range(n):
        out = []
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            out += [(0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]),
                    (0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1])]
        pts = out
    return pts


def _gradient(size, top, bottom):
    g = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    return g.resize((size, size))


def draw() -> Image.Image:
    """A flat, front-on Class 387 cab on a light tile, in the proportions of the real front."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile = Image.new("L", (S, S), 0)
    ImageDraw.Draw(tile).rounded_rectangle([16, 16, S - 16, S - 16], radius=224, fill=255)
    img.paste(_gradient(S, TILE_TOP, TILE_BOTTOM), (0, 0), tile)

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([*T(60, 1000), *T(650, 1080)], fill=(20, 30, 70, 120))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))

    def rr(box, r, fill, d=None):
        (d or ImageDraw.Draw(img)).rounded_rectangle([*T(box[0], box[1]), *T(box[2], box[3])], radius=r * K, fill=fill)

    def poly(points, fill, spline=0):
        pts = _pts(points)
        ImageDraw.Draw(img).polygon(_spline(pts, spline) if spline else pts, fill=fill)

    def oval(cx, cy, r, fill):
        ImageDraw.Draw(img).ellipse([*T(cx - r, cy - r), *T(cx + r, cy + r)], fill=fill)

    # body: arched roof, near-vertical sides, a valance below, shaded from top to bottom
    outline = [(30, 330), (34, 230), (58, 160), (120, 100), (230, 66), (350, 55), (470, 66), (580, 100), (642, 160),
               (666, 230), (670, 330), (670, 800), (664, 980), (640, 1022), (560, 1030), (200, 1030), (100, 1022),
               (60, 975), (28, 800)]
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(_spline(_pts(outline), 3), fill=255)
    img.paste(_gradient(S, BLUE_TOP, BLUE_BOTTOM), (0, 0), mask)
    poly([(56, 795), (668, 795), (664, 980), (640, 1022), (560, 1030), (200, 1030), (100, 1022), (60, 975)], VALANCE, 3)
    ImageDraw.Draw(img).line([*T(60, 797), *T(666, 797)], fill=VALANCE_EDGE, width=max(2, int(5 * K)))

    # yellow hood across the top, with the thin orange line under it
    hood = [(30, 215), (40, 170), (80, 128), (150, 104), (230, 90), (350, 86), (470, 90), (580, 110), (640, 150),
            (668, 200), (672, 215)]
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.polygon(_pts(hood), fill=YELLOW)
    ld.polygon(_pts([(28, 203), (672, 203), (672, 216), (28, 216)]), fill=ORANGE)
    layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", (S, S), 0), mask))
    img.alpha_composite(layer)
    rr((285, 62, 415, 122), 30, TRAY)                                          # roof light
    rr((300, 72, 400, 108), 18, SHINE)

    # everything below is mirrored about the centre line (x = 350 in the photo's coordinates)
    def mirror(points):
        return [(700 - x, y) for x, y in points]

    # windscreens either side of the door, each with a dark wiper tray under it
    for side in (False, True):
        tray = [(46, 222), (232, 222), (232, 548), (40, 544), (38, 470)]
        glass = [(58, 232), (230, 232), (230, 508), (56, 504)]
        shine = [(86, 500), (130, 250), (160, 250), (116, 500)]
        poly(mirror(tray) if side else tray, TRAY)
        poly(mirror(glass) if side else glass, GLASS)
        poly(mirror(shine) if side else shine, SHINE)

    # yellow warning panels, each with a headlight and a marker lamp (the lamp nearest the door is the small one)
    panels = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panels)
    left = [(10, 566), (236, 566), (236, 750), (150, 752), (70, 722), (10, 660)]
    for pts in (left, mirror(left)):
        pd.polygon(_spline(_pts(pts), 1), fill=YELLOW)
    panels.putalpha(Image.composite(panels.getchannel("A"), Image.new("L", (S, S), 0), mask))   # follow the body edge
    img.alpha_composite(panels)
    for side in (False, True):
        sx = -1 if side else 1
        cx = 350 - sx * 230                       # centre of each light cluster
        rr((cx - 90, 628, cx + 90, 742), 56, RIM)
        oval(cx - sx * 30, 684, 38, SILVER_DARK)
        oval(cx - sx * 30, 684, 32, SILVER)
        oval(cx + sx * 44, 702, 26, SILVER_DARK)
        oval(cx + sx * 44, 702, 21, SILVER)

    # recess under the door, then the central gangway door with its frame
    rr((222, 806, 478, 1006), 34, BLACK)
    rr((228, 134, 472, 814), 34, FRAME)
    rr((240, 150, 460, 800), 22, FRAME_LIGHT)
    poly([(266, 228), (434, 228), (434, 792), (266, 792)], YELLOW)
    rr((240, 150, 460, 215), 22, FRAME_LIGHT)
    ImageDraw.Draw(img).line([*T(266, 228), *T(434, 228)], fill=YELLOW_DARK, width=max(2, int(6 * K)))

    # coupler cover and bar
    rr((290, 836, 410, 924), 10, WHITE_BOX)
    oval(350, 880, 24, BLACK)
    oval(312, 880, 9, SILVER_DARK)
    rr((268, 928, 432, 968), 12, BLACK)
    return img


def main():
    big = draw()
    os.makedirs(os.path.join(ROOT, "rstools", "assets"), exist_ok=True)
    big.resize((256, 256), Image.LANCZOS).save(
        os.path.join(HERE, "TrainPlanningTools.ico"),
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
    for size, name in ((64, "logo.png"), (48, "logo_48.png"), (32, "logo_32.png"), (16, "logo_16.png")):
        big.resize((size, size), Image.LANCZOS).save(os.path.join(ROOT, "rstools", "assets", name), optimize=True)
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(HERE, "logo.png"), optimize=True)
    print("written")


if __name__ == "__main__":
    main()
