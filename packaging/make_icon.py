"""Generate the Train Planning Tools logo (run once; the outputs are committed).

A flat, front-on Class 387 style cab (blue body, yellow hood, gangway door and warning panel, dark
windscreens, headlight clusters, red / white stripes up the cab sides) on a light tile. No operator
logos. Drawn at 1024 px and scaled down, so it stays recognisable
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
BODY_TOP, BODY_BOTTOM = (46, 74, 176), (22, 36, 112)
NAVY = (16, 26, 82)
RED, WHITE = (216, 36, 44), (252, 252, 252)
YELLOW, YELLOW_DARK = (252, 206, 24), (214, 164, 0)
GLASS, SHINE = (16, 24, 44), (74, 96, 132)
FRAME, STEEL, BLACK = (92, 98, 108), (66, 72, 82), (20, 22, 26)


def _gradient(size, top, bottom):
    g = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    return g.resize((size, size))


def draw() -> Image.Image:
    """A flat, front-on Class 387 style cab on a light tile: few bold shapes, one blue, one yellow, one red."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile = Image.new("L", (S, S), 0)
    ImageDraw.Draw(tile).rounded_rectangle([16, 16, S - 16, S - 16], radius=224, fill=255)
    img.paste(_gradient(S, TILE_TOP, TILE_BOTTOM), (0, 0), tile)

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([226, 838, 798, 904], fill=(20, 30, 70, 120))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))

    # body: rounded roof, squarer base, blue shading from top to bottom, red / white stripes up the sides
    mask = Image.new("L", (S, S), 0)
    m = ImageDraw.Draw(mask)
    m.rounded_rectangle([236, 120, 788, 860], radius=190, fill=255)
    m.rounded_rectangle([236, 560, 788, 860], radius=44, fill=255)
    body = _gradient(S, BODY_TOP, BODY_BOTTOM)
    b = ImageDraw.Draw(body)
    for side in (1, -1):
        x = (lambda v: v) if side == 1 else (lambda v: S - v)
        b.polygon([(x(236), 560), (x(292), 470), (x(292), 860), (x(236), 860)], fill=WHITE)
        b.polygon([(x(236), 620), (x(270), 560), (x(270), 860), (x(236), 860)], fill=RED)
    img.paste(body, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # yellow hood and dark windscreens
    d.rounded_rectangle([300, 168, 724, 330], radius=86, fill=YELLOW)
    d.rounded_rectangle([312, 238, 712, 506], radius=40, fill=GLASS)
    d.polygon([(330, 480), (372, 262), (398, 262), (358, 480)], fill=SHINE)
    d.polygon([(694, 480), (652, 262), (626, 262), (666, 480)], fill=SHINE)

    # yellow warning panel and headlight clusters
    d.rounded_rectangle([296, 500, 728, 716], radius=34, fill=YELLOW)
    d.rectangle([296, 500, 728, 514], fill=YELLOW_DARK)
    for cx, sx in ((366, 1), (658, -1)):
        d.rounded_rectangle([cx - 58, 590, cx + 58, 690], radius=34, fill=BLACK)
        d.ellipse([cx - 26 * sx - 30, 610, cx - 26 * sx + 30, 670], fill=WHITE)
        d.ellipse([cx + 30 * sx - 13, 628, cx + 30 * sx + 13, 654], fill=(255, 232, 160))

    # gangway door down the middle
    d.rounded_rectangle([436, 176, 588, 716], radius=24, fill=FRAME)
    d.rounded_rectangle([450, 190, 574, 702], radius=14, fill=YELLOW)
    d.rounded_rectangle([474, 238, 550, 352], radius=12, fill=GLASS)
    d.rectangle([450, 190, 574, 208], fill=YELLOW_DARK)

    # dark skirt and coupler
    d.rounded_rectangle([276, 716, 748, 806], radius=30, fill=NAVY)
    d.rectangle([276, 716, 748, 740], fill=NAVY)
    d.rounded_rectangle([452, 736, 572, 830], radius=20, fill=STEEL)
    d.rounded_rectangle([480, 762, 544, 806], radius=12, fill=BLACK)
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
