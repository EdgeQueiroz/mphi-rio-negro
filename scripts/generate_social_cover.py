"""Generate the static MPHI sharing cover (requires Pillow).

No live river level or model output belongs in this cached social preview.
Run from the repository root: python3 scripts/generate_social_cover.py
"""

from pathlib import Path
import math

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assets/mphi-rio-negro-social.jpg"
SCALE = 2
WIDTH, HEIGHT = 1200, 630


def pt(value):
    return round(value * SCALE)


def font(size, bold=False):
    variant = "Bold" if bold else "Regular"
    candidates = (
        f"/usr/share/fonts/opentype/urw-base35/NimbusSans-{variant}.otf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, pt(size))
    raise FileNotFoundError("Nimbus Sans or DejaVu Sans is needed to render the cover")


def tracked(draw, xy, value, font_obj, fill, spacing):
    x, y = xy
    for char in value:
        draw.text((pt(x), pt(y)), char, font=font_obj, fill=fill, anchor="lt")
        x += draw.textlength(char, font=font_obj) / SCALE + spacing


def main():
    image = Image.new("RGB", (pt(WIDTH), pt(HEIGHT)))
    pixels = image.load()
    for y in range(pt(HEIGHT)):
        for x in range(pt(WIDTH)):
            nx = x / pt(WIDTH)
            ny = y / pt(HEIGHT)
            glow = max(0.0, 1 - math.hypot((nx - 0.86) / 0.79, (ny - 0.42) / 0.97))
            pixels[x, y] = (
                int(7 + 7 * nx + 8 * glow),
                int(20 + 15 * nx + 21 * glow),
                int(32 + 20 * nx + 27 * glow),
            )

    draw = ImageDraw.Draw(image, "RGBA")

    # Abstract channel lines are decorative, without scale or plotted data.
    for i in range(21):
        xbase = 745 + 27 * i
        line = []
        for y in range(-40, 701, 5):
            bend = 43 * math.sin((y / 620) * 2.0 * math.pi + i * 0.18)
            smaller = 17 * math.sin((y / 620) * 4.1 * math.pi + i * 0.28)
            line.append((pt(xbase + bend + smaller), pt(y)))
        hue = (95, 200, 201, 70 if i % 5 == 0 else 29)
        draw.line(line, fill=hue, width=pt(2 if i % 5 == 0 else 1), joint="curve")

    # Framing and institutional masthead.
    draw.rounded_rectangle((pt(38), pt(38), pt(1162), pt(592)), radius=pt(14), outline=(143, 202, 212, 49), width=pt(1))
    draw.rounded_rectangle((pt(76), pt(72), pt(132), pt(128)), radius=pt(12), fill=(24, 54, 71, 255), outline=(87, 142, 155, 162), width=pt(1))
    for yy in (88, 100, 112):
        coords = [(pt(86 + x), pt(yy + 3 * math.sin(x * math.pi / 18))) for x in range(0, 36, 2)]
        draw.line(coords, fill=(115, 213, 208, 235), width=pt(2), joint="curve")
    tracked(draw, (151, 76), "MPHI", font(36, bold=True), (235, 246, 248, 255), 3)
    tracked(draw, (151, 114), "MODELO PREDITIVO HIDROLÓGICO UIARA", font(10, bold=True), (151, 187, 198, 255), 1.35)
    draw.line((pt(76), pt(168), pt(1124), pt(168)), fill=(127, 173, 187, 80), width=pt(1))

    tracked(draw, (76, 218), "INTELIGÊNCIA HIDROLÓGICA · AMAZÔNIA", font(15, bold=True), (117, 210, 207, 255), 2.6)
    draw.text((pt(71), pt(263)), "Rio Negro", font=font(112, bold=True), fill=(239, 248, 249, 255), anchor="lt", stroke_width=0)
    draw.rounded_rectangle((pt(76), pt(411), pt(131), pt(416)), radius=pt(2), fill=(104, 205, 199, 255))
    draw.text((pt(76), pt(444)), "Monitoramento, projeções e validação contínua", font=font(26), fill=(191, 217, 226, 255), anchor="lt")

    draw.line((pt(76), pt(543), pt(1124), pt(543)), fill=(127, 173, 187, 80), width=pt(1))
    tracked(draw, (76, 559), "RIO NEGRO / MANAUS · AM", font(12, bold=True), (166, 196, 205, 255), 2.2)
    tracked(draw, (955, 559), "UIARA · MPHI", font(12, bold=True), (166, 196, 205, 255), 1.8)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(
        OUTPUT, quality=88, optimize=True, progressive=True, subsampling=0
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
