"""Branded image-card helpers for Heribhee Academy.

Uses the existing repo assets when available:
- logo.png
- signature.jpg
- Outfit-Bold.ttf / Outfit-Regular.ttf
- WorkSans-Bold.ttf / WorkSans-Regular.ttf
- Italiana-Regular.ttf

Falls back gracefully if any asset is missing.
"""
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent

NAVY = "#0B1739"
NAVY_2 = "#142A63"
GOLD = "#D7B25D"
GOLD_2 = "#F0D78B"
CREAM = "#FAF8F2"
WHITE = "#FFFFFF"
INK = "#202631"
MUTED = "#5F6774"


def _font(size, bold=False, elegant=False):
    candidates = []
    if elegant:
        candidates += [ROOT / "Italiana-Regular.ttf"]
    if bold:
        candidates += [ROOT / "Outfit-Bold.ttf", ROOT / "WorkSans-Bold.ttf"]
    else:
        candidates += [ROOT / "Outfit-Regular.ttf", ROOT / "WorkSans-Regular.ttf"]
    candidates += [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ]
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def _png(img, name="card.png"):
    out = BytesIO()
    img.save(out, format="PNG", quality=95)
    out.seek(0)
    out.name = name
    return out


def _fit_text(draw, text, max_width, start_size, min_size=22, bold=False, elegant=False):
    text = (text or "").strip()
    for size in range(start_size, min_size - 1, -2):
        f = _font(size, bold=bold, elegant=elegant)
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            return f
    return _font(min_size, bold=bold, elegant=elegant)


def _rounded_image(path, size, radius=22):
    img = Image.open(path).convert("RGBA")
    img.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 0))
    x = (size[0] - img.width) // 2
    y = (size[1] - img.height) // 2
    canvas.alpha_composite(img, (x, y))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    canvas.putalpha(mask)
    return canvas


def generate_id_card(name, occupation, student_no, program):
    """Create a premium branded student ID card.

    `occupation` is deliberately shown instead of the broad category so the card
    tells people what the student actually does.
    """
    W, H = 1200, 700
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # Header / brand panel
    d.rounded_rectangle((28, 28, W - 28, H - 28), radius=42, fill=WHITE, outline=GOLD, width=4)
    d.rounded_rectangle((28, 28, W - 28, 235), radius=42, fill=NAVY)
    d.rectangle((28, 190, W - 28, 235), fill=NAVY)
    d.rectangle((28, 225, W - 28, 235), fill=GOLD)

    logo_path = ROOT / "logo.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((145, 145), Image.LANCZOS)
            # white badge behind logo
            d.ellipse((65, 55, 225, 215), fill=WHITE)
            img.paste(logo, (145 - logo.width // 2, 135 - logo.height // 2), logo)
        except Exception:
            pass

    d.text((260, 73), "HERIBHEE ACADEMY", font=_font(46, True), fill=WHITE)
    program_font = _fit_text(d, program, 820, 28, 20)
    d.text((260, 137), program, font=program_font, fill=GOLD_2)
    d.text((1010, 70), "STUDENT", font=_font(25, True), fill=GOLD_2, anchor="ra")
    d.text((1010, 108), "IDENTIFICATION", font=_font(25, True), fill=WHITE, anchor="ra")

    # Body
    d.text((85, 285), "STUDENT NAME", font=_font(21, True), fill=MUTED)
    name_font = _fit_text(d, name, 900, 48, 30, True)
    d.text((85, 325), name.upper(), font=name_font, fill=NAVY)

    d.text((85, 420), "OCCUPATION / CURRENT ROLE", font=_font(21, True), fill=MUTED)
    occ_font = _fit_text(d, occupation or "Academy Student", 900, 37, 24, True)
    d.text((85, 458), (occupation or "Academy Student"), font=occ_font, fill=INK)

    # Bottom info strip
    d.rounded_rectangle((75, 555, 1125, 635), radius=22, fill="#F1F4FA")
    d.text((105, 580), "STUDENT ID", font=_font(18, True), fill=MUTED)
    d.text((245, 576), student_no, font=_font(28, True), fill=NAVY)
    d.text((850, 580), "VERIFIED MEMBER", font=_font(19, True), fill=GOLD)

    # decorative mark
    d.ellipse((1035, 300, 1100, 365), fill=GOLD)
    d.ellipse((1054, 319, 1081, 346), fill=WHITE)

    return _png(img, "heribhee_student_id.png")


def generate_certificate(name, program, date_str, certificate_no=None):
    """Create a branded landscape certificate with logo and signature."""
    W, H = 1600, 1100
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # layered certificate border
    d.rectangle((28, 28, W - 28, H - 28), outline=NAVY, width=18)
    d.rectangle((52, 52, W - 52, H - 52), outline=GOLD, width=5)
    d.rectangle((70, 70, W - 70, H - 70), outline=NAVY_2, width=2)

    # corner ornaments
    for x, y, sx, sy in [(85, 85, 1, 1), (1515, 85, -1, 1), (85, 1015, 1, -1), (1515, 1015, -1, -1)]:
        d.line((x, y, x + sx * 110, y), fill=GOLD, width=6)
        d.line((x, y, x, y + sy * 110), fill=GOLD, width=6)
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=GOLD)

    logo_path = ROOT / "logo.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((135, 135), Image.LANCZOS)
            img.paste(logo, (800 - logo.width // 2, 105), logo)
        except Exception:
            pass

    d.text((800, 255), "HERIBHEE ACADEMY", anchor="mm", font=_font(48, True), fill=NAVY)
    d.text((800, 335), "Certificate of Completion", anchor="mm", font=_font(58, elegant=True), fill=GOLD)
    d.line((500, 385, 1100, 385), fill=GOLD, width=3)

    d.text((800, 455), "This certificate is proudly presented to", anchor="mm", font=_font(27), fill=MUTED)
    name_font = _fit_text(d, name, 1180, 68, 42, True, elegant=True)
    d.text((800, 555), name, anchor="mm", font=name_font, fill=NAVY)
    d.line((340, 615, 1260, 615), fill="#C9C3B3", width=2)

    d.text((800, 680), "for successfully completing", anchor="mm", font=_font(27), fill=MUTED)
    program_font = _fit_text(d, program, 1150, 42, 28, True)
    d.text((800, 740), program, anchor="mm", font=program_font, fill=INK)

    # Date block
    d.text((310, 900), date_str, anchor="mm", font=_font(28, True), fill=NAVY)
    d.line((165, 936, 455, 936), fill=NAVY, width=2)
    d.text((310, 968), "DATE ISSUED", anchor="mm", font=_font(19, True), fill=MUTED)

    # Signature block
    sig_path = ROOT / "signature.jpg"
    if sig_path.exists():
        try:
            sig = Image.open(sig_path).convert("RGBA")
            # make light/white areas transparent enough for clean placement
            sig.thumbnail((360, 130), Image.LANCZOS)
            img.paste(sig, (800 - sig.width // 2, 835), sig if sig.mode == "RGBA" else None)
        except Exception:
            pass
    d.line((655, 936, 945, 936), fill=NAVY, width=2)
    d.text((800, 968), "AUTHORIZED SIGNATURE", anchor="mm", font=_font(19, True), fill=MUTED)

    # Certificate number block
    cert_text = certificate_no or "HERIBHEE ACADEMY"
    d.text((1290, 900), cert_text, anchor="mm", font=_font(25, True), fill=NAVY)
    d.line((1135, 936, 1445, 936), fill=NAVY, width=2)
    d.text((1290, 968), "CERTIFICATE NUMBER", anchor="mm", font=_font(19, True), fill=MUTED)

    return _png(img, "heribhee_certificate.png")
