"""Simple image-card helpers for the Heribhee Academy Telegram bot.

Replace this file with your original cards.py later if you have a branded version.
"""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _png(img):
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    out.name = "card.png"
    return out


def generate_id_card(name, category, student_no, program):
    img = Image.new("RGB", (1200, 700), "white")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, 1160, 660), radius=35, outline="black", width=4)
    d.text((90, 90), "HERIBHEE ACADEMY", font=_font(54, True), fill="black")
    d.text((90, 175), program, font=_font(30), fill="black")
    d.line((90, 235, 1110, 235), fill="black", width=2)
    d.text((90, 290), name, font=_font(50, True), fill="black")
    d.text((90, 380), f"Student ID: {student_no}", font=_font(38, True), fill="black")
    d.text((90, 450), f"Category: {category}", font=_font(32), fill="black")
    d.text((90, 575), "Official Student Identification", font=_font(25), fill="black")
    return _png(img)


def generate_certificate(name, program, date_str):
    img = Image.new("RGB", (1600, 1100), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((45, 45, 1555, 1055), outline="black", width=5)
    d.rectangle((70, 70, 1530, 1030), outline="black", width=2)
    d.text((800, 155), "HERIBHEE ACADEMY", anchor="mm", font=_font(58, True), fill="black")
    d.text((800, 270), "CERTIFICATE OF COMPLETION", anchor="mm", font=_font(52, True), fill="black")
    d.text((800, 390), "This certifies that", anchor="mm", font=_font(30), fill="black")
    d.text((800, 500), name, anchor="mm", font=_font(64, True), fill="black")
    d.text((800, 610), "has successfully completed", anchor="mm", font=_font(30), fill="black")
    d.text((800, 700), program, anchor="mm", font=_font(40, True), fill="black")
    d.text((800, 850), f"Issued: {date_str}", anchor="mm", font=_font(28), fill="black")
    return _png(img)
