"""Generate the Train Planning Tools logo (run once; the outputs are committed).

A front-on Class 387 Electrostar cab in the blue, red and white Great British Railways livery: yellow
gangway door and warning panel, dark windscreens, headlight clusters, the red / white stripe on the
cab sides, on a sky-blue badge with rails. Drawn at 1024 px and scaled down, so it stays recognisable
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

SKY_TOP, SKY_BOTTOM = (120, 186, 236), (214, 236, 250)
BLUE, BLUE_DARK, BLUE_LIGHT = (32, 44, 120), (18, 26, 78), (58, 74, 160)
RED, WHITE = (222, 40, 40), (250, 250, 250)
YELLOW, YELLOW_DARK = (250, 204, 20), (206, 160, 0)
GLASS, GLASS_SHINE = (14, 20, 30), (70, 92, 118)
GREY, GREY_DARK = (150, 156, 162), (92, 98, 104)
BLACK, STEEL, RAIL, SLEEPER = (22, 24, 28), (60, 66, 72), (196, 202, 208), (110, 92, 74)


def _gradient(size, top, bottom):
    g = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    return g.resize((size, size))


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([24, 24, S - 24, S - 24], radius=210, fill=255)
    img.paste(_gradient(S, SKY_TOP, SKY_BOTTOM), (0, 0), mask)
    d = ImageDraw.Draw(img)

    # ballast, sleepers and rails running towards the viewer
    d.polygon([(330, 820), (694, 820), (900, S - 40), (124, S - 40)], fill=(150, 140, 128))
    for y, half in ((846, 200), (900, 255), (956, 310)):
        d.rectangle([512 - half, y, 512 + half, y + 18], fill=SLEEPER)
    d.polygon([(452, 820), (482, 820), (330, S - 40), (268, S - 40)], fill=RAIL)
    d.polygon([(542, 820), (572, 820), (756, S - 40), (694, S - 40)], fill=RAIL)
    img.paste((0, 0, 0, 0), (0, 0, S, S), Image.eval(mask, lambda v: 255 - v))   # keep inside the badge

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([230, 780, 794, 860], fill=(0, 0, 0, 130))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(img)

    # cab body: rounded roof, sides flaring out slightly towards the bottom
    body = [(286, 330), (318, 210), (392, 150), (632, 150), (706, 210), (738, 330), (758, 790), (266, 790)]
    d.polygon(body, fill=BLUE)
    d.polygon([(286, 330), (318, 210), (392, 150), (412, 150), (346, 222), (318, 340), (300, 790), (266, 790)],
              fill=BLUE_LIGHT)                                              # light on the left edge
    d.polygon([(738, 330), (706, 210), (632, 150), (612, 150), (678, 222), (706, 340), (724, 790), (758, 790)],
              fill=BLUE_DARK)                                               # shade on the right edge
    # red and white stripe sweeping up the cab sides (as on the bodyside next to the cab)
    for side in (1, -1):
        x = (lambda v: v) if side == 1 else (lambda v: S - v)
        d.polygon([(x(266), 790), (x(266), 560), (x(296), 420), (x(330), 420), (x(312), 790)], fill=WHITE)
        d.polygon([(x(266), 790), (x(266), 610), (x(292), 480), (x(316), 480), (x(302), 790)], fill=RED)

    # front face: one dark glazed band across the cab (windscreens), gangway door in the middle
    d.polygon([(326, 238), (698, 238), (716, 470), (308, 470)], fill=GLASS)
    d.polygon([(330, 452), (380, 262), (410, 262), (360, 452)], fill=GLASS_SHINE)       # reflections
    d.polygon([(620, 452), (670, 262), (690, 262), (640, 452)], fill=GLASS_SHINE)
    d.rounded_rectangle([348, 248, 416, 268], radius=6, fill=(40, 40, 40))             # destination blind
    d.rectangle([356, 254, 408, 262], fill=(255, 176, 0))
    d.rounded_rectangle([430, 210, 594, 610], radius=26, fill=GREY_DARK)               # gangway frame
    d.rounded_rectangle([446, 226, 578, 600], radius=18, fill=GREY)
    d.rounded_rectangle([460, 240, 564, 590], radius=12, fill=YELLOW)                  # gangway door
    d.rectangle([460, 240, 564, 256], fill=YELLOW_DARK)
    d.rounded_rectangle([484, 286, 540, 376], radius=10, fill=GLASS)                   # door window

    # lower front: yellow warning panel with the headlight clusters, dark valance and coupler
    d.polygon([(308, 470), (716, 470), (736, 700), (288, 700)], fill=YELLOW)
    d.polygon([(308, 470), (716, 470), (718, 486), (306, 486)], fill=YELLOW_DARK)
    d.rounded_rectangle([430, 470, 594, 610], radius=0, fill=GREY_DARK)                # frame continues down
    d.rounded_rectangle([446, 470, 578, 600], radius=18, fill=GREY)
    d.rounded_rectangle([460, 470, 564, 590], radius=12, fill=YELLOW)
    for cx in (366, 658):
        d.rounded_rectangle([cx - 52, 596, cx + 52, 664], radius=26, fill=BLACK)
        d.ellipse([cx - 40, 606, cx, 654], fill=(255, 255, 255))             # headlight
        d.ellipse([cx + 4, 612, cx + 40, 648], fill=(255, 236, 170))          # marker light
    d.polygon([(288, 700), (736, 700), (758, 790), (266, 790)], fill=BLUE_DARK)
    d.rounded_rectangle([438, 690, 586, 806], radius=18, fill=STEEL)          # Dellner coupler
    d.rounded_rectangle([470, 716, 554, 778], radius=12, fill=BLACK)
    d.rounded_rectangle([488, 734, 536, 760], radius=8, fill=GREY_DARK)
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
