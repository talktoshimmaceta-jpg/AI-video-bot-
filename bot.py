import asyncio
import csv
import io
import logging
import os
import sqlite3
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
PROGRAM = os.getenv("PROGRAM_NAME", "AI Video & Movie Making Training")
PRICE_FULL = int(os.getenv("PRICE_FULL", "5000"))
PRICE_HALF = int(os.getenv("PRICE_HALF", "2500"))
BANK_DETAILS = os.getenv("BANK_DETAILS", "Bank: ____\nAccount name: ____\nAccount number: ____")
PAY_LINK = os.getenv("PAY_LINK", "")
CLASS_LINK = os.getenv("CLASS_LINK", "")
CLASS_LINK_2 = os.getenv("CLASS_LINK_2", "")
DB_PATH = os.getenv("DB_PATH", "students.db")
CURRICULUM_FILE = os.getenv("CURRICULUM_FILE", "curriculum.pdf")
LOGO_FILE = os.getenv("LOGO_FILE", "logo.png")
WHATSAPP_LINK = os.getenv("WHATSAPP_LINK", "")
TZ = ZoneInfo("Africa/Lagos")

NAME, AGE, PHONE, EMAIL, FOUND_US, GOAL, MOTIVATION, CATEGORY = range(8)
CATEGORIES = ["Student", "Business owner", "Knowledge seeker", "Income seeker"]


# ---------- database ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                user_id INTEGER PRIMARY KEY,
                username TEXT, name TEXT, age TEXT, phone TEXT, email TEXT,
                found_us TEXT, goal TEXT, motivation TEXT,
                category TEXT, source TEXT, plan TEXT,
                status TEXT DEFAULT 'registered',
                paid_amount INTEGER DEFAULT 0,
                registered_at TEXT, second_due TEXT, last_reminded TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, amount INTEGER, proof_file_id TEXT,
                status TEXT DEFAULT 'pending', created_at TEXT
            );
            """
        )


def get_student(uid):
    with db() as c:
        return c.execute("SELECT * FROM students WHERE user_id=?", (uid,)).fetchone()


def now():
    return datetime.now(TZ)


# ---------- registration form ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ctx.args:
        ctx.user_data["source"] = ctx.args[0][:40]
    s = get_student(uid)
    if s:
        await update.message.reply_text(
            f"Welcome back, {s['name']}! Use /pay to make a payment, /status to check your status, or /help.",
        )
        return ConversationHandler.END

    if os.path.exists(LOGO_FILE):
        try:
            with open(LOGO_FILE, "rb") as f:
                await update.message.reply_photo(f)
        except Exception as e:
            log.warning("Could not send logo: %s", e)

    await update.message.reply_text(
        f"Welcome to the {PROGRAM}! 🎬\n\n"
        "Before anything else, we'd like to get to know you properly — this isn't just a "
        "mailing list signup, it's a short application so we understand who's joining us "
        "and can support you better.\n\n"
        "It's about a dozen questions and takes 2–3 minutes. Let's start:\n\n"
        "What's your full name?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NAME


async def got_name(update, ctx):
    ctx.user_data["name"] = update.message.text.strip()[:80]
    await update.message.reply_text("How old are you?")
    return AGE


async def got_age(update, ctx):
    age = update.message.text.strip()
    digits = "".join(ch for ch in age if ch.isdigit())
    if not digits or not (10 <= int(digits) <= 100):
        await update.message.reply_text("Please enter a valid age (just the number).")
        return AGE
    ctx.user_data["age"] = digits
    await update.message.reply_text("Your WhatsApp / phone number?")
    return PHONE


async def got_phone(update, ctx):
    phone = update.message.text.strip()
    if sum(ch.isdigit() for ch in phone) < 8:
        await update.message.reply_text("That doesn't look like a valid number. Please try again.")
        return PHONE
    ctx.user_data["phone"] = phone
    await update.message.reply_text("Your email address?")
    return EMAIL


async def got_email(update, ctx):
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("That doesn't look like a valid email. Please try again.")
        return EMAIL
    ctx.user_data["email"] = email
    await update.message.reply_text(
        "How did you hear about us? (e.g. a friend, a particular blog/page, Instagram, etc.)"
    )
    return FOUND_US


async def got_found_us(update, ctx):
    ctx.user_data["found_us"] = update.message.text.strip()[:200]
    await update.message.reply_text(
        "What specifically do you want to learn or be able to do by the end of this training?"
    )
    return GOAL


async def got_goal(update, ctx):
    ctx.user_data["goal"] = update.message.text.strip()[:500]
    await update.message.reply_text(
        "Last one before the multiple choice — tell us a bit about yourself: what do you "
        "currently do, and why does this training matter to you right now?"
    )
    return MOTIVATION


async def got_motivation(update, ctx):
    ctx.user_data["motivation"] = update.message.text.strip()[:800]
    kb = ReplyKeyboardMarkup([[c] for c in CATEGORIES], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Which best describes you?", reply_markup=kb)
    return CATEGORY


async def got_category(update, ctx):
    cat = update.message.text.strip()
    if cat not in CATEGORIES:
        await update.message.reply_text("Please pick one of the options.")
        return CATEGORY
    ctx.user_data["category"] = cat
    u = update.effective_user
    d = ctx.user_data
    with db() as c:
        c.execute(
            """INSERT OR REPLACE INTO students
               (user_id, username, name, age, phone, email, found_us, goal, motivation,
                category, source, plan, status, paid_amount, registered_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,'registered',0,?)""",
            (u.id, u.username, d["name"], d["age"], d["phone"], d["email"],
             d["found_us"], d["goal"], d["motivation"], d["category"],
             d.get("source", "direct"), now().isoformat()),
        )
    await update.message.reply_text(
        f"Thank you, {d['name']} — that means a lot, and we can already tell you're serious "
        f"about this. Welcome to the {PROGRAM}! 🎬\n\n"
        "Here's our full curriculum so you can see exactly what you'll be learning, "
        "week by week.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await send_curriculum(update.message, ctx)

    if WHATSAPP_LINK:
        await update.message.reply_text(
            "Join our WhatsApp community here — this is where announcements, class links "
            f"and updates will be shared:\n\n{WHATSAPP_LINK}"
        )

    await update.message.reply_text(
        f"Good luck, {d['name']} — we're rooting for you already. See you soon! 🎉\n\n"
        "When you're ready to secure your seat, just send /pay right here in this chat."
    )
    return ConversationHandler.END


async def send_curriculum(message, ctx):
    if not os.path.exists(CURRICULUM_FILE):
        log.warning("Curriculum file not found at %s", CURRICULUM_FILE)
        return
    try:
        with open(CURRICULUM_FILE, "rb") as f:
            await message.reply_document(
                f,
                filename="Curriculum.pdf",
                caption="📄 Your training curriculum — take a look before you pay.",
            )
    except Exception as e:
        log.warning("Could not send curriculum: %s", e)


async def curriculum_cmd(update, ctx):
    await send_curriculum(update.message, ctx)


async def cancel(update, ctx):
    await update.message.reply_text("Cancelled. Send /start whenever you're ready.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ---------- payments ----------
def amount_due(s):
    if s["plan"] == "full":
        return max(PRICE_FULL - s["paid_amount"], 0)
    if s["paid_amount"] < PRICE_HALF:
        return PRICE_HALF
    return max(PRICE_FULL - s["paid_amount"], 0)


async def send_payment_instructions(message, ctx, uid):
    s = get_student(uid)
    due = amount_due(s)
    if due == 0:
        await message.reply_text("You're fully paid. See you in class!")
        return
    text = f"Please pay N{due:,}.\n\n{BANK_DETAILS}"
    if PAY_LINK:
        text += f"\n\nOr pay online: {PAY_LINK}"
    text += "\n\nAfter paying, send a screenshot of your receipt here in this chat."
    ctx.user_data["awaiting_proof"] = due
    await message.reply_text(text)


async def pay_cmd(update, ctx):
    s = get_student(update.effective_user.id)
    if not s:
        await update.message.reply_text("Please register first with /start.")
        return
    if not s["plan"]:
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(f"Pay in full (N{PRICE_FULL:,})", callback_data="plan:full")],
                [InlineKeyboardButton(
                    f"Two instalments (N{PRICE_HALF:,} + N{PRICE_HALF:,})", callback_data="plan:two"
                )],
            ]
        )
        await update.message.reply_text("How would you like to pay?", reply_markup=kb)
        return
    await send_payment_instructions(update.message, ctx, update.effective_user.id)


async def choose_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    plan = "full" if q.data == "plan:full" else "two"
    uid = q.from_user.id
    with db() as c:
        c.execute("UPDATE students SET plan=? WHERE user_id=?", (plan, uid))
    await q.edit_message_text("Great choice.")
    await send_payment_instructions(q.message, ctx, uid)


async def got_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_student(uid)
    if not s:
        await update.message.reply_text("Please register first with /start.")
        return
    amount = ctx.user_data.get("awaiting_proof") or amount_due(s)
    if amount == 0:
        await update.message.reply_text("You're already fully paid.")
        return
    file_id = (
        update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id
    )
    with db() as c:
        cur = c.execute(
            "INSERT INTO payments (user_id, amount, proof_file_id, created_at) VALUES (?,?,?,?)",
            (uid, amount, file_id, now().isoformat()),
        )
        pid = cur.lastrowid
    ctx.user_data.pop("awaiting_proof", None)
    await update.message.reply_text("Received! We'll confirm your payment shortly.")
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Approve", callback_data=f"ap:{pid}"),
          InlineKeyboardButton("Reject", callback_data=f"rj:{pid}")]]
    )
    caption = f"Payment #{pid}\n{s['name']} ({s['category']})\nAmount: N{amount:,}\nPlan: {s['plan']}\nSource: {s['source']}"
    for admin in ADMIN_IDS:
        try:
            await ctx.bot.send_photo(admin, file_id, caption=caption, reply_markup=kb)
        except Exception:
            try:
                await ctx.bot.send_document(admin, file_id, caption=caption, reply_markup=kb)
            except Exception as e:
                log.warning("Could not notify admin %s: %s", admin, e)


async def review_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id not in ADMIN_IDS:
        await q.answer("Admins only.", show_alert=True)
        return
    action, pid = q.data.split(":")
    pid = int(pid)
    with db() as c:
        p = c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        if not p or p["status"] != "pending":
            await q.answer("Already handled.")
            return
        if action == "rj":
            c.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
            await q.answer("Rejected")
            await q.edit_message_caption((q.message.caption or "") + "\n\nREJECTED")
            await ctx.bot.send_message(
                p["user_id"], "We couldn't confirm your payment. Please check and send a clear receipt with /pay."
            )
            return
        c.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        s = c.execute("SELECT * FROM students WHERE user_id=?", (p["user_id"],)).fetchone()
        paid = s["paid_amount"] + p["amount"]
        if paid >= PRICE_FULL:
            status, second_due = "paid", None
        else:
            status, second_due = "part_paid", (now() + timedelta(days=7)).isoformat()
        c.execute(
            "UPDATE students SET paid_amount=?, status=?, second_due=? WHERE user_id=?",
            (paid, status, second_due, p["user_id"]),
        )
    await q.answer("Approved")
    await q.edit_message_caption((q.message.caption or "") + "\n\nAPPROVED")
    if status == "paid":
        msg = "Payment confirmed. You're fully paid!"
        link = CLASS_LINK_2 or CLASS_LINK
    else:
        msg = f"Payment confirmed. Your balance of N{PRICE_FULL - paid:,} is due within 7 days to unlock the second half."
        link = CLASS_LINK
    if link:
        msg += f"\n\nJoin the class here: {link}"
    await ctx.bot.send_message(p["user_id"], msg)


async def status_cmd(update, ctx):
    s = get_student(update.effective_user.id)
    if not s:
        await update.message.reply_text("You're not registered yet. Send /start.")
        return
    await update.message.reply_text(
        f"Status: {s['status']}\nPaid: N{s['paid_amount']:,} of N{PRICE_FULL:,}\nUse /pay to pay the balance."
    )


async def help_cmd(update, ctx):
    text = (
        "/start - register\n/pay - payment details\n/status - your payment status"
        "\n/curriculum - get the training curriculum (PDF)"
    )
    if update.effective_user.id in ADMIN_IDS:
        text += "\n\nAdmin:\n/stats\n/export\n/broadcast <all|unpaid|paid> <message>"
    await update.message.reply_text(text)


# ---------- admin ----------
def admin_only(fn):
    async def wrapper(update, ctx):
        if update.effective_user.id not in ADMIN_IDS:
            return
        return await fn(update, ctx)
    return wrapper


@admin_only
async def stats(update, ctx):
    with db() as c:
        total = c.execute("SELECT COUNT(*) n FROM students").fetchone()["n"]
        by_status = c.execute("SELECT status, COUNT(*) n FROM students GROUP BY status").fetchall()
        by_source = c.execute(
            "SELECT source, COUNT(*) n, SUM(paid_amount>0) payers FROM students GROUP BY source ORDER BY n DESC"
        ).fetchall()
        by_cat = c.execute(
            "SELECT category, COUNT(*) n, SUM(paid_amount>0) payers FROM students GROUP BY category"
        ).fetchall()
        revenue = c.execute("SELECT COALESCE(SUM(paid_amount),0) r FROM students").fetchone()["r"]
    lines = [f"Registered: {total}", f"Revenue confirmed: N{revenue:,}", "", "By status:"]
    lines += [f"  {r['status']}: {r['n']}" for r in by_status]
    lines += ["", "By source (registered / paid):"]
    lines += [f"  {r['source']}: {r['n']} / {r['payers'] or 0}" for r in by_source]
    lines += ["", "By category (registered / paid):"]
    lines += [f"  {r['category']}: {r['n']} / {r['payers'] or 0}" for r in by_cat]
    await update.message.reply_text("\n".join(lines))


@admin_only
async def export(update, ctx):
    with db() as c:
        rows = c.execute("SELECT * FROM students").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    if rows:
        w.writerow(rows[0].keys())
        for r in rows:
            w.writerow(list(r))
    data = io.BytesIO(buf.getvalue().encode())
    data.name = "students.csv"
    await update.message.reply_document(data)


@admin_only
async def broadcast(update, ctx):
    if len(ctx.args) < 2 or ctx.args[0] not in ("all", "unpaid", "paid"):
        await update.message.reply_text("Usage: /broadcast <all|unpaid|paid> <message>")
        return
    audience, text = ctx.args[0], " ".join(ctx.args[1:])
    query = "SELECT user_id FROM students"
    if audience == "unpaid":
        query += " WHERE status IN ('registered','part_paid')"
    elif audience == "paid":
        query += " WHERE status='paid'"
    with db() as c:
        ids = [r["user_id"] for r in c.execute(query).fetchall()]
    sent = 0
    for uid in ids:
        try:
            await ctx.bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await update.message.reply_text(f"Sent to {sent} of {len(ids)}.")


# ---------- automatic reminders (daily, 9am Lagos) ----------
async def daily_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    t = now()
    with db() as c:
        rows = c.execute("SELECT * FROM students WHERE status IN ('registered','part_paid')").fetchall()
        for s in rows:
            last = datetime.fromisoformat(s["last_reminded"]) if s["last_reminded"] else None
            if last and (t - last) < timedelta(days=2):
                continue
            if s["status"] == "registered":
                if (t - datetime.fromisoformat(s["registered_at"])) < timedelta(days=1):
                    continue
                text = f"Hi {s['name']}, your seat for the {PROGRAM} is not secured yet. Send /pay to get started."
            else:
                due = datetime.fromisoformat(s["second_due"]) if s["second_due"] else t
                if due - t > timedelta(days=2):
                    continue
                text = f"Hi {s['name']}, your balance of N{PRICE_FULL - s['paid_amount']:,} is due soon. Send /pay to complete it."
            try:
                await ctx.bot.send_message(s["user_id"], text)
                c.execute("UPDATE students SET last_reminded=? WHERE user_id=?", (t.isoformat(), s["user_id"]))
            except Exception:
                pass
            await asyncio.sleep(0.05)


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    form = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_age)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_email)],
            FOUND_US: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_found_us)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_goal)],
            MOTIVATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_motivation)],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_category)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(form)
    app.add_handler(CommandHandler("pay", pay_cmd))
    app.add_handler(CommandHandler("curriculum", curriculum_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(review_payment, pattern=r"^(ap|rj):\d+$"))
    app.add_handler(CallbackQueryHandler(choose_plan, pattern=r"^plan:(full|two)$"))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & filters.ChatType.PRIVATE, got_proof))
    app.job_queue.run_daily(daily_reminders, time=time(9, 0, tzinfo=TZ))
    app.run_polling()


if __name__ == "__main__":
    main()
