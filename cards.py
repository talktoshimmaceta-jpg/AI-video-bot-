from io import BytesIO
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont

try:
    import qrcode
except Exception:
    qrcode = None

ROOT = Path(__file__).resolve().parent
CERT_TEMPLATE = ROOT / "certificate_template.png"
ID_TEMPLATE = ROOT / "student_card_template.png"

NAVY = "#0C1F42"
GOLD = "#EEB83C"
BLACK = "#111111"
LIGHT = "#F0F3F9"
MUTED = "#9EAECF"


def _font(size, bold=False):
    # Exact Montserrat will be used automatically if you add these files to the repo.
    # Existing Heribhee font files remain valid fallbacks.
    names = (
        ["Montserrat-Bold.ttf", "Outfit-Bold.ttf", "WorkSans-Bold.ttf"]
        if bold else
        ["Montserrat-Regular.ttf", "Outfit-Regular.ttf", "WorkSans-Regular.ttf"]
    )
    system = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for p in [ROOT / n for n in names] + [Path(p) for p in system]:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _fit_font(draw, text, max_width, start_size, min_size=24, bold=True):
    for size in range(start_size, min_size - 1, -2):
        f = _font(size, bold=bold)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_width:
            return f
    return _font(min_size, bold=bold)


def _png(img, filename):
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    out.name = filename
    return out


def _make_qr(data, size):
    if not qrcode or not data:
        return None
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(data)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return qimg.resize((size, size), Image.LANCZOS)


def validate_assets():
    missing = []
    if not CERT_TEMPLATE.exists():
        missing.append(CERT_TEMPLATE.name)
    if not ID_TEMPLATE.exists():
        missing.append(ID_TEMPLATE.name)
    return missing


def _split_name(name):
    """At most two close lines so long student names still fit cleanly."""
    words = (name or "").strip().split()
    if len(words) <= 2:
        return [" ".join(words)] if words else [""]
    # balance words over two lines
    best = None
    for cut in range(1, len(words)):
        a, b = " ".join(words[:cut]), " ".join(words[cut:])
        score = abs(len(a) - len(b))
        if best is None or score < best[0]:
            best = (score, a, b)
    return [best[1], best[2]]


def generate_id_card(name, occupation, student_no, program=None):
    if not ID_TEMPLATE.exists():
        raise FileNotFoundError(f"Missing {ID_TEMPLATE.name}")

    img = Image.open(ID_TEMPLATE).convert("RGB")
    d = ImageDraw.Draw(img)
    W, H = img.size

    # Student name: centered, with tight two-line spacing when necessary.
    lines = _split_name(name)
    if len(lines) == 1:
        f = _fit_font(d, lines[0], 650, 58, 30, bold=True)
        d.text((W // 2, 450), lines[0], anchor="mm", font=f, fill=LIGHT)
    else:
        f1 = _fit_font(d, lines[0], 650, 52, 28, bold=True)
        f2 = _fit_font(d, lines[1], 650, 52, 28, bold=True)
        d.text((W // 2, 437), lines[0], anchor="mm", font=f1, fill=LIGHT)
        d.text((W // 2, 476), lines[1], anchor="mm", font=f2, fill=LIGHT)

    # Occupation/current role goes inside the approved gold pill.
    role = (occupation or "Academy Student").strip()
    role_font = _fit_font(d, role, 410, 30, 18, bold=True)
    d.text((W // 2, 575), role, anchor="mm", font=role_font, fill=GOLD)

    # Real QR replaces the template's blank QR space.
    bot_username = os.getenv("BOT_USERNAME", "").lstrip("@")
    qr_data = f"https://t.me/{bot_username}" if bot_username else os.getenv("PAID_CLASS_LINK", "") or os.getenv("CRASH_COURSE_LINK", "")
    qr = _make_qr(qr_data, 220)
    if qr:
        img.paste(qr, (340, 723))
    else:
        d.text((W // 2, 835), "QR", anchor="mm", font=_font(54, True), fill=BLACK)

    # Student number is deliberately higher than the old version so it never sits on the border.
    sid = (student_no or "").strip()
    sid_font = _fit_font(d, sid, 620, 54, 30, bold=True)
    d.text((132, 1185), sid, anchor="la", font=sid_font, fill=LIGHT)

    return _png(img, "heribhee_student_card.png")


def generate_certificate(name, program, date_str, certificate_no=None):
    if not CERT_TEMPLATE.exists():
        raise FileNotFoundError(f"Missing {CERT_TEMPLATE.name}")

    img = Image.open(CERT_TEMPLATE).convert("RGB")
    d = ImageDraw.Draw(img)
    W, H = img.size

    # Approved design is already complete. Only name and original issue date are dynamic.
    name = (name or "").strip()
    name_font = _fit_font(d, name, int(W * 0.62), 58, 34, bold=False)
    d.text((W // 2, 447), name, anchor="mm", font=name_font, fill="#0A2348")

    date_font = _fit_font(d, date_str, 280, 25, 18, bold=True)
    # Date sits directly on the right-hand line as requested.
    d.text((1091, 850), date_str, anchor="mm", font=date_font, fill=BLACK)

    return _png(img, "heribhee_certificate.png")
