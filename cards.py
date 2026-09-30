
"""Branded image-card helpers for Heribhee Academy / Heribhee Studio.

Certificate and ID card designs tuned to match the reference visuals:
- cream background with navy/gold accents
- certificate keeps the supplied layout but updates the name font and wording
- student ID uses a portrait layout with softly rounded corners

Assets used when available in the repo root:
- logo.png
- signature.jpg
- Montserrat / Poppins / Outfit / Work Sans / Italiana font files
"""
from io import BytesIO
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

try:
    import qrcode
except Exception:
    qrcode = None

ROOT = Path(__file__).resolve().parent

NAVY = "#091C45"
NAVY_2 = "#0D235B"
GOLD = "#D4AF5A"
GOLD_2 = "#E4C57C"
CREAM = "#F5F1E8"
WHITE = "#FFFFFF"
INK = "#243041"
MUTED = "#6E7075"
LIGHT_LINE = "#D8D0BF"

CERT_MESSAGE = (
    "This is to certify that the above-named participant has successfully completed "
    "the AI Video Making Training program and has acquired practical skills in AI "
    "image creation, image editing, digital content production, and the effective "
    "use of social media tools for content creation and audience engagement."
)


def _existing(paths):
    for p in paths:
        p = Path(p)
        if p.exists():
            return p
    return None


def _font(size, bold=False, elegant=False, preferred=None):
    candidates = []
    if preferred:
        if isinstance(preferred, str):
            preferred = [preferred]
        for name in preferred:
            candidates += [ROOT / name]
    if elegant:
        candidates += [ROOT / "Italiana-Regular.ttf"]
    if bold:
        candidates += [
            ROOT / "Montserrat-Bold.ttf",
            ROOT / "Poppins-Bold.ttf",
            ROOT / "Outfit-Bold.ttf",
            ROOT / "WorkSans-Bold.ttf",
            "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf",
            "/usr/share/fonts/truetype/poppins/Poppins-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        candidates += [
            ROOT / "Montserrat-Regular.ttf",
            ROOT / "Poppins-Regular.ttf",
            ROOT / "Outfit-Regular.ttf",
            ROOT / "WorkSans-Regular.ttf",
            "/usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf",
            "/usr/share/fonts/truetype/poppins/Poppins-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    for path in candidates:
        try:
            path = Path(path)
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_text(draw, text, max_width, start_size, min_size=18, bold=False, elegant=False, preferred=None):
    text = (text or "").strip()
    for size in range(start_size, min_size - 1, -2):
        f = _font(size, bold=bold, elegant=elegant, preferred=preferred)
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            return f
    return _font(min_size, bold=bold, elegant=elegant, preferred=preferred)


def _text_multiline_center(draw, text, center_x, top_y, max_width, font, fill, spacing=8):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        w = draw.textbbox((0, 0), test, font=font)[2]
        if w <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    y = top_y
    for line in lines:
        draw.text((center_x, y), line, anchor="ma", font=font, fill=fill)
        box = draw.textbbox((0, 0), line, font=font)
        y += (box[3] - box[1]) + spacing
    return y


def _png(img, name):
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    out.name = name
    return out


def _add_corner_arc(draw, box, start, end, fill, width):
    draw.arc(box, start=start, end=end, fill=fill, width=width)


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def _paste_logo(img, center_x, top_y, max_size):
    logo_path = ROOT / "logo.png"
    if not logo_path.exists():
        return
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((max_size, max_size), Image.LANCZOS)
        img.paste(logo, (center_x - logo.width // 2, top_y), logo)
    except Exception:
        pass


def _paste_signature(img, x, y, max_w=260, max_h=110):
    sig_path = ROOT / "signature.jpg"
    if not sig_path.exists():
        return
    try:
        sig = Image.open(sig_path).convert("RGBA")
        # make white background transparent-ish
        datas = []
        for r, g, b, a in sig.getdata():
            if r > 235 and g > 235 and b > 235:
                datas.append((255, 255, 255, 0))
            else:
                datas.append((r, g, b, a))
        sig.putdata(datas)
        sig.thumbnail((max_w, max_h), Image.LANCZOS)
        img.paste(sig, (x, y), sig)
    except Exception:
        pass


def _make_qr(data, size=180):
    if not qrcode or not data:
        return None
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size), Image.LANCZOS)
    return img


def generate_certificate(name, program, date_str, certificate_no=None):
    W, H = 1600, 1100
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # Decorative corner accents similar to the supplied design
    arc_boxes = [
        (-140, -140, 260, 260, 20, 110),
        (W - 260, -140, W + 140, 260, 70, 160),
        (-140, H - 260, 260, H + 140, 290, 20),
        (W - 260, H - 260, W + 140, H + 140, 200, 290),
    ]
    for x1, y1, x2, y2, s, e in arc_boxes:
        _add_corner_arc(d, (x1, y1, x2, y2), s, e, NAVY, 42)
        _add_corner_arc(d, (x1 + 22, y1 + 22, x2 - 22, y2 - 22), s, e, GOLD, 14)

    _paste_logo(img, W // 2, 70, 115)

    d.text((W // 2, 205), "HERIBHEE STUDIO", anchor="mm", font=_font(54, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=NAVY)
    d.text((W // 2, 283), "CERTIFICATE OF COMPLETION", anchor="mm", font=_font(60, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=GOLD)
    d.line((500, 323, 1100, 323), fill=GOLD_2, width=3)

    d.text((W // 2, 370), "PROUDLY PRESENTED TO", anchor="mm", font=_font(24, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=INK)

    name_font = _fit_text(d, name, 950, 70, 40, bold=False, elegant=False, preferred=["Montserrat-Regular.ttf", "Poppins-Regular.ttf"])
    d.text((W // 2, 462), name, anchor="mm", font=name_font, fill=INK)
    d.line((515, 510, 1085, 510), fill=GOLD_2, width=2)

    body_font = _font(27, False, preferred=["Montserrat-Regular.ttf", "Poppins-Regular.ttf"])
    _text_multiline_center(d, CERT_MESSAGE, W // 2, 565, 980, body_font, fill="#575B63", spacing=8)

    # signature block left
    _paste_signature(img, 175, 835)
    d.line((140, 955, 510, 955), fill=LIGHT_LINE, width=2)
    d.text((140, 988), "Heribhee Studio", anchor="la", font=_font(26, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=INK)
    d.text((140, 1022), "Program Director", anchor="la", font=_font(18, False, preferred=["Montserrat-Regular.ttf", "Poppins-Regular.ttf"]), fill=MUTED)

    # date block right
    d.line((1090, 955, 1460, 955), fill=LIGHT_LINE, width=2)
    d.text((1275, 922), date_str, anchor="mm", font=_font(28, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=INK)
    d.text((1275, 1022), "Date Issued", anchor="mm", font=_font(18, False, preferred=["Montserrat-Regular.ttf", "Poppins-Regular.ttf"]), fill=MUTED)

    if certificate_no:
        d.text((W // 2, 1048), f"Certificate No: {certificate_no}", anchor="mm", font=_font(15, False, preferred=["Montserrat-Regular.ttf", "Poppins-Regular.ttf"]), fill="#88806F")

    return _png(img, "heribhee_certificate.png")


def generate_id_card(name, occupation, student_no, program):
    W, H = 700, 1200
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # main rounded card
    card = Image.new("RGBA", (W, H), CREAM)
    mask = _rounded_mask((W, H), 36)
    base.paste(card, (0, 0), mask)
    d = ImageDraw.Draw(base)

    # outer and inner rounded borders
    d.rounded_rectangle((8, 8, W - 8, H - 8), radius=36, outline=GOLD, width=4)
    d.rounded_rectangle((22, 22, W - 22, H - 22), radius=28, outline=NAVY_2, width=2)

    # top header
    d.rounded_rectangle((22, 22, W - 22, 185), radius=28, fill=NAVY)
    d.rectangle((22, 140, W - 22, 185), fill=NAVY)

    # logo and headings
    logo_path = ROOT / "logo.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((88, 88), Image.LANCZOS)
            base.paste(logo, (38, 42), logo)
        except Exception:
            pass

    d.text((128, 58), "HERIBHEE STUDIO", anchor="la", font=_font(31, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=GOLD_2)
    d.text((128, 105), "AI VIDEO & MOVIE ACADEMY", anchor="la", font=_font(16, False, preferred=["Montserrat-Regular.ttf", "Poppins-Regular.ttf"]), fill=WHITE)

    # small ornament
    d.text((W // 2, 230), "◇", anchor="mm", font=_font(24, False, preferred=["Montserrat-Regular.ttf", "Poppins-Regular.ttf"]), fill=GOLD)

    # name
    name_font = _fit_text(d, name, W - 90, 34, 20, bold=False, elegant=False, preferred=["Italiana-Regular.ttf", "Montserrat-Regular.ttf", "Poppins-Regular.ttf"])
    d.text((W // 2, 298), name, anchor="mm", font=name_font, fill=INK)
    d.line((230, 362, 470, 362), fill=GOLD, width=3)

    # student id block
    y = 410
    d.text((W // 2, y), "STUDENT ID", anchor="mm", font=_font(15, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=GOLD)
    d.text((W // 2, y + 44), student_no, anchor="mm", font=_font(36, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=NAVY)
    d.line((80, y + 82, W - 80, y + 82), fill="#E2DDCF", width=2)

    # role block
    y2 = y + 122
    d.text((W // 2, y2), "ROLE", anchor="mm", font=_font(15, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=GOLD)
    occ_font = _fit_text(d, occupation or "Student", W - 90, 26, 18, bold=True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"])
    d.text((W // 2, y2 + 40), occupation or "Student", anchor="mm", font=occ_font, fill=NAVY)
    d.line((80, y2 + 82, W - 80, y2 + 82), fill="#E2DDCF", width=2)

    # program block
    y3 = y2 + 122
    d.text((W // 2, y3), "PROGRAM", anchor="mm", font=_font(15, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=GOLD)
    prog_label = "AI Video Making Training"
    program_font = _fit_text(d, prog_label, W - 90, 23, 16, bold=True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"])
    d.text((W // 2, y3 + 40), prog_label, anchor="mm", font=program_font, fill=NAVY)
    d.line((80, y3 + 82, W - 80, y3 + 82), fill="#E2DDCF", width=2)

    # QR area
    qr_data = None
    bot_username = os.getenv("BOT_USERNAME", "").lstrip("@")
    if bot_username:
        qr_data = f"https://t.me/{bot_username}"
    elif os.getenv("CRASH_COURSE_LINK"):
        qr_data = os.getenv("CRASH_COURSE_LINK")
    qr_img = _make_qr(qr_data, 160)
    qr_x = W // 2 - 90
    qr_y = 815
    d.rounded_rectangle((qr_x - 8, qr_y - 8, qr_x + 168, qr_y + 168), radius=18, outline=GOLD, width=2, fill=WHITE)
    if qr_img:
        base.paste(qr_img.convert("RGBA"), (qr_x, qr_y))
    else:
        d.rectangle((qr_x + 16, qr_y + 16, qr_x + 144, qr_y + 144), outline=NAVY, width=3)
        d.text((W // 2, qr_y + 80), "CHAT", anchor="mm", font=_font(32, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=NAVY)
    d.text((W // 2, qr_y + 190), "SCAN TO CHAT", anchor="mm", font=_font(14, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"]), fill=GOLD)

    # footer
    d.rectangle((22, H - 120, W - 22, H - 22), fill=NAVY)
    footer_font = _font(17, True, preferred=["Montserrat-Bold.ttf", "Poppins-Bold.ttf"])
    d.text((W // 2, H - 78), "This card certifies enrollment in the", anchor="mm", font=footer_font, fill=WHITE)
    d.text((W // 2, H - 52), "Heribhee Studio training program.", anchor="mm", font=footer_font, fill=WHITE)

    # flatten onto cream background to keep nice corners in some viewers
    final = Image.new("RGB", (W, H), CREAM)
    final.paste(base, (0, 0), base)
    return _png(final, "heribhee_student_id.png")
