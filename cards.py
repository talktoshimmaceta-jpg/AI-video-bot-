"""Generates branded student ID cards and completion certificates as PNGs.

Uses only Pillow (no photos required — name + role, matching the
Heribhee Studio navy-and-gold branding).
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
# Fonts can live either in a fonts/ subfolder or directly in the repo root —
# whichever is found first is used, so no need to reorganize files on GitHub.
_fonts_subdir = os.path.join(HERE, "fonts")
FONT_DIR = _fonts_subdir if os.path.isdir(_fonts_subdir) else HERE
LOGO_PATH = os.getenv("LOGO_FILE", os.path.join(HERE, "logo.png"))

NAVY = (5, 22, 46)
NAVY_DEEP = (3, 14, 30)
GOLD = (223, 178, 95)
GOLD_LIGHT = (240, 210, 150)
CREAM = (245, 240, 228)
WHITE = (255, 255, 255)


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _centered_text(draw, cx, y, text, font, fill, anchor="ma"):
    draw.text((cx, y), text, font=font, fill=fill, anchor=anchor)


def _load_logo(max_size):
    if not os.path.exists(LOGO_PATH):
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo.thumbnail((max_size, max_size), Image.LANCZOS)
    return logo


def _gold_border(draw, box, width=4, radius=28):
    draw.rounded_rectangle(box, radius=radius, outline=GOLD, width=width)


# ---------------------------------------------------------------------------
# Student ID card
# ---------------------------------------------------------------------------
def generate_id_card(name: str, role: str, student_no: str, program: str) -> io.BytesIO:
    W, H = 1000, 1250
    img = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(img)

    # subtle vertical gradient
    for y in range(H):
        t = y / H
        r = int(NAVY[0] + (NAVY_DEEP[0] - NAVY[0]) * t)
        g = int(NAVY[1] + (NAVY_DEEP[1] - NAVY[1]) * t)
        b = int(NAVY[2] + (NAVY_DEEP[2] - NAVY[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # outer gold frame
    _gold_border(draw, [24, 24, W - 24, H - 24], width=5, radius=36)
    _gold_border(draw, [40, 40, W - 40, H - 40], width=2, radius=28)

    # top header band
    draw.rounded_rectangle([40, 40, W - 40, 260], radius=28, fill=(8, 32, 62))
    draw.rectangle([40, 220, W - 40, 260], fill=(8, 32, 62))  # square off bottom of band

    logo = _load_logo(150)
    if logo:
        img.paste(logo, (70, 55), logo)

    title_x = 240 if logo else 80
    draw.text((title_x, 75), "HERIBHEE STUDIO", font=_font("Outfit-Bold.ttf", 46), fill=GOLD_LIGHT)
    draw.text((title_x, 140), "AI VIDEO & MOVIE CREATION ACADEMY", font=_font("WorkSans-Regular.ttf", 24), fill=CREAM)

    # big vertical "STUDENT" watermark on the left
    vert = Image.new("RGBA", (H, 220), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vert)
    vd.text((0, 0), "STUDENT", font=_font("Outfit-Bold.ttf", 150), fill=(255, 255, 255, 16))
    vert = vert.rotate(90, expand=True)
    img.paste(vert, (0, 300), vert)

    # small gold diamond emblem instead of a photo
    ex, ey, es = W // 2, 350, 16
    draw.polygon(
        [(ex, ey - es), (ex + es, ey), (ex, ey + es), (ex - es, ey)],
        outline=GOLD, width=3,
    )

    # name — the centerpiece
    name_font = _font("Italiana-Regular.ttf", 72)
    _centered_text(draw, W // 2, 430, name, name_font, WHITE, anchor="ma")

    # divider
    draw.line([(150, 560), (W - 150, 560)], fill=GOLD, width=2)

    # fields
    label_font = _font("WorkSans-Bold.ttf", 26)
    value_font = _font("WorkSans-Regular.ttf", 32)
    fields = [
        ("STUDENT ID", student_no),
        ("ROLE", role),
        ("PROGRAM", program),
    ]
    fy = 620
    for label, value in fields:
        draw.text((150, fy), label, font=label_font, fill=GOLD)
        draw.text((150, fy + 44), value, font=value_font, fill=CREAM)
        fy += 130

    # bottom band
    draw.rounded_rectangle([40, H - 150, W - 40, H - 40], radius=24, fill=(8, 32, 62))
    draw.rectangle([40, H - 150, W - 40, H - 110], fill=(8, 32, 62))
    _centered_text(
        draw, W // 2, H - 110,
        "This card certifies enrollment in the Heribhee Studio training program.",
        _font("WorkSans-Regular.ttf", 20), CREAM, anchor="ma",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "student_id_card.png"
    return buf


# ---------------------------------------------------------------------------
# Certificate of completion
# ---------------------------------------------------------------------------
def generate_certificate(name: str, program: str, date_str: str, signatory: str = "Heribhee Studio") -> io.BytesIO:
    W, H = 1600, 1130
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)

    # diagonal boundary between the cream header and the navy body
    split_left, split_right = int(H * 0.40), int(H * 0.30)
    draw.polygon(
        [(0, split_left), (W, split_right), (W, H), (0, H)],
        fill=NAVY,
    )

    def y_boundary(x):
        # y of the diagonal line at a given x, for placing text safely on one side
        return split_left + (split_right - split_left) * (x / W)

    # outer gold border
    _gold_border(draw, [30, 30, W - 30, H - 30], width=5, radius=8)
    _gold_border(draw, [46, 46, W - 46, H - 46], width=2, radius=6)

    # logo + brand (cream zone)
    logo = _load_logo(120)
    if logo:
        img.paste(logo, (W // 2 - 60, 55), logo)
    _centered_text(draw, W // 2, 190, "HERIBHEE STUDIO", _font("Outfit-Bold.ttf", 38), NAVY, anchor="ma")
    _centered_text(draw, W // 2, 250, "CERTIFICATE OF COMPLETION", _font("Outfit-Bold.ttf", 54), GOLD, anchor="ma")
    draw.line([(W // 2 - 250, 320), (W // 2 + 250, 320)], fill=GOLD, width=3)
    _centered_text(draw, W // 2, 350, "PROUDLY PRESENTED TO", _font("WorkSans-Bold.ttf", 22), NAVY, anchor="ma")

    # name (navy zone — sits safely below the diagonal at every x it touches)
    name_y = 480
    _centered_text(draw, W // 2, name_y, name, _font("Italiana-Regular.ttf", 84), WHITE, anchor="ma")
    draw.line([(W // 2 - 300, name_y + 105), (W // 2 + 300, name_y + 105)], fill=GOLD, width=2)

    body = (
        f"for successfully completing the {program} training,\n"
        "demonstrating dedication, creativity and a genuine commitment\n"
        "to mastering the craft of AI-powered content creation."
    )
    body_font = _font("WorkSans-Regular.ttf", 28)
    y = name_y + 150
    for line in body.split("\n"):
        _centered_text(draw, W // 2, y, line, body_font, CREAM, anchor="ma")
        y += 42

    # signature + date footer (navy zone)
    draw.line([(180, 950), (560, 950)], fill=GOLD_LIGHT, width=2)
    draw.text((180, 960), signatory, font=_font("WorkSans-Bold.ttf", 26), fill=CREAM)
    draw.text((180, 995), "Program Director", font=_font("WorkSans-Regular.ttf", 20), fill=GOLD_LIGHT)

    draw.line([(W - 560, 950), (W - 180, 950)], fill=GOLD_LIGHT, width=2)
    _centered_text(draw, W - 370, 960, date_str, _font("WorkSans-Bold.ttf", 26), CREAM, anchor="ma")
    _centered_text(draw, W - 370, 995, "Date Issued", _font("WorkSans-Regular.ttf", 20), GOLD_LIGHT, anchor="ma")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "certificate.png"
    return buf
