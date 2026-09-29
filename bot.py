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

import cards
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
BANK_DETAILS = os.getenv("BANK_DETAILS", "Bank: First Bank\nAccount name: Blessed Shima Kpete\nAccount number: 3231296192")
PAY_LINK = os.getenv("PAY_LINK", "")
CLASS_LINK = os.getenv("CLASS_LINK", "")
CLASS_LINK_2 = os.getenv("CLASS_LINK_2", "")
CLASS_GROUP_ID = int(os.getenv("CLASS_GROUP_ID", "0") or 0)
RULES_VERSION = os.getenv("RULES_VERSION", "2026-09-v1")
DB_PATH = os.getenv("DB_PATH", "students.db")
CURRICULUM_FILE = os.getenv("CURRICULUM_FILE", "curriculum.pdf")
LOGO_FILE = os.getenv("LOGO_FILE", "logo.png")
WHATSAPP_LINK = os.getenv("WHATSAPP_LINK", "https://chat.whatsapp.com/LwlosE8KbTBCIh5oM0JKCD")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
REFERRAL_BONUS_THRESHOLD = int(os.getenv("REFERRAL_BONUS_THRESHOLD", "3"))
REFERRAL_FREE_ACCESS_CAP = int(os.getenv("REFERRAL_FREE_ACCESS_CAP", "20"))
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
                student_no TEXT,
                status TEXT DEFAULT 'registered',
                paid_amount INTEGER DEFAULT 0,
                registered_at TEXT, second_due TEXT, last_reminded TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, amount INTEGER, proof_file_id TEXT,
                status TEXT DEFAULT 'pending', created_at TEXT
            );
            """
        )
        # safe additive migration for referral tracking (won't error on an
        # already-populated live database that predates these columns)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(students)").fetchall()}
        if "referred_by" not in cols:
            c.execute("ALTER TABLE students ADD COLUMN referred_by TEXT")
        if "bonus_sent" not in cols:
            c.execute("ALTER TABLE students ADD COLUMN bonus_sent INTEGER DEFAULT 0")
        if "rules_accepted_at" not in cols:
            c.execute("ALTER TABLE students ADD COLUMN rules_accepted_at TEXT")
        if "rules_version" not in cols:
            c.execute("ALTER TABLE students ADD COLUMN rules_version TEXT")
        if "registration_pack_sent_at" not in cols:
            c.execute("ALTER TABLE students ADD COLUMN registration_pack_sent_at TEXT")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS moderation_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, message_id INTEGER, user_id INTEGER,
                username TEXT, display_name TEXT, message_text TEXT,
                detected_terms TEXT, status TEXT DEFAULT 'pending',
                created_at TEXT, reviewed_by INTEGER, reviewed_at TEXT, decision TEXT
            );
            CREATE TABLE IF NOT EXISTS assignment_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, assignment_key TEXT NOT NULL,
                file_id TEXT, text TEXT, submitted_at TEXT NOT NULL,
                UNIQUE(user_id, assignment_key)
            );
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, message TEXT, status TEXT DEFAULT 'open',
                created_at TEXT, handled_by INTEGER
            );
        """)


def get_student(uid):
    with db() as c:
        return c.execute("SELECT * FROM students WHERE user_id=?", (uid,)).fetchone()


def get_student_by_no(student_no):
    with db() as c:
        return c.execute(
            "SELECT * FROM students WHERE student_no=? COLLATE NOCASE", (student_no,)
        ).fetchone()


def now():
    return datetime.now(TZ)


def referral_count(student_no):
    with db() as c:
        return c.execute(
            "SELECT COUNT(*) n FROM students WHERE referred_by=? COLLATE NOCASE",
            (student_no,),
        ).fetchone()["n"]


# ---------- registration form ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ctx.args:
        payload = ctx.args[0][:60]
        if payload.startswith("ref_"):
            ref_no = payload[4:].strip()
            if get_student_by_no(ref_no):
                ctx.user_data["referred_by"] = ref_no
                ctx.user_data["source"] = f"referral:{ref_no}"
        else:
            ctx.user_data["source"] = payload
    s = get_student(uid)
    if s:
        if not rules_accepted(uid):
            await send_rules_page(ctx, uid, 0)
        else:
            await send_registration_pack(ctx, uid)
            await send_student_menu(ctx, uid, f"Welcome back, {s['name']}!")
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
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(c, callback_data=f"cat:{i}")] for i, c in enumerate(CATEGORIES)]
    )
    await update.message.reply_text(
        "Which best describes you?", reply_markup=kb
    )
    return CATEGORY


async def got_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split(":")[1])
    cat = CATEGORIES[idx]
    ctx.user_data["category"] = cat
    u = q.from_user
    d = ctx.user_data

    referred_by = d.get("referred_by")
    with db() as c:
        next_no = c.execute("SELECT COUNT(*) n FROM students").fetchone()["n"] + 1
        student_no = f"HB-{next_no:04d}"
        c.execute(
            """INSERT OR REPLACE INTO students
               (user_id, username, name, age, phone, email, found_us, goal, motivation,
                category, source, plan, student_no, status, paid_amount, registered_at,
                referred_by, bonus_sent)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?,'registered',0,?,?,0)""",
            (u.id, u.username, d["name"], d["age"], d["phone"], d["email"],
             d["found_us"], d["goal"], d["motivation"], cat,
             d.get("source", "direct"), student_no, now().isoformat(), referred_by),
        )

    await q.edit_message_text(f"Got it — {cat}. ✅")

    await ctx.bot.send_message(
        u.id,
        f"Thank you, {d['name']}! Welcome to {PROGRAM}.\n\n"
        "Before we send your student ID, official course outline, and crash-course WhatsApp link, "
        "please read and accept all sections of the Academy Rules & Regulations below.",
    )
    # Mandatory gate: ID, curriculum and crash-course link are withheld until rules acceptance.
    await send_rules_page(ctx, u.id, 0)

    if referred_by:
        await maybe_send_referral_bonus(ctx, referred_by)

    return ConversationHandler.END


async def maybe_send_referral_bonus(ctx, referrer_no):
    referrer = get_student_by_no(referrer_no)
    if not referrer or referrer["bonus_sent"]:
        return
    count = referral_count(referrer_no)
    if count < REFERRAL_BONUS_THRESHOLD:
        return

    # first time this referrer crosses the threshold — decide now, once,
    # whether a free-access slot is still available
    with db() as c:
        granted_so_far = c.execute(
            "SELECT COUNT(*) n FROM students WHERE bonus_sent=1"
        ).fetchone()["n"]

    if granted_so_far < REFERRAL_FREE_ACCESS_CAP:
        with db() as c:
            c.execute(
                "UPDATE students SET bonus_sent=1, status='paid', paid_amount=?, second_due=NULL WHERE student_no=?",
                (PRICE_FULL, referrer_no),
            )
        msg = (
            f"🎉 Amazing — you've referred {count} people! That earns you FREE full access "
            f"to the {PROGRAM}, no payment needed. Please open the rules and accept them "
            "to receive class access."
        )
        try:
            await ctx.bot.send_message(referrer["user_id"], msg)
        except Exception as e:
            log.warning("Could not notify %s of free access: %s", referrer["user_id"], e)
    else:
        with db() as c:
            c.execute("UPDATE students SET bonus_sent=1 WHERE student_no=?", (referrer_no,))
        try:
            await ctx.bot.send_message(
                referrer["user_id"],
                f"You've referred {count} people — thank you so much for spreading the word! "
                f"All {REFERRAL_FREE_ACCESS_CAP} free-access slots have already been claimed by "
                "earlier referrers, but we really appreciate you.",
            )
        except Exception as e:
            log.warning("Could not notify %s of referral cap: %s", referrer["user_id"], e)


async def send_curriculum_to(ctx, uid):
    if not os.path.exists(CURRICULUM_FILE):
        log.warning("Curriculum file not found at %s", CURRICULUM_FILE)
        return
    try:
        with open(CURRICULUM_FILE, "rb") as f:
            await ctx.bot.send_document(
                uid,
                f,
                filename="Curriculum.pdf",
                caption="📄 Your training curriculum — take a look and see everything you'll be learning.",
            )
    except Exception as e:
        log.warning("Could not send curriculum: %s", e)


async def curriculum_cmd(update, ctx):
    uid = update.effective_user.id
    if not rules_accepted(uid):
        await send_rules_page(ctx, uid, 0)
        return
    await send_curriculum_to(ctx, uid)


async def send_registration_pack(ctx, uid):
    """Send student ID, official curriculum and crash-course WhatsApp link once rules are accepted."""
    s = get_student(uid)
    if not s or not rules_accepted(uid):
        return
    if s["registration_pack_sent_at"]:
        return
    await ctx.bot.send_message(
        uid,
        f"Rules accepted. Your registration is complete!\n\nStudent ID: {s['student_no']}\n"
        "Here is your student ID card, official course outline, and crash-course WhatsApp link.",
    )
    try:
        id_card = cards.generate_id_card(s["name"], s["category"], s["student_no"], PROGRAM)
        await ctx.bot.send_photo(uid, id_card, caption=f"Your Heribhee Academy Student ID — {s['student_no']}")
    except Exception as e:
        log.warning("Could not generate/send ID card: %s", e)
        await ctx.bot.send_message(uid, f"Your student ID is: {s['student_no']}")
    await send_curriculum_to(ctx, uid)
    if WHATSAPP_LINK:
        await ctx.bot.send_message(uid, f"Crash-course WhatsApp group link (for registered students):\n{WHATSAPP_LINK}\n\nPlease do not share this link.")
    else:
        await ctx.bot.send_message(uid, "Your crash-course WhatsApp link is not configured yet. Please contact an Academy admin.")
    with db() as c:
        c.execute("UPDATE students SET registration_pack_sent_at=? WHERE user_id=?", (now().isoformat(), uid))


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
    uid = update.effective_user.id
    s = get_student(uid)
    if not s:
        await update.message.reply_text("Please register first with /start.")
        return
    if not rules_accepted(uid):
        await send_rules_page(ctx, uid, 0)
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
                p["user_id"], "We couldn't confirm your transfer. Please check the details and submit a clear receipt again through Payment & Status in the bot."
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
        msg = "Payment confirmed. You're fully paid! Open My Classes in the student menu to access the paid class."
    else:
        msg = f"Payment confirmed. You have paid ₦{paid:,}; your remaining balance is ₦{PRICE_FULL - paid:,}. Open Payment & Status whenever you're ready to pay the balance."
    await ctx.bot.send_message(p["user_id"], msg)
    if rules_accepted(p["user_id"]):
        await deliver_class_access(ctx, p["user_id"])


async def status_cmd(update, ctx):
    s = get_student(update.effective_user.id)
    if not s:
        await update.message.reply_text("You're not registered yet. Send /start.")
        return
    await update.message.reply_text(
        f"Student ID: {s['student_no']}\nStatus: {s['status']}\nPaid: ₦{s['paid_amount']:,} of ₦{PRICE_FULL:,}\nBalance: ₦{max(PRICE_FULL - s['paid_amount'], 0):,}\n\n{BANK_DETAILS}\n\nUse Payment & Status in the menu to submit your receipt."
    )


async def certificate_cmd(update, ctx):
    s = get_student(update.effective_user.id)
    if not s:
        await update.message.reply_text("You're not registered yet. Send /start.")
        return
    if s["status"] != "completed":
        await update.message.reply_text(
            "Your certificate unlocks once you've completed the training — hang tight, "
            "your instructor will mark you as done at the end of the program."
        )
        return
    try:
        date_str = datetime.fromisoformat(s["completed_at"]).strftime("%d %b %Y") if s["completed_at"] else now().strftime("%d %b %Y")
        cert = cards.generate_certificate(s["name"], PROGRAM, date_str)
        await update.message.reply_photo(cert, caption="🎓 Congratulations! Here's your certificate.")
    except Exception as e:
        log.warning("Could not generate certificate: %s", e)
        await update.message.reply_text("Sorry, something went wrong generating your certificate. Try again shortly.")


async def id_cmd(update, ctx):
    s = get_student(update.effective_user.id)
    if not s:
        await update.message.reply_text("You're not registered yet. Send /start.")
        return
    try:
        id_card = cards.generate_id_card(s["name"], s["category"], s["student_no"] or "HB-0000", PROGRAM)
        await update.message.reply_photo(id_card, caption=f"🪪 Your student ID — {s['student_no']}")
    except Exception as e:
        log.warning("Could not generate ID card: %s", e)


async def refer_cmd(update, ctx):
    uid = update.effective_user.id
    s = get_student(uid)
    if not s:
        await update.message.reply_text("You're not registered yet. Send /start.")
        return
    count = referral_count(s["student_no"])
    remaining = max(0, REFERRAL_BONUS_THRESHOLD - count)
    if not BOT_USERNAME:
        await update.message.reply_text(
            "Your referral tracking is set up, but the bot's link isn't configured yet — "
            "let the team know."
        )
        return
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{s['student_no']}"
    lines = [
        f"🔗 Your personal referral link:\n{link}",
        "",
        "Share it with friends — when someone registers through it, it counts as your referral.",
        "",
        f"You've referred {count} so far.",
    ]
    if s["bonus_sent"]:
        if s["status"] == "paid" and s["paid_amount"] >= PRICE_FULL:
            lines.append("🎉 You've already unlocked FREE full access. Thank you for spreading the word!")
        else:
            lines.append("You crossed the referral threshold, but all free-access slots were already taken. Thank you regardless!")
    else:
        lines.append(
            f"Refer {remaining} more (at {REFERRAL_BONUS_THRESHOLD} total) to unlock FREE full "
            f"access — limited to the first {REFERRAL_FREE_ACCESS_CAP} people who qualify."
        )
    await update.message.reply_text("\n".join(lines))


async def leaderboard_cmd(update, ctx):
    with db() as c:
        rows = c.execute(
            """SELECT referred_by, COUNT(*) n FROM students
               WHERE referred_by IS NOT NULL AND referred_by != ''
               GROUP BY referred_by COLLATE NOCASE ORDER BY n DESC LIMIT 10"""
        ).fetchall()
    if not rows:
        await update.message.reply_text("No referrals yet — be the first! Use /refer to get your link.")
        return
    lines = ["🏆 Referral leaderboard:", ""]
    for i, r in enumerate(rows, 1):
        ref = get_student_by_no(r["referred_by"])
        name = ref["name"] if ref else r["referred_by"]
        lines.append(f"{i}. {name} — {r['n']} referral{'s' if r['n'] != 1 else ''}")
    await update.message.reply_text("\n".join(lines))


async def help_cmd(update, ctx):
    await send_student_menu(ctx, update.effective_user.id, "How can we help you?")


# ---------- student menu, rules gate, FAQs, assignments and moderation ----------
RULES_PAGES = [
    ("1/5 — Respectful conduct", "Communicate respectfully with instructors and fellow students. Insults, harassment, threats, bullying, hate speech, sexual harassment, and deliberate foul or abusive language are prohibited."),
    ("2/5 — Removal and other violations", "Confirmed abusive or seriously disruptive conduct may result in immediate removal without prior warning. Spam, impersonation, unauthorized sharing of class links or course materials, and deliberate disruption may also result in removal."),
    ("3/5 — Assignments and deadlines", "Submit assignments before the stated deadline. Missing or late assignments alone do not remove you from class, but may affect certification eligibility."),
    ("4/5 — Certification", "Certification requires submission of the final project and at least four assignments, within the Academy's stated submission cutoffs."),
    ("5/5 — Access and declaration", "Class access is for enrolled students only. By accepting, you confirm that you have reviewed these rules and agree to follow them. Violations may result in loss of class access, subject to applicable payment/refund terms."),
]

FAQS = {
    "schedule": ("Classes & Schedule", [
        ("When are classes?", "Monday, Tuesday, Thursday and Friday, 8–10 PM. Friday is the live milestone session. Confirmed times are Nigeria time (Africa/Lagos)."),
        ("Where is the class?", "The class is hosted in the private Telegram class group. The bot releases access after you accept the rules and your enrollment is eligible."),
        ("What if I miss a class?", "Follow the Academy's replay instructions and complete the required work before its deadline."),
    ]),
    "assignments": ("Assignments", [
        ("When are assignments due?", "Monday task: Tuesday 6 PM. Tuesday task: Thursday 6 PM. Thursday task: Friday 5 PM. Friday weekly milestone: Sunday 11:59 PM."),
        ("Can I submit late?", "No. Work must be submitted before the stated deadline. Late submissions may not be reviewed or counted."),
        ("Will missing work get me removed?", "No. Missing assignments alone do not remove you from class, but certification requirements still apply."),
        ("How do I submit?", "Use the Assignments menu and follow the instructions for the active task. If submission buttons are not available for your task, contact an admin through Ask Admin."),
    ]),
    "cert": ("Certification", [
        ("What do I need?", "Submit the final project and at least four assignments before the applicable cutoffs."),
        ("When are certificates issued?", "After the final project cutoff and eligibility verification by the Academy."),
    ]),
    "payment": ("Payments & Referrals", [
        ("How do I check payment status?", "Choose Payment & Status from the menu or use /status."),
        ("How do referrals work?", "Open Refer a Friend to get your personal link and referral count. Referral free access is subject to the published threshold and available slots."),
    ]),
    "rules": ("Rules & Conduct", [
        ("What happens for abusive language?", "Potential abuse is sent privately to an Academy admin for review. Removal occurs only after an authorized admin confirms the violation."),
        ("How do I accept the rules?", "Open Rules & Regulations and navigate through all sections. The acceptance button appears at the final section."),
    ]),
}


def rules_accepted(uid):
    s = get_student(uid)
    return bool(s and s["rules_accepted_at"] and s["rules_version"] == RULES_VERSION)


def student_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 My Classes", callback_data="menu:classes"), InlineKeyboardButton("📝 Assignments", callback_data="menu:assignments")],
        [InlineKeyboardButton("❓ Help & FAQs", callback_data="menu:help"), InlineKeyboardButton("💬 Ask Admin", callback_data="menu:ask")],
        [InlineKeyboardButton("📈 My Progress", callback_data="menu:progress"), InlineKeyboardButton("📜 Rules & Regulations", callback_data="menu:rules")],
        [InlineKeyboardButton("👥 Refer a Friend", callback_data="menu:refer"), InlineKeyboardButton("🎓 Certification", callback_data="menu:cert")],
        [InlineKeyboardButton("💳 Payment & Status", callback_data="menu:status")],
    ])


async def send_student_menu(ctx, uid, intro="Heribhee Academy Student Menu"):
    await ctx.bot.send_message(uid, intro + "\n\nChoose an option:", reply_markup=student_keyboard())


async def send_rules_page(ctx, uid, page):
    page = max(0, min(page, len(RULES_PAGES)-1))
    title, body = RULES_PAGES[page]
    rows = []
    if page > 0:
        rows.append(InlineKeyboardButton("⬅ Previous", callback_data=f"rules:page:{page-1}"))
    if page < len(RULES_PAGES)-1:
        rows.append(InlineKeyboardButton("Next ➡", callback_data=f"rules:page:{page+1}"))
    keyboard = [rows] if rows else []
    if page == len(RULES_PAGES)-1:
        keyboard.append([InlineKeyboardButton("I HAVE READ AND ACCEPT", callback_data="rules:accept")])
    else:
        keyboard.append([InlineKeyboardButton("Back to start", callback_data="rules:page:0")])
    await ctx.bot.send_message(uid, f"HERIBHEE ACADEMY — RULES & REGULATIONS\n\n{title}\n\n{body}\n\nPlease use the buttons to review every section.", reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    data = q.data
    if data.startswith("rules:page:"):
        await send_rules_page(ctx, uid, int(data.rsplit(":", 1)[1])); return
    if data == "rules:accept":
        if not get_student(uid):
            await q.message.reply_text("Please register first using /start."); return
        with db() as c:
            c.execute("UPDATE students SET rules_accepted_at=?, rules_version=? WHERE user_id=?", (now().isoformat(), RULES_VERSION, uid))
        await q.message.reply_text("Thank you. Your acceptance has been recorded.")
        await send_registration_pack(ctx, uid)
        await deliver_class_access(ctx, uid)
        await send_student_menu(ctx, uid)
        return
    if data.startswith("faq:"):
        key = data.split(":",1)[1]
        title, items = FAQS.get(key, ("Help", []))
        kb = [[InlineKeyboardButton(question, callback_data=f"faqanswer:{key}:{i}")] for i,(question,_) in enumerate(items)]
        kb.append([InlineKeyboardButton("⬅ Help categories", callback_data="menu:help")])
        await q.message.reply_text(title + "\nChoose a question:", reply_markup=InlineKeyboardMarkup(kb)); return
    if data.startswith("faqanswer:"):
        _, key, n = data.split(":")
        title, items = FAQS[key]
        question, answer = items[int(n)]
        await q.message.reply_text(f"{question}\n\n{answer}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to questions", callback_data=f"faq:{key}")],[InlineKeyboardButton("Main menu", callback_data="menu:home")]])); return
    if data == "menu:home":
        await send_student_menu(ctx, uid); return
    if data == "menu:help":
        kb = [[InlineKeyboardButton(v[0], callback_data=f"faq:{k}")] for k,v in FAQS.items()]
        kb.append([InlineKeyboardButton("Main menu", callback_data="menu:home")])
        await q.message.reply_text("Help & FAQs — choose a category:", reply_markup=InlineKeyboardMarkup(kb)); return
    if data == "menu:rules":
        await send_rules_page(ctx, uid, 0); return
    if data == "menu:classes":
        if not rules_accepted(uid):
            await send_rules_page(ctx, uid, 0); return
        await deliver_class_access(ctx, uid); return
    if data == "menu:assignments":
        await q.message.reply_text("Assignment deadlines (Nigeria time):\n• Monday task — Tuesday, 6 PM\n• Tuesday task — Thursday, 6 PM\n• Thursday task — Friday, 5 PM\n• Friday milestone — Sunday, 11:59 PM\n\nSubmit before the stated deadline. Use Ask Admin if you need help with a submission.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Submit assignment", callback_data="assignment:submitinfo")],[InlineKeyboardButton("Main menu", callback_data="menu:home")]])); return
    if data == "assignment:submitinfo":
        ctx.user_data["awaiting_assignment"] = True
        await q.message.reply_text("Send your assignment as a document, photo, or text in this private chat. Include the assignment name in your message/caption. Your submission will be recorded for admin review.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="menu:home")]])); return
    if data == "menu:progress":
        with db() as c:
            rows = c.execute("SELECT assignment_key, submitted_at FROM assignment_submissions WHERE user_id=? ORDER BY submitted_at", (uid,)).fetchall()
        text = "Your recorded submissions:\n" + ("\n".join(f"• {r['assignment_key']} — {r['submitted_at'][:16].replace('T',' ')}" for r in rows) if rows else "No assignments recorded yet.")
        await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main menu", callback_data="menu:home")]])); return
    if data == "menu:ask":
        ctx.user_data["awaiting_support"] = True
        await q.message.reply_text("Please type your question or describe the issue here. It will be sent privately to the Academy admins.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="menu:home")]])); return
    if data == "menu:refer":
        s=get_student(uid)
        if not s: await q.message.reply_text("Please register first with /start."); return
        count=referral_count(s["student_no"]); remaining=max(0,REFERRAL_BONUS_THRESHOLD-count)
        if not BOT_USERNAME: await q.message.reply_text("Referral link is not configured yet."); return
        link=f"https://t.me/{BOT_USERNAME}?start=ref_{s['student_no']}"
        await q.message.reply_text(f"Your referral link:\n{link}\n\nReferrals: {count}. Remaining to threshold: {remaining}."); return
    if data == "menu:cert":
        s=get_student(uid)
        if not s: await q.message.reply_text("Please register first with /start."); return
        await q.message.reply_text("Certification requires the final project and at least four assignments. Use My Progress to check recorded submissions."); return
    if data == "menu:status":
        s=get_student(uid)
        if not s:
            await q.message.reply_text("Please register first with /start."); return
        paid = int(s["paid_amount"] or 0)
        balance = max(PRICE_FULL - paid, 0)
        status_label = {"registered": "Not paid", "part_paid": "Part payment received", "paid": "Fully paid"}.get(s["status"], s["status"])
        pay_kb = []
        if balance > 0:
            pay_kb.append([InlineKeyboardButton(f"Pay in full (₦{PRICE_FULL:,})", callback_data="plan:full")])
            if paid == 0:
                pay_kb.append([InlineKeyboardButton(f"Pay first instalment (₦{PRICE_HALF:,})", callback_data="plan:two")])
            else:
                pay_kb.append([InlineKeyboardButton(f"Pay remaining balance (₦{balance:,})", callback_data="plan:two")])
        pay_kb.append([InlineKeyboardButton("Main menu", callback_data="menu:home")])
        msg = (f"PAYMENT & STATUS\n\nStudent ID: {s['student_no']}\nPayment status: {status_label}\n"
               f"Amount paid: ₦{paid:,} of ₦{PRICE_FULL:,}\nBalance: ₦{balance:,}\n\n"
               f"Bank details\n{BANK_DETAILS}\n\nAfter transferring, choose a payment option and send your transfer receipt here in the bot. "
               "An Academy admin will verify it manually.")
        await q.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(pay_kb)); return


async def deliver_class_access(ctx, uid):
    s = get_student(uid)
    if not s:
        await ctx.bot.send_message(uid, "Please register first using /start."); return
    if not rules_accepted(uid):
        await send_rules_page(ctx, uid, 0); return
    if s["status"] != "paid" and not s["bonus_sent"]:
        await ctx.bot.send_message(uid, "Your class access is not yet unlocked. Please complete payment or check your status using /status."); return
    link = CLASS_LINK_2 or CLASS_LINK
    if link:
        await ctx.bot.send_message(uid, f"Your class access link (please do not share it):\n{link}")
    else:
        await ctx.bot.send_message(uid, "Your rules acceptance is recorded. The class invite link has not been configured yet; please contact an admin.")


async def student_private_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    uid = update.effective_user.id
    if uid in ADMIN_IDS or not get_student(uid):
        return
    if ctx.user_data.get("awaiting_support"):
        text = (msg.text or msg.caption or "[attachment]")[:3500]
        with db() as c:
            cur = c.execute("INSERT INTO support_tickets(user_id,message,created_at) VALUES(?,?,?)", (uid,text,now().isoformat()))
            tid = cur.lastrowid
        s = get_student(uid)
        for admin in ADMIN_IDS:
            await ctx.bot.send_message(admin, f"Support ticket #{tid}\nStudent: {s['name']} ({s['student_no']})\nTelegram: {uid}\n\n{text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Mark handled", callback_data=f"supportdone:{tid}")]]))
        ctx.user_data.pop("awaiting_support",None)
        await msg.reply_text("Your question has been sent to the Academy admins. We'll get back to you.")
        return
    if ctx.user_data.get("awaiting_assignment"):
        s = get_student(uid)
        caption = (msg.caption or msg.text or "").strip()
        key = caption[:100] if caption else "Unlabelled assignment"
        file_id = msg.document.file_id if msg.document else (msg.photo[-1].file_id if msg.photo else None)
        with db() as c:
            c.execute("INSERT OR REPLACE INTO assignment_submissions(user_id,assignment_key,file_id,text,submitted_at) VALUES(?,?,?,?,?)", (uid,key,file_id,caption,now().isoformat()))
        ctx.user_data.pop("awaiting_assignment",None)
        await msg.reply_text(f"Your submission for '{key}' has been recorded for review.")
        for admin in ADMIN_IDS:
            await ctx.bot.send_message(admin, f"Assignment submission\n{s['name']} ({s['student_no']})\nTask: {key}\nSubmitted: {now().isoformat()}\nTelegram ID: {uid}")
            if file_id:
                if msg.document:
                    await ctx.bot.send_document(admin,file_id,caption=f"{s['student_no']} — {key}")
                elif msg.photo:
                    await ctx.bot.send_photo(admin,file_id,caption=f"{s['student_no']} — {key}")
            elif caption:
                await ctx.bot.send_message(admin, caption)
        return


async def group_moderation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or user.is_bot or user.id in ADMIN_IDS:
        return
    # Moderation is restricted to the configured class group, not private chats.
    if CLASS_GROUP_ID and msg.chat_id != CLASS_GROUP_ID:
        return
    if msg.chat.type not in ("group", "supergroup"):
        return
    text = (msg.text or msg.caption or "").lower()
    if not text:
        return
    # Initial configurable keyword detector; admins make the actual removal decision.
    terms = ["fuck", "fucking", "shit", "bitch", "bastard", "motherfucker", "asshole", "idiot", "stupid", "retard"]
    hits = [term for term in terms if term in text]
    if not hits:
        return
    try:
        await msg.delete()
    except Exception as e:
        log.warning("Could not delete flagged message: %s", e)
    display = user.full_name or str(user.id)
    with db() as c:
        cur = c.execute("INSERT INTO moderation_reports(chat_id,message_id,user_id,username,display_name,message_text,detected_terms,created_at) VALUES(?,?,?,?,?,?,?,?)", (msg.chat_id,msg.message_id,user.id,user.username,display,text[:3000],", ".join(hits),now().isoformat()))
        rid = cur.lastrowid
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Confirm removal", callback_data=f"mod:remove:{rid}"),InlineKeyboardButton("Dismiss", callback_data=f"mod:dismiss:{rid}")]])
    for admin in ADMIN_IDS:
        try:
            await ctx.bot.send_message(admin, f"⚠️ MODERATION REVIEW #{rid}\nStudent: {display} (@{user.username or 'no username'})\nUser ID: {user.id}\nGroup: {msg.chat.title or msg.chat_id}\nDetected: {', '.join(hits)}\n\nFlagged message:\n{text[:2500]}\n\nMessage was deleted pending review. Confirm removal or dismiss.", reply_markup=kb)
        except Exception as e:
            log.warning("Could not send moderation alert to admin %s: %s", admin,e)


async def moderation_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q.from_user.id not in ADMIN_IDS:
        await q.answer("Admins only",show_alert=True); return
    _, action, rid_s=q.data.split(":")
    rid=int(rid_s)
    with db() as c:
        report=c.execute("SELECT * FROM moderation_reports WHERE id=?",(rid,)).fetchone()
        if not report or report["status"] != "pending":
            await q.answer("This report has already been handled.",show_alert=True); return
        decision="removed" if action=="remove" else "dismissed"
        c.execute("UPDATE moderation_reports SET status=?,reviewed_by=?,reviewed_at=?,decision=? WHERE id=?",(decision,q.from_user.id,now().isoformat(),decision,rid))
    if action=="remove":
        try:
            await ctx.bot.ban_chat_member(report["chat_id"],report["user_id"])
            await q.answer("Student removed")
            await q.edit_message_text((q.message.text or "")+f"\n\nADMIN DECISION: REMOVED by {q.from_user.full_name}")
        except Exception as e:
            await q.answer("Could not remove member; check bot admin permissions.",show_alert=True)
            log.exception("Moderation ban failed: %s",e)
    else:
        await q.answer("Report dismissed")
        await q.edit_message_text((q.message.text or "")+f"\n\nADMIN DECISION: DISMISSED by {q.from_user.full_name}")


async def support_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q.from_user.id not in ADMIN_IDS:
        await q.answer("Admins only",show_alert=True); return
    tid=int(q.data.split(":")[1])
    with db() as c:
        c.execute("UPDATE support_tickets SET status='handled',handled_by=? WHERE id=?",(q.from_user.id,tid))
    await q.answer("Marked handled")
    await q.edit_message_text((q.message.text or "")+f"\n\nHandled by {q.from_user.full_name}")


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
async def complete_cmd(update, ctx):
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /complete <student ID>\nExample: /complete HB-0001\n\n"
            "(A raw Telegram ID also still works, if you ever have one.)"
        )
        return
    arg = ctx.args[0].strip()
    s = get_student_by_no(arg)
    if not s:
        # fall back to a raw numeric Telegram ID, for backwards compatibility
        try:
            s = get_student(int(arg))
        except ValueError:
            s = None
    if not s:
        await update.message.reply_text(
            f"No student found with ID {arg}. Check /stats or /export for the right student ID (e.g. HB-0001)."
        )
        return
    uid = s["user_id"]
    with db() as c:
        c.execute(
            "UPDATE students SET status='completed', completed_at=? WHERE user_id=?",
            (now().isoformat(), uid),
        )
    try:
        cert = cards.generate_certificate(s["name"], PROGRAM, now().strftime("%d %b %Y"))
        await ctx.bot.send_photo(
            uid, cert,
            caption="🎓 Congratulations — you've completed the program! Here's your certificate."
        )
        await update.message.reply_text(f"Marked {s['name']} ({s['student_no']}) as completed and sent their certificate.")
    except Exception as e:
        log.warning("Could not send certificate to %s: %s", uid, e)
        await update.message.reply_text(f"Marked {s['name']} ({s['student_no']}) as completed, but sending the certificate failed.")


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
            CATEGORY: [CallbackQueryHandler(got_category, pattern=r"^cat:\d+$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(form)
    app.add_handler(CommandHandler("pay", pay_cmd))
    app.add_handler(CommandHandler("curriculum", curriculum_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("certificate", certificate_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^(menu:|rules:|faq:|faqanswer:|assignment:).+"))
    app.add_handler(CallbackQueryHandler(moderation_decision, pattern=r"^mod:(remove|dismiss):\d+$"))
    app.add_handler(CallbackQueryHandler(support_decision, pattern=r"^supportdone:\d+$"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, student_private_message), group=2)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & (filters.TEXT | filters.CAPTION), group_moderation), group=1)
    app.add_handler(CommandHandler("refer", refer_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CommandHandler("complete", complete_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(review_payment, pattern=r"^(ap|rj):\d+$"))
    app.add_handler(CallbackQueryHandler(choose_plan, pattern=r"^plan:(full|two)$"))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & filters.ChatType.PRIVATE, got_proof))
    app.job_queue.run_daily(daily_reminders, time=time(9, 0, tzinfo=TZ))
    app.run_polling()


if __name__ == "__main__":
    main()
