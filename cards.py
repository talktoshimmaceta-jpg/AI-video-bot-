"""Generates branded student ID cards and completion certificates as PNGs.

Uses only Pillow (no photos required — name + role, matching the
Heribhee Studio navy-and-gold branding).
"""
import io
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None

HERE = os.path.dirname(os.path.abspath(__file__))
# Fonts can live either in a fonts/ subfolder or directly in the repo root —
# whichever is found first is used, so no need to reorganize files on GitHub.
_fonts_subdir = os.path.join(HERE, "fonts")
FONT_DIR = _fonts_subdir if os.path.isdir(_fonts_subdir) else HERE
LOGO_PATH = os.getenv("LOGO_FILE", os.path.join(HERE, "logo.png"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "")


def _resolve_signature_path():
    """SIGNATURE_FILE can be set explicitly; otherwise look for a
    signature.<ext> file in the repo root under common extensions, so it
    doesn't matter which format the signed photo was uploaded as."""
    explicit = os.getenv("SIGNATURE_FILE")
    if explicit:
        return os.path.join(HERE, explicit) if not os.path.isabs(explicit) else explicit
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(HERE, f"signature.{ext}")
        if os.path.exists(p):
            return p
    return os.path.join(HERE, "signature.png")


SIGNATURE_PATH = _resolve_signature_path()

NAVY = (5, 22, 46)
NAVY_DEEP = (3, 14, 30)
GOLD = (223, 178, 95)
GOLD_LIGHT = (240, 210, 150)
CREAM = (245, 240, 228)
WHITE = (255, 255, 255)


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _centered_text(draw, cx, y, text, font, fill, anchor="ma", align="left"):
    draw.text((cx, y), text, font=font, fill=fill, anchor=anchor, align=align)


def _isolate_shield(img: Image.Image, tolerance: int = 80) -> Image.Image:
    """Extracts just the shield emblem from the full logo file (which has a
    busy navy circuit-pattern background and the 'HERIBHEE STUDIO' wordmark
    underneath it), as a clean transparent cutout with its internal navy
    shading intact — not a hollowed-out silhouette.

    Naive color-distance keying doesn't work well here: the background has
    everything from near-black navy (very close to the shield's own
    interior fill) to bright glowing blue lines (color-close to nothing in
    particular), so no single threshold cleanly separates "background" from
    "artwork" everywhere at once. Instead this treats it as a shape problem:
    - mark pixels that are clearly far from the background color as
      "foreground" candidates (circuit lines included — that's fine)
    - take the single largest connected blob of those — the shield is one
      big solid shape, while the circuit lines and each wordmark letter are
      comparatively small, separate pieces, so the shield always wins
    - fill any holes in that blob (the enclosed navy interior reads as
      "background-colored" by the threshold, so it would otherwise punch
      a hole straight through the middle of the shield)
    Vectorized with numpy + scipy's connected-component labeling."""
    from scipy import ndimage

    img = img.convert("RGBA")
    arr = np.array(img)
    rgb = arr[:, :, :3].astype(np.int32)
    h, w = rgb.shape[:2]
    corners = np.array([rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]])
    bg = corners.mean(axis=0)
    dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    fg = dist >= tolerance

    labels, n = ndimage.label(fg)
    if n == 0:
        return _content_bbox(img)
    sizes = ndimage.sum(fg, labels, index=np.arange(1, n + 1))
    biggest = int(np.argmax(sizes)) + 1
    mask = ndimage.binary_fill_holes(labels == biggest)

    arr[:, :, 3] = np.where(mask, arr[:, :, 3], 0)
    return _content_bbox(Image.fromarray(arr, "RGBA"), pad=6)


def _content_bbox(img: Image.Image, pad: int = 0):
    arr = np.array(img)
    ys, xs = np.where(arr[:, :, 3] > 10)
    if len(xs) == 0:
        return img
    x0, x1 = max(0, xs.min() - pad), min(arr.shape[1], xs.max() + pad)
    y0, y1 = max(0, ys.min() - pad), min(arr.shape[0], ys.max() + pad)
    return img.crop((x0, y0, x1, y1))


_LOGO_CACHE = {}


def _load_icon(max_size):
    """The shield/brain/globe emblem alone, cleanly cut out — cached after
    the first (slightly heavier) extraction."""
    if "icon" not in _LOGO_CACHE:
        if not os.path.exists(LOGO_PATH):
            _LOGO_CACHE["icon"] = None
        else:
            raw = Image.open(LOGO_PATH).convert("RGBA")
            _LOGO_CACHE["icon"] = _isolate_shield(raw, tolerance=80)
    icon = _LOGO_CACHE["icon"]
    if icon is None:
        return None
    ico = icon.copy()
    ico.thumbnail((max_size, max_size), Image.LANCZOS)
    return ico


def _load_signature(max_width, color=None):
    """Loads a photo of a signature (blue/black pen on paper, possibly with
    shadows, wood-grain or uneven lighting in the background) and extracts
    just the ink strokes as a transparent PNG, recolored to `color`.

    Brightness alone isn't reliable here — a shadow in the photo can be as
    dark as the ink. Instead this keys on hue: pen ink reads distinctly
    blue/dark against a warm paper or wood background, so it isolates
    pixels where the blue channel stands out from red+green ("blueness"),
    which cleanly separates ink from shadows. Vectorized with numpy."""
    if not os.path.exists(SIGNATURE_PATH):
        return None
    color = color or NAVY_DEEP
    sig = Image.open(SIGNATURE_PATH).convert("RGB")
    sig.thumbnail((max_width * 3, max_width * 3), Image.LANCZOS)
    arr = np.array(sig).astype(np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    blueness = b - (r + g) / 2
    alpha = np.clip((blueness - 8) * 10, 0, 255).astype(np.uint8)

    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        return None
    pad = 10
    x0, x1 = max(0, xs.min() - pad), min(alpha.shape[1], xs.max() + pad)
    y0, y1 = max(0, ys.min() - pad), min(alpha.shape[0], ys.max() + pad)
    alpha = alpha[y0:y1, x0:x1]

    out = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = color
    out[:, :, 3] = alpha
    result = Image.fromarray(out, "RGBA")
    result.thumbnail((max_width, max_width), Image.LANCZOS)
    return result


def _make_qr(data: str, box_size: int = 8, border: int = 2):
    if not qrcode:
        return None
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color=NAVY_DEEP, back_color=CREAM).convert("RGBA")


def _gold_border(draw, box, width=4, radius=28):
    draw.rounded_rectangle(box, radius=radius, outline=GOLD, width=width)


# ---------------------------------------------------------------------------
# Student ID card
# ---------------------------------------------------------------------------
def generate_id_card(name: str, role: str, student_no: str, program: str) -> io.BytesIO:
    # Narrower, badge-like proportions (closer to a standard portrait ID
    # card). Navy header and footer bands frame the card top and bottom;
    # everything in between is clean cream, centered on the vertical axis —
    # no side "STUDENT" spine.
    #
    # The content's total height depends on how many lines the name/fields
    # wrap to, so the layout is computed once on a scratch canvas first,
    # and the real image is then built at exactly the height that needs —
    # never guessing a fixed height and hoping the footer doesn't collide
    # with the QR code.
    W = 840
    cx = W // 2
    label_color = (150, 120, 55)
    header_bottom = 260
    scratch = ImageDraw.Draw(Image.new("RGB", (W, 10)))

    def layout(draw_):
        name_size = 62
        name_font = _font("Italiana-Regular.ttf", name_size)
        max_name_w = W - 160
        while draw_.textlength(name, font=name_font) > max_name_w and name_size > 30:
            name_size -= 2
            name_font = _font("Italiana-Regular.ttf", name_size)
        name_y = header_bottom + 55

        label_font = _font("WorkSans-Bold.ttf", 32)
        value_font = _font("WorkSans-Bold.ttf", 42)
        fields = [("STUDENT ID", student_no), ("ROLE", role), ("PROGRAM", program)]
        field_col_width = W - 220
        field_layout = []
        fy = name_y + 160
        for label, value in fields:
            words, line, lines = value.split(), "", []
            for w_ in words:
                trial = (line + " " + w_).strip()
                if draw_.textlength(trial, font=value_font) > field_col_width:
                    lines.append(line)
                    line = w_
                else:
                    line = trial
            lines.append(line)
            field_layout.append((label, lines, fy))
            rule_y = fy + 52 + len(lines) * 52 + 16
            fy = rule_y + 48
        return name_font, name_y, label_font, value_font, field_layout, fy

    _, name_y, label_font, value_font, field_layout, fy = layout(scratch)

    qr_data = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else None
    qsize, qy = 190, None
    if qr_data:
        qy = fy + 20
        content_bottom = qy + qsize + 16 + 16 + 30  # QR + pad + "SCAN TO CHAT" + gap
    else:
        content_bottom = fy + 10
    footer_h = 150
    H = content_bottom + footer_h + 20

    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)

    # outer gold frame — soft, generously rounded corners (like a road sign)
    _gold_border(draw, [24, 24, W - 24, H - 24], width=5, radius=60)
    _gold_border(draw, [40, 40, W - 40, H - 40], width=2, radius=50)

    # top header band
    draw.rounded_rectangle([40, 40, W - 40, header_bottom], radius=44, fill=NAVY)
    draw.rectangle([40, header_bottom - 44, W - 40, header_bottom], fill=NAVY)

    logo = _load_icon(128)
    if logo:
        img.paste(logo, (58, 56), logo)

    _centered_text(draw, cx, 78, "HERIBHEE STUDIO", _font("Outfit-Bold.ttf", 50), GOLD_LIGHT, anchor="ma")
    _centered_text(draw, cx, 150, "AI VIDEO & MOVIE ACADEMY", _font("WorkSans-Regular.ttf", 28), CREAM, anchor="ma")

    # small gold diamond emblem instead of a photo
    ex, ey, es = cx, header_bottom + 25, 15
    draw.polygon(
        [(ex, ey - es), (ex + es, ey), (ex, ey + es), (ex - es, ey)],
        outline=GOLD, width=3,
    )

    # name — the centerpiece, sized to fit the card width
    name_font, name_y, _, _, _, _ = layout(draw)
    _centered_text(draw, cx, name_y, name, name_font, NAVY, anchor="ma")

    # short divider — centered under the name, bolder and a touch wider
    draw.line([(cx - 110, name_y + 112), (cx + 110, name_y + 112)], fill=GOLD, width=5)

    # fields, larger + bolder type, fully centered, each with a thin rule underneath
    rule_x0, rule_x1 = 130, W - 130
    for label, lines, fy_ in field_layout:
        _centered_text(draw, cx, fy_, label, label_font, label_color, anchor="ma")
        for li, ln in enumerate(lines):
            _centered_text(draw, cx, fy_ + 52 + li * 52, ln, value_font, NAVY, anchor="ma")
        rule_y = fy_ + 52 + len(lines) * 52 + 16
        draw.line([(rule_x0, rule_y), (rule_x1, rule_y)], fill=(214, 205, 180), width=1)

    # QR code — centered directly under the fields, opens a chat with the
    # bot when scanned
    if qr_data:
        qr_img = _make_qr(qr_data, box_size=6, border=1)
        if qr_img:
            qr_img = qr_img.resize((qsize, qsize), Image.NEAREST)
            pad = 16
            qx = cx - qsize // 2
            draw.rounded_rectangle(
                [qx - pad, qy - pad, qx + qsize + pad, qy + qsize + pad],
                radius=16, outline=GOLD, width=2,
            )
            img.paste(qr_img, (qx, qy))
            _centered_text(
                draw, cx, qy + qsize + pad + 18,
                "SCAN TO CHAT", _font("WorkSans-Bold.ttf", 22), label_color, anchor="ma",
            )

    # bottom band — comfortably clear of the outer border, not sitting on it
    footer_top = H - footer_h
    draw.rounded_rectangle([40, footer_top, W - 40, H - 40], radius=40, fill=NAVY)
    draw.rectangle([40, footer_top, W - 40, footer_top + 40], fill=NAVY)
    _centered_text(
        draw, cx, footer_top + (footer_h - 40) // 2,
        "This card certifies enrollment in the\nHeribhee Studio training program.",
        _font("WorkSans-Bold.ttf", 23), CREAM, anchor="mm", align="center",
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

    # Corner accents: the brand's OWN shield artwork, rotated so only its
    # own curved edge shows — peeking in from the top-left and bottom-right
    # corners, the way HP's wedge echoes the curve of their own logotype —
    # instead of a full diagonal color block, a boxed border, or a
    # generic hand-drawn shape.
    icon = _load_icon(700)
    if icon:
        tl = icon.rotate(-52, expand=True, resample=Image.BICUBIC)
        ox, oy = -int(tl.width * 0.60), -int(tl.height * 0.62)
        img.paste(tl, (ox, oy), tl)

        from PIL import ImageOps
        br = ImageOps.mirror(ImageOps.flip(tl))
        img.paste(br, (W - tl.width - ox, H - tl.height - oy), br)

    # logo + brand — icon only here since the wordmark is set in type below
    if icon:
        icon_small = icon.copy()
        icon_small.thumbnail((150, 150), Image.LANCZOS)
        img.paste(icon_small, (W // 2 - icon_small.width // 2, 45), icon_small)
    _centered_text(draw, W // 2, 210, "HERIBHEE STUDIO", _font("Outfit-Bold.ttf", 48), NAVY, anchor="ma")
    _centered_text(draw, W // 2, 268, "CERTIFICATE OF COMPLETION", _font("Outfit-Bold.ttf", 56), GOLD, anchor="ma")
    draw.line([(W // 2 - 260, 342), (W // 2 + 260, 342)], fill=GOLD, width=3)
    _centered_text(draw, W // 2, 358, "PROUDLY PRESENTED TO", _font("WorkSans-Bold.ttf", 22), NAVY, anchor="ma")

    # name — the centerpiece
    name_y = 430
    name_size = 84
    name_font = _font("Italiana-Regular.ttf", name_size)
    max_name_w = W - 480
    while draw.textlength(name, font=name_font) > max_name_w and name_size > 44:
        name_size -= 2
        name_font = _font("Italiana-Regular.ttf", name_size)
    _centered_text(draw, W // 2, name_y, name, name_font, NAVY, anchor="ma")
    draw.line([(W // 2 - 260, name_y + 108), (W // 2 + 260, name_y + 108)], fill=GOLD, width=2)

    body = (
        f"for successfully completing the {program} training,\n"
        "demonstrating dedication, creativity and a genuine commitment\n"
        "to mastering the craft of AI-powered content creation."
    )
    body_font = _font("WorkSans-Regular.ttf", 26)
    y = name_y + 155
    for line in body.split("\n"):
        _centered_text(draw, W // 2, y, line, body_font, (60, 58, 50), anchor="ma")
        y += 40

    # signature + date footer
    sig = _load_signature(280, color=NAVY_DEEP)
    if sig:
        sx = 210 + (380 - sig.width) // 2
        img.paste(sig, (sx, 940 - sig.height - 6), sig)
    draw.line([(210, 940), (590, 940)], fill=(180, 170, 145), width=2)
    draw.text((210, 950), signatory, font=_font("WorkSans-Bold.ttf", 24), fill=NAVY)
    draw.text((210, 984), "Program Director", font=_font("WorkSans-Regular.ttf", 18), fill=(120, 112, 95))

    draw.line([(W - 590, 940), (W - 210, 940)], fill=(180, 170, 145), width=2)
    _centered_text(draw, W - 400, 950, date_str, _font("WorkSans-Bold.ttf", 24), NAVY, anchor="ma")
    _centered_text(draw, W - 400, 984, "Date Issued", _font("WorkSans-Regular.ttf", 18), (120, 112, 95), anchor="ma")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "certificate.png"
    return buf
