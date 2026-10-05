import asyncio
import csv
import io
import json
import logging
import os
import random
import re
from html import escape
from contextlib import asynccontextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak

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
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "8596935426,7101038703").split(",") if x.strip()}
REVIEWER_IDS = {int(x) for x in os.getenv("ASSIGNMENT_REVIEWER_IDS", "").split(",") if x.strip()} | ADMIN_IDS
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0") or 0)
PROGRAM = os.getenv("PROGRAM_NAME", "AI Video & Movie Making Training")
PRICE_FULL = int(os.getenv("PRICE_FULL", "5000"))
PRICE_HALF = int(os.getenv("PRICE_HALF", "2500"))
BANK_DETAILS = os.getenv("BANK_DETAILS", "Bank: First Bank\nAccount name: Blessed Shima Kpete\nAccount number: 3231296192")
PAY_LINK = os.getenv("PAY_LINK", "")
CLASS_LINK = os.getenv("CLASS_LINK", "")
CLASS_LINK_2 = os.getenv("CLASS_LINK_2", "")
CLASS_GROUP_ID = int(os.getenv("CLASS_GROUP_ID", "0") or 0)
RULES_VERSION = os.getenv("RULES_VERSION", "2026-09-v1")
DATABASE_URL = os.environ["DATABASE_URL"]
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
REMINDER_TRIGGER_SECRET = os.getenv("REMINDER_TRIGGER_SECRET", "").strip()
CURRICULUM_FILE = os.getenv("CURRICULUM_FILE", "curriculum.pdf")
LOGO_FILE = os.getenv("LOGO_FILE", "logo.png")
# Registration/crash-course group. WHATSAPP_LINK is the primary Render key.
WHATSAPP_LINK = os.getenv("WHATSAPP_LINK", "").strip()
CRASH_COURSE_LINK = WHATSAPP_LINK or os.getenv("CRASH_COURSE_LINK", "").strip()

# Separate main class for students whose payment has been approved.
# Use PAID_CLASS_LINK in Render. Legacy CLASS_LINK_2 / CLASS_LINK remain as fallbacks.
PAID_CLASS_LINK = (
    os.getenv("PAID_CLASS_LINK", "").strip()
    or os.getenv("CLASS_LINK_2", "").strip()
    or os.getenv("CLASS_LINK", "").strip()
)
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
REFERRAL_BONUS_THRESHOLD = int(os.getenv("REFERRAL_BONUS_THRESHOLD", "3"))
REFERRAL_FREE_ACCESS_CAP = int(os.getenv("REFERRAL_FREE_ACCESS_CAP", "20"))
TZ = ZoneInfo("Africa/Lagos")

# Weekly knowledge-test system. Defaults are intentionally usable without new
# Render variables; you may override them later if desired.
WEEKLY_TEST_DURATION_MINUTES = int(os.getenv("WEEKLY_TEST_DURATION_MINUTES", "15"))
WEEKLY_TEST_PASS_PERCENT = float(os.getenv("WEEKLY_TEST_PASS_PERCENT", "70"))
WEEKLY_TEST_MAX_ATTEMPTS = int(os.getenv("WEEKLY_TEST_MAX_ATTEMPTS", "2"))
WEEKLY_TEST_RETRY_COOLDOWN_MINUTES = int(os.getenv("WEEKLY_TEST_RETRY_COOLDOWN_MINUTES", "30"))
WEEKLY_TEST_WINDOW_HOURS = int(os.getenv("WEEKLY_TEST_WINDOW_HOURS", "24"))
WEEKLY_TEST_QUESTIONS_PER_ATTEMPT = int(os.getenv("WEEKLY_TEST_QUESTIONS_PER_ATTEMPT", "15"))

# Class-group automation. Times are Lagos/Nigeria time and can be changed in Render.
GROUP_MORNING_TIME = os.getenv("GROUP_MORNING_TIME", "08:00").strip()
GROUP_REMINDER_TIME = os.getenv("GROUP_REMINDER_TIME", "17:00").strip()
GROUP_MESSAGES_DEFAULT_ENABLED = os.getenv("GROUP_MESSAGES_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}

GROUP_MESSAGE_PACK = {
    "morning": {
        0: [
            "Good morning, everyone ☀️ Welcome to a new learning week. Stay curious, practise what you learn, and ask questions whenever you get stuck.",
            "Good morning, class 🎬 New week, fresh energy. Focus on understanding the process, not just finishing quickly. Small practice today will make the next task easier.",
            "Happy Monday, everyone 🌟 This week, aim to create, test, improve, and repeat. Progress comes from actually using the tools, not only watching the lessons.",
        ],
        1: [
            "Good morning, class 👋 Keep building on what you learned yesterday. If something did not work the first time, adjust it and try again.",
            "Good morning ☀️ Today is another chance to practise. Save your best prompts, note what works, and keep improving your workflow.",
            "Morning, everyone 🎥 Remember: good AI video work comes from clear ideas, clear prompts, and patient refinement. Keep practising.",
        ],
        3: [
            "Good morning, class 🌤️ We are back at it today. Review your previous work, correct weak areas, and try one new technique before the day ends.",
            "Good morning 👋 Thursday is a good day to check your progress. Do not wait until the weekend to fix something you already know needs attention.",
            "Morning, creators 🎬 Keep your work simple and intentional today. One well-made piece is more useful than several rushed attempts.",
        ],
        4: [
            "Good morning, everyone 🎉 It is Friday. Finish the week strong, organise your files, complete your practice, and note what you want to improve next week.",
            "Happy Friday, class 🌟 Take a moment to look at how much you have learned this week. Finish your outstanding practice and keep your best work saved.",
            "Good morning ☀️ Friday is for finishing well. Review your work, make corrections, and keep practising the skills you want to become confident in.",
        ],
    },
    "reminder": {
        0: [
            "📌 Monday reminder: your Monday task is due Tuesday by 6 PM. Start early so you have enough time to test, correct, and submit properly.",
            "📝 Assignment reminder: do not leave the Monday task until the last minute. Submission deadline is Tuesday, 6 PM Nigeria time.",
        ],
        1: [
            "📌 Tuesday reminder: your Tuesday task is due Thursday by 6 PM. Use the time to practise and submit a clean final attempt.",
            "📝 Keep your Tuesday task moving. Deadline is Thursday at 6 PM Nigeria time. If you are stuck, ask for help early.",
        ],
        3: [
            "📌 Thursday reminder: today’s task is due Friday by 5 PM. Check your work carefully before submitting it through the bot.",
            "📝 Thursday task reminder: deadline is Friday, 5 PM Nigeria time. Complete it early enough to review your result before submission.",
        ],
        4: [
            "📌 Friday milestone reminder: your weekly milestone is due Sunday by 11:59 PM. Use the weekend wisely and submit through the bot before the deadline.",
            "📝 Weekly milestone: deadline is Sunday, 11:59 PM Nigeria time. Build it carefully, review it, and submit before the cutoff.",
        ],
    },
}

# Reuse a small set of PostgreSQL connections instead of opening a fresh
# network connection for every Telegram button press. This is especially
# important on free hosting, where repeated TLS/database handshakes can make
# inline buttons feel stuck.
DB_POOL_MIN = max(1, int(os.getenv("DB_POOL_MIN", "1")))
DB_POOL_MAX = max(DB_POOL_MIN, int(os.getenv("DB_POOL_MAX", "5")))
DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "10"))
DB_POOL = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=DB_POOL_MIN,
    max_size=DB_POOL_MAX,
    timeout=DB_POOL_TIMEOUT,
    kwargs={"row_factory": dict_row, "connect_timeout": 10},
    open=False,
)

NAME, AGE, PHONE, EMAIL, FOUND_US, GOAL, OCCUPATION, MOTIVATION, CATEGORY = range(9)
CATEGORIES = ["Student", "Business owner", "Knowledge seeker", "Income seeker"]


# ---------- database ----------
def _normalize_row(row):
    if row is None:
        return None
    out = dict(row)
    for key, value in list(out.items()):
        if isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


class CursorResult:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        return _normalize_row(self.cursor.fetchone())

    def fetchall(self):
        return [_normalize_row(r) for r in self.cursor.fetchall()]


class DatabaseConnection:
    def __init__(self):
        self.conn = None

    def __enter__(self):
        # Borrow an already-open connection from the shared pool.
        self.conn = DB_POOL.getconn(timeout=DB_POOL_TIMEOUT)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.conn is not None:
            try:
                if exc_type is None:
                    self.conn.commit()
                else:
                    self.conn.rollback()
            finally:
                # Return the connection to the pool instead of closing the TCP/TLS
                # connection and forcing the next button press to reconnect.
                DB_POOL.putconn(self.conn)
                self.conn = None
        return False

    def execute(self, query, params=None):
        # The original bot used SQLite-style '?' placeholders. Convert them
        # centrally so the rest of the bot stays readable while using Postgres.
        query = query.replace("?", "%s")
        return CursorResult(self.conn.execute(query, params or ()))


def db():
    return DatabaseConnection()


def init_db():
    # Tables are created in Supabase using heribhee_supabase_schema.sql.
    # At startup we only verify that the database is reachable and the core
    # table exists. This avoids destructive schema changes during a deploy.
    with db() as c:
        c.execute("SELECT user_id FROM students LIMIT 1").fetchall()
    log.info("Supabase/PostgreSQL database connection verified")


def get_student(uid):
    with db() as c:
        return c.execute("SELECT * FROM students WHERE user_id=?", (uid,)).fetchone()


def visible_student_no(student):
    """Return the cohort-facing Student ID shown to students and on ID cards."""
    if not student:
        return "-"
    public_no = (student.get("display_student_no") or "").strip()
    if public_no:
        return public_no
    internal = (student.get("student_no") or "").strip()
    m = re.fullmatch(r"HB-(\d+)", internal, re.I)
    if m:
        return f"HB-{int(m.group(1)):03d}"
    return internal or "-"


def get_student_by_no(student_no):
    """Resolve a user-entered Student ID in the active cohort first."""
    value = (student_no or "").strip().upper()
    if not value:
        return None
    cohort = active_cohort()
    with db() as c:
        row = c.execute(
            """SELECT * FROM students
               WHERE COALESCE(archived,FALSE)=FALSE AND cohort=?
                 AND (display_student_no ILIKE ? OR student_no ILIKE ?)
               ORDER BY registered_at DESC LIMIT 1""",
            (cohort, value, value),
        ).fetchone()
        if row:
            return row
        return c.execute(
            "SELECT * FROM students WHERE student_no ILIKE ? ORDER BY registered_at DESC LIMIT 1",
            (value,),
        ).fetchone()


def next_display_student_no(cursor, cohort):
    """Allocate the lowest unused visible Student ID inside one cohort."""
    rows = cursor.execute(
        """SELECT display_student_no FROM students
           WHERE cohort=? AND display_student_no ~ '^HB-[0-9]+$'""",
        (cohort,),
    ).fetchall()
    used = set()
    for row in rows:
        try:
            used.add(int(str(row.get("display_student_no") or "").split("-", 1)[1]))
        except Exception:
            continue
    number = 1
    while number in used:
        number += 1
    return f"HB-{number:03d}"

def now():
    return datetime.now(TZ)


def _parse_hhmm(value, fallback):
    try:
        hour_s, minute_s = value.split(":", 1)
        return time(int(hour_s), int(minute_s), tzinfo=TZ)
    except Exception:
        log.warning("Invalid schedule time %r. Falling back to %s", value, fallback)
        hour_s, minute_s = fallback.split(":", 1)
        return time(int(hour_s), int(minute_s), tzinfo=TZ)


def get_app_setting(key, default=None):
    try:
        with db() as c:
            row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    except Exception:
        return default


def set_app_setting(key, value):
    with db() as c:
        c.execute(
            "INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
            (key, str(value)),
        )


def active_cohort():
    return (get_app_setting("active_cohort", "Cohort 1") or "Cohort 1").strip()


def remember_staff(user_id, display_name):
    """Keep a friendly staff name so audit/history screens show people, not only Telegram IDs."""
    if user_id not in REVIEWER_IDS:
        return
    try:
        role = "full_admin" if user_id in ADMIN_IDS else "reviewer"
        name = (display_name or str(user_id)).strip()[:160]
        with db() as c:
            c.execute(
                "INSERT INTO staff_directory(user_id,display_name,role,last_seen_at) VALUES(?,?,?,NOW()) "
                "ON CONFLICT (user_id) DO UPDATE SET display_name=EXCLUDED.display_name, role=EXCLUDED.role, last_seen_at=NOW()",
                (int(user_id), name, role),
            )
    except Exception as e:
        log.warning("Could not remember staff identity %s: %s", user_id, e)


def staff_name(user_id):
    if not user_id:
        return "System"
    try:
        with db() as c:
            row = c.execute("SELECT display_name FROM staff_directory WHERE user_id=?", (int(user_id),)).fetchone()
        if row and row.get("display_name"):
            return row["display_name"]
    except Exception:
        pass
    return str(user_id)


def audit_log(actor_user_id, action, target_type="", target_id="", details="", student_user_id=None):
    """Append-only audit trail with staff-name snapshot and optional student linkage."""
    try:
        actor_role = "full_admin" if actor_user_id in ADMIN_IDS else ("reviewer" if actor_user_id in REVIEWER_IDS else "student")
        actor_name = staff_name(actor_user_id) if actor_user_id in REVIEWER_IDS else ("Student" if actor_role == "student" else str(actor_user_id))
        with db() as c:
            c.execute(
                "INSERT INTO audit_log(actor_user_id,actor_name,actor_role,action,target_type,target_id,student_user_id,details,created_at) VALUES(?,?,?,?,?,?,?,?,NOW())",
                (actor_user_id, actor_name[:160], actor_role, action[:120], target_type[:80], str(target_id)[:160], student_user_id, str(details)[:3000]),
            )
    except Exception as e:
        log.warning("Audit log write failed for %s: %s", action, e)



# ---------- weekly knowledge tests ----------
def has_course_access(student):
    """Paid, referral-bonus, or complimentary access unlocks paid-course features."""
    if not student:
        return False
    return bool(student.get("status") == "paid" or student.get("free_access") or student.get("bonus_sent"))


def get_open_test_release(week_number=None, cohort=None):
    """Return an active test release that is currently inside its release window."""
    cohort = cohort or active_cohort()
    try:
        with db() as c:
            if week_number is None:
                return c.execute(
                    "SELECT * FROM weekly_test_releases WHERE cohort=? AND is_active=TRUE AND released_at<=NOW() AND closes_at>NOW() ORDER BY week_number DESC LIMIT 1",
                    (cohort,),
                ).fetchone()
            return c.execute(
                "SELECT * FROM weekly_test_releases WHERE cohort=? AND week_number=? AND is_active=TRUE AND released_at<=NOW() AND closes_at>NOW() LIMIT 1",
                (cohort, int(week_number)),
            ).fetchone()
    except Exception as e:
        log.warning("Could not read weekly test release: %s", e)
        return None


def get_test_release(week_number, cohort=None):
    cohort = cohort or active_cohort()
    try:
        with db() as c:
            return c.execute(
                "SELECT * FROM weekly_test_releases WHERE cohort=? AND week_number=? LIMIT 1",
                (cohort, int(week_number)),
            ).fetchone()
    except Exception:
        return None


def get_passed_test_weeks(uid):
    try:
        with db() as c:
            rows = c.execute(
                "SELECT DISTINCT week_number FROM weekly_test_attempts WHERE user_id=? AND passed=TRUE ORDER BY week_number",
                (uid,),
            ).fetchall()
        return {int(r["week_number"]) for r in rows}
    except Exception as e:
        log.warning("Could not read passed weekly tests for %s: %s", uid, e)
        return set()


def weekly_test_results(uid):
    try:
        with db() as c:
            return c.execute(
                "SELECT DISTINCT ON (week_number) week_number,score,total_questions,percentage,passed,attempt_number,submitted_at "
                "FROM weekly_test_attempts WHERE user_id=? AND submitted_at IS NOT NULL "
                "ORDER BY week_number,attempt_number DESC",
                (uid,),
            ).fetchall()
    except Exception:
        return []


def missing_weekly_tests(uid):
    passed = get_passed_test_weeks(uid)
    return [w for w in (1, 2, 3, 4) if w not in passed]


def _attempt_option_order(attempt, question_id):
    orders = attempt.get("option_orders") or {}
    if isinstance(orders, str):
        try:
            orders = json.loads(orders)
        except Exception:
            orders = {}
    return orders.get(str(question_id), [])


def _attempt_question_order(attempt):
    order = attempt.get("question_order") or []
    if isinstance(order, str):
        try:
            order = json.loads(order)
        except Exception:
            order = []
    return [int(x) for x in order]


def _question_options(question):
    opts = question.get("options") or []
    if isinstance(opts, str):
        try:
            opts = json.loads(opts)
        except Exception:
            opts = []
    return opts


def get_active_attempt(uid, week_number):
    try:
        with db() as c:
            return c.execute(
                "SELECT * FROM weekly_test_attempts WHERE user_id=? AND week_number=? AND status='active' ORDER BY id DESC LIMIT 1",
                (uid, int(week_number)),
            ).fetchone()
    except Exception:
        return None


def get_attempt(attempt_id):
    with db() as c:
        return c.execute("SELECT * FROM weekly_test_attempts WHERE id=?", (int(attempt_id),)).fetchone()


def get_question(question_id):
    with db() as c:
        return c.execute("SELECT * FROM weekly_test_questions WHERE id=? AND is_active=TRUE", (int(question_id),)).fetchone()


def _remaining_seconds(attempt):
    try:
        expires = datetime.fromisoformat(attempt["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=TZ)
        return max(0, int((expires - now()).total_seconds()))
    except Exception:
        return 0


def _format_remaining(seconds):
    mins, secs = divmod(max(0, int(seconds)), 60)
    return f"{mins:02d}:{secs:02d}"


def _result_keyboard(week_number, passed):
    rows = []
    if passed:
        rows.append([InlineKeyboardButton(f"🚀 Open Week {week_number} Project", callback_data=f"project:week:{week_number}")])
    rows.append([InlineKeyboardButton("📈 My Progress", callback_data="menu:progress")])
    rows.append([InlineKeyboardButton("Main menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


async def send_test_result(ctx, uid, attempt, auto_submitted=False):
    passed = bool(attempt.get("passed"))
    score = int(attempt.get("score") or 0)
    total = int(attempt.get("total_questions") or WEEKLY_TEST_QUESTIONS_PER_ATTEMPT)
    pct = float(attempt.get("percentage") or 0)
    week = int(attempt["week_number"])
    attempt_no = int(attempt.get("attempt_number") or 1)
    prefix = "⏰ Time expired — your answers were submitted automatically.\n\n" if auto_submitted else ""
    if passed:
        body = (
            f"{prefix}🎉 WEEK {week} KNOWLEDGE TEST COMPLETED\n\n"
            f"Score: {score}/{total}\nPercentage: {pct:.1f}%\nResult: PASS ✅\nAttempt: {attempt_no} of {WEEKLY_TEST_MAX_ATTEMPTS}\n\n"
            f"Your Week {week} project is now unlocked."
        )
    else:
        attempts_left = max(0, WEEKLY_TEST_MAX_ATTEMPTS - attempt_no)
        if attempts_left:
            retry_at = attempt.get("retry_available_at")
            retry_text = ""
            if retry_at:
                try:
                    dt = datetime.fromisoformat(retry_at)
                    retry_text = f"\nCorrection attempt available from {dt.astimezone(TZ).strftime('%I:%M %p')} (Nigeria time)."
                except Exception:
                    pass
            extra = f"\nAttempts remaining: {attempts_left}.{retry_text}\nReview the week's lessons before retrying."
        else:
            extra = "\nNo automatic attempts remain. Contact the Academy if you need help."
        body = (
            f"{prefix}WEEK {week} KNOWLEDGE TEST COMPLETED\n\n"
            f"Score: {score}/{total}\nPercentage: {pct:.1f}%\nResult: NOT YET PASSED\nPass mark: {WEEKLY_TEST_PASS_PERCENT:.0f}%\nAttempt: {attempt_no} of {WEEKLY_TEST_MAX_ATTEMPTS}{extra}"
        )
    await ctx.bot.send_message(uid, body, reply_markup=_result_keyboard(week, passed))


def finalize_test_attempt(attempt_id, expired=False):
    """Mark an attempt immediately from recorded answers and return the updated row."""
    attempt = get_attempt(attempt_id)
    if not attempt or attempt.get("status") != "active":
        return attempt
    with db() as c:
        stats = c.execute(
            "SELECT COUNT(*) answered, COALESCE(SUM(CASE WHEN is_correct THEN 1 ELSE 0 END),0) correct FROM weekly_test_answers WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        score = int(stats["correct"] or 0)
        total = int(attempt.get("total_questions") or WEEKLY_TEST_QUESTIONS_PER_ATTEMPT)
        pct = round((score * 100.0 / total), 1) if total else 0.0
        passed = pct >= WEEKLY_TEST_PASS_PERCENT
        submitted_at = now()
        retry_at = submitted_at + timedelta(minutes=WEEKLY_TEST_RETRY_COOLDOWN_MINUTES)
        c.execute(
            "UPDATE weekly_test_attempts SET status=?,submitted_at=?,score=?,percentage=?,passed=?,retry_available_at=? WHERE id=?",
            ("expired" if expired else "submitted", submitted_at.isoformat(), score, pct, passed, retry_at.isoformat(), attempt_id),
        )
    audit_log(
        attempt["user_id"],
        "weekly_test_completed",
        "weekly_test",
        f"week-{attempt['week_number']}",
        f"attempt={attempt.get('attempt_number')}; score={score}/{total}; percentage={pct}; passed={passed}; expired={expired}",
        student_user_id=attempt["user_id"],
    )
    return get_attempt(attempt_id)


async def finalize_expired_test_attempts(ctx):
    """Auto-submit expired tests. Called both by the app scheduler and /reminder-check."""
    try:
        with db() as c:
            rows = c.execute(
                "SELECT id,user_id FROM weekly_test_attempts WHERE status='active' AND expires_at<=NOW() ORDER BY id LIMIT 100"
            ).fetchall()
    except Exception as e:
        log.warning("Could not scan expired weekly tests: %s", e)
        return 0
    count = 0
    for row in rows:
        attempt = finalize_test_attempt(row["id"], expired=True)
        if attempt:
            try:
                await send_test_result(ctx, row["user_id"], attempt, auto_submitted=True)
            except Exception as e:
                log.warning("Could not send auto-submitted test result to %s: %s", row["user_id"], e)
            count += 1
    return count


async def scheduled_expired_test_check(ctx: ContextTypes.DEFAULT_TYPE):
    await finalize_expired_test_attempts(ctx)


def _test_attempt_count(uid, week_number):
    with db() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM weekly_test_attempts WHERE user_id=? AND week_number=?",
            (uid, int(week_number)),
        ).fetchone()
    return int(row["n"] or 0)


def _latest_attempt(uid, week_number):
    with db() as c:
        return c.execute(
            "SELECT * FROM weekly_test_attempts WHERE user_id=? AND week_number=? ORDER BY attempt_number DESC LIMIT 1",
            (uid, int(week_number)),
        ).fetchone()


def start_test_attempt(uid, week_number):
    student = get_student(uid)
    if not has_course_access(student):
        return None, "Payment or approved complimentary access is required."
    release = get_open_test_release(week_number, student.get("cohort") or active_cohort())
    if not release:
        return None, "This weekly test is not currently open."
    passed = get_passed_test_weeks(uid)
    if int(week_number) in passed:
        return None, "You have already passed this week's test."
    active = get_active_attempt(uid, week_number)
    if active:
        if _remaining_seconds(active) <= 0:
            finalize_test_attempt(active["id"], expired=True)
        else:
            return active, None
    latest = _latest_attempt(uid, week_number)
    if latest:
        if int(latest.get("attempt_number") or 0) >= WEEKLY_TEST_MAX_ATTEMPTS:
            return None, "You have used all automatic attempts for this week."
        retry_at = latest.get("retry_available_at")
        if retry_at:
            try:
                dt = datetime.fromisoformat(retry_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TZ)
                if now() < dt:
                    return None, f"Your correction attempt opens at {dt.astimezone(TZ).strftime('%I:%M %p')} Nigeria time."
            except Exception:
                pass
    with db() as c:
        questions = c.execute(
            "SELECT id FROM weekly_test_questions WHERE week_number=? AND is_active=TRUE ORDER BY id",
            (int(week_number),),
        ).fetchall()
    ids = [int(r["id"]) for r in questions]
    if not ids:
        return None, "No questions are configured for this week yet."
    count = min(WEEKLY_TEST_QUESTIONS_PER_ATTEMPT, len(ids))
    question_order = random.sample(ids, count)
    option_orders = {}
    with db() as c:
        for qid in question_order:
            q = c.execute("SELECT options FROM weekly_test_questions WHERE id=?", (qid,)).fetchone()
            opts = _question_options(q)
            opt_ids = [str(o["id"]) for o in opts]
            random.shuffle(opt_ids)
            option_orders[str(qid)] = opt_ids
    attempt_number = _test_attempt_count(uid, week_number) + 1
    started = now()
    expires = started + timedelta(minutes=WEEKLY_TEST_DURATION_MINUTES)
    with db() as c:
        row = c.execute(
            "INSERT INTO weekly_test_attempts(user_id,cohort,week_number,attempt_number,started_at,expires_at,status,total_questions,question_order,option_orders,current_index) "
            "VALUES(?,?,?,?,?,?,?,?,?::jsonb,?::jsonb,0) RETURNING *",
            (uid, student.get("cohort") or active_cohort(), int(week_number), attempt_number, started.isoformat(), expires.isoformat(), "active", count, json.dumps(question_order), json.dumps(option_orders)),
        ).fetchone()
    audit_log(uid, "weekly_test_started", "weekly_test", f"week-{week_number}", f"attempt={attempt_number}", student_user_id=uid)
    return row, None


async def render_test_question(ctx, uid, attempt, message=None):
    if not attempt:
        return
    if _remaining_seconds(attempt) <= 0:
        result = finalize_test_attempt(attempt["id"], expired=True)
        await send_test_result(ctx, uid, result, auto_submitted=True)
        return
    order = _attempt_question_order(attempt)
    idx = int(attempt.get("current_index") or 0)
    if idx >= len(order):
        result = finalize_test_attempt(attempt["id"], expired=False)
        await send_test_result(ctx, uid, result)
        return
    qid = order[idx]
    q = get_question(qid)
    if not q:
        result = finalize_test_attempt(attempt["id"], expired=False)
        await send_test_result(ctx, uid, result)
        return
    options = {str(o["id"]): o["text"] for o in _question_options(q)}
    option_order = _attempt_option_order(attempt, qid) or list(options)
    letters = "ABCD"
    kb = []
    for i, opt_id in enumerate(option_order):
        if opt_id not in options:
            continue
        kb.append([InlineKeyboardButton(f"{letters[i]}. {options[opt_id]}", callback_data=f"test:answer:{attempt['id']}:{qid}:{opt_id}")])
    text = (
        f"🧠 WEEK {attempt['week_number']} KNOWLEDGE TEST\n\n"
        f"Question {idx+1} of {len(order)}\n"
        f"Time remaining: {_format_remaining(_remaining_seconds(attempt))}\n\n"
        f"{q['question_text']}"
    )
    markup = InlineKeyboardMarkup(kb)
    if message is not None:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await ctx.bot.send_message(uid, text, reply_markup=markup)


async def weekly_test_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    student = get_student(uid)
    if not has_course_access(student):
        await q.answer("This feature is available after payment/access approval.", show_alert=True)
        return
    if data.startswith("project:week:"):
        await q.answer()
        week = int(data.rsplit(":", 1)[1])
        if week not in get_passed_test_weeks(uid):
            await q.message.reply_text("Your weekly project unlocks after you pass this week's knowledge test.")
            return
        await q.message.reply_text(
            f"🚀 WEEK {week} PROJECT UNLOCKED\n\n"
            "Use the weekly project brief given by your instructor/live session. Complete the practical project, then submit it through Assignments in this bot.\n\n"
            "The knowledge test is only the checkpoint; the project is where you prove the practical skill.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Submit Assignment", callback_data="assignment:submitinfo")],[InlineKeyboardButton("Main menu", callback_data="menu:home")]])
        )
        return
    if data.startswith("test:start:"):
        await q.answer()
        week = int(data.rsplit(":", 1)[1])
        release = get_open_test_release(week, student.get("cohort") or active_cohort())
        if not release:
            await q.message.reply_text("This weekly test is not currently open.")
            return
        latest = _latest_attempt(uid, week)
        if latest and latest.get("passed"):
            await q.message.reply_text(f"✅ You already passed Week {week}: {latest.get('score')}/{latest.get('total_questions')} ({float(latest.get('percentage') or 0):.1f}%).")
            return
        active = get_active_attempt(uid, week)
        if active and _remaining_seconds(active) > 0:
            await render_test_question(ctx, uid, active)
            return
        attempts = _test_attempt_count(uid, week)
        if attempts >= WEEKLY_TEST_MAX_ATTEMPTS:
            await q.message.reply_text("You have used all automatic attempts for this week. Please contact the Academy if you need help.")
            return
        await q.message.reply_text(
            f"🧠 WEEK {week} KNOWLEDGE TEST\n\n"
            f"Questions: up to {WEEKLY_TEST_QUESTIONS_PER_ATTEMPT}\nTime: {WEEKLY_TEST_DURATION_MINUTES} minutes\nPass mark: {WEEKLY_TEST_PASS_PERCENT:.0f}%\nMaximum attempts: {WEEKLY_TEST_MAX_ATTEMPTS}\n\n"
            "The timer starts only after you press START NOW. Once started, it cannot be paused. The bot marks the test automatically and shows your result immediately.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ START NOW", callback_data=f"test:confirm:{week}")],[InlineKeyboardButton("Not now", callback_data="menu:home")]])
        )
        return
    if data.startswith("test:confirm:"):
        await q.answer()
        week = int(data.rsplit(":", 1)[1])
        attempt, error = start_test_attempt(uid, week)
        if error:
            await q.message.reply_text(error, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main menu", callback_data="menu:home")]]))
            return
        await render_test_question(ctx, uid, attempt, message=q.message)
        return
    if data.startswith("test:answer:"):
        parts = data.split(":")
        if len(parts) != 5:
            await q.answer("Invalid test response.", show_alert=True); return
        _, _, attempt_id_s, question_id_s, option_id = parts
        attempt_id = int(attempt_id_s); question_id = int(question_id_s)
        attempt = get_attempt(attempt_id)
        if not attempt or int(attempt.get("user_id") or 0) != uid:
            await q.answer("This test attempt does not belong to your account.", show_alert=True); return
        if attempt.get("status") != "active":
            await q.answer("This attempt is already closed.", show_alert=True); return
        if _remaining_seconds(attempt) <= 0:
            await q.answer("Time is up.", show_alert=True)
            result = finalize_test_attempt(attempt_id, expired=True)
            await send_test_result(ctx, uid, result, auto_submitted=True)
            return
        order = _attempt_question_order(attempt)
        idx = int(attempt.get("current_index") or 0)
        if idx >= len(order) or int(order[idx]) != question_id:
            await q.answer("That question is no longer active.", show_alert=True); return
        question = get_question(question_id)
        if not question:
            await q.answer("Question unavailable.", show_alert=True); return
        valid_ids = {str(o["id"]) for o in _question_options(question)}
        if option_id not in valid_ids:
            await q.answer("Invalid answer.", show_alert=True); return
        is_correct = option_id == str(question["correct_option_id"])
        try:
            with db() as c:
                c.execute(
                    "INSERT INTO weekly_test_answers(attempt_id,question_id,selected_option_id,is_correct,answered_at) VALUES(?,?,?,?,NOW()) ON CONFLICT (attempt_id,question_id) DO NOTHING",
                    (attempt_id, question_id, option_id, is_correct),
                )
                c.execute("UPDATE weekly_test_attempts SET current_index=current_index+1 WHERE id=?", (attempt_id,))
        except Exception as e:
            log.warning("Could not record test answer: %s", e)
            await q.answer("Could not record that answer. Please tap again.", show_alert=True); return
        await q.answer("Answer recorded")
        updated = get_attempt(attempt_id)
        if int(updated.get("current_index") or 0) >= len(order):
            result = finalize_test_attempt(attempt_id, expired=False)
            try:
                await q.message.edit_text("✅ Final answer recorded. Marking your test...")
            except Exception:
                pass
            await send_test_result(ctx, uid, result)
            return
        await render_test_question(ctx, uid, updated, message=q.message)
        return


async def release_weekly_test(ctx, admin_uid, week_number):
    cohort = active_cohort()
    released = now()
    closes = released + timedelta(hours=WEEKLY_TEST_WINDOW_HOURS)
    with db() as c:
        c.execute(
            "INSERT INTO weekly_test_releases(cohort,week_number,released_at,closes_at,released_by,is_active) VALUES(?,?,?,?,?,TRUE) "
            "ON CONFLICT (cohort,week_number) DO UPDATE SET released_at=EXCLUDED.released_at,closes_at=EXCLUDED.closes_at,released_by=EXCLUDED.released_by,is_active=TRUE",
            (cohort, int(week_number), released.isoformat(), closes.isoformat(), admin_uid),
        )
        students = c.execute(
            "SELECT user_id FROM students WHERE COALESCE(archived,FALSE)=FALSE AND cohort=? AND (status='paid' OR COALESCE(free_access,FALSE)=TRUE OR COALESCE(bonus_sent,FALSE)=TRUE)",
            (cohort,),
        ).fetchall()
    sent = 0
    for s in students:
        try:
            await ctx.bot.send_message(
                s["user_id"],
                f"🧠 WEEK {week_number} KNOWLEDGE TEST IS NOW LIVE\n\n"
                "The live session has ended. Complete this short knowledge check before starting your weekly project.\n\n"
                f"Questions: {WEEKLY_TEST_QUESTIONS_PER_ATTEMPT}\nTime once started: {WEEKLY_TEST_DURATION_MINUTES} minutes\nPass mark: {WEEKLY_TEST_PASS_PERCENT:.0f}%\n"
                f"Available until: {closes.strftime('%a, %d %b %Y %I:%M %p')} Nigeria time\n\n"
                "Your project unlocks immediately after you pass.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"START WEEK {week_number} TEST", callback_data=f"test:start:{week_number}")]])
            )
            sent += 1
        except Exception as e:
            log.warning("Could not notify student %s of weekly test: %s", s["user_id"], e)
        await asyncio.sleep(0.03)
    audit_log(admin_uid, "weekly_test_released", "weekly_test", f"week-{week_number}", f"cohort={cohort}; notified={sent}")
    return sent, closes


def revoke_weekly_test(admin_uid, week_number, clear_attempts=False):
    """Close a released weekly test immediately.

    clear_attempts=False preserves completed results and only closes the release.
    clear_attempts=True is a test/clearance reset: it also removes all attempts
    and answers for the active cohort/week so the week behaves as never tested.
    """
    cohort = active_cohort()
    with db() as c:
        c.execute(
            "UPDATE weekly_test_releases SET is_active=FALSE, closes_at=NOW() WHERE cohort=? AND week_number=?",
            (cohort, int(week_number)),
        )
        # Cancel any attempt that was still running so old inline buttons stop working.
        c.execute(
            "UPDATE weekly_test_attempts SET status='revoked', submitted_at=COALESCE(submitted_at,NOW()) "
            "WHERE cohort=? AND week_number=? AND status='active'",
            (cohort, int(week_number)),
        )
        removed = 0
        if clear_attempts:
            row = c.execute(
                "SELECT COUNT(*) n FROM weekly_test_attempts WHERE cohort=? AND week_number=?",
                (cohort, int(week_number)),
            ).fetchone()
            removed = int(row["n"] or 0)
            # weekly_test_answers are ON DELETE CASCADE from attempts.
            c.execute(
                "DELETE FROM weekly_test_attempts WHERE cohort=? AND week_number=?",
                (cohort, int(week_number)),
            )
            # Remove the release row too so the admin panel returns to Not released.
            c.execute(
                "DELETE FROM weekly_test_releases WHERE cohort=? AND week_number=?",
                (cohort, int(week_number)),
            )
    action = "weekly_test_reset" if clear_attempts else "weekly_test_revoked"
    audit_log(admin_uid, action, "weekly_test", f"week-{week_number}", f"cohort={cohort}; attempts_removed={removed}")
    return removed


def wipe_student_record(admin_uid, student_uid):
    """Permanently remove a student and student-owned course data from the bot."""
    student = get_student(int(student_uid))
    if not student:
        return None
    snapshot = {
        "user_id": int(student["user_id"]),
        "name": student.get("name") or "Unknown",
        "student_no": visible_student_no(student),
        "internal_student_no": student.get("student_no") or "-",
    }
    if student.get("certificate_issued_at") or student.get("certificate_number"):
        snapshot["protected"] = True
        return snapshot
    with db() as c:
        # These tables are explicitly cleared so a removed Telegram account can
        # register again as a genuinely fresh student.
        c.execute("DELETE FROM weekly_test_attempts WHERE user_id=?", (int(student_uid),))
        c.execute("DELETE FROM moderation_reports WHERE user_id=?", (int(student_uid),))
        c.execute("DELETE FROM support_tickets WHERE user_id=?", (int(student_uid),))
        c.execute("DELETE FROM assignment_submissions WHERE user_id=?", (int(student_uid),))
        c.execute("DELETE FROM payments WHERE user_id=?", (int(student_uid),))
        c.execute("DELETE FROM students WHERE user_id=?", (int(student_uid),))
    # Keep one admin-side audit event showing that a full admin intentionally
    # performed the deletion; it contains no course answers or payment proof.
    audit_log(admin_uid, "student_wiped", "student", snapshot["student_no"], f"name={snapshot['name']}; telegram={snapshot['user_id']}")
    return snapshot


async def send_weekly_test_admin_panel(ctx, uid):
    cohort = active_cohort()
    lines = ["🧠 WEEKLY KNOWLEDGE TESTS", f"Cohort: {cohort}", "", "Release a test immediately after that week's live session."]
    kb = []
    for week in (1, 2, 3, 4):
        rel = get_test_release(week, cohort)
        if rel and rel.get("is_active") and rel.get("closes_at"):
            try:
                close_dt = datetime.fromisoformat(rel["closes_at"])
                open_now = get_open_test_release(week, cohort) is not None
                status = f"LIVE until {close_dt.astimezone(TZ).strftime('%d %b %I:%M %p')}" if open_now else "Closed"
            except Exception:
                status = "Released"
        else:
            status = "Not released"
        lines.append(f"Week {week}: {status}")
        kb.append([
            InlineKeyboardButton(f"🎙 Release W{week}", callback_data=f"admin:tests:release:{week}"),
            InlineKeyboardButton(f"🚫 Revoke W{week}", callback_data=f"admin:tests:revoke:{week}"),
        ])
        kb.append([
            InlineKeyboardButton(f"📊 W{week} Results", callback_data=f"admin:tests:results:{week}"),
            InlineKeyboardButton(f"🧹 Reset W{week}", callback_data=f"admin:tests:reset:{week}"),
        ])
    kb.append([InlineKeyboardButton("Admin dashboard", callback_data="admin:home")])
    await ctx.bot.send_message(uid, "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

def certificate_verify_url(cert_no):
    base = (os.getenv("RENDER_EXTERNAL_URL", "").strip() or WEBHOOK_URL).rstrip("/")
    if not base:
        return ""
    if base.endswith("/telegram"):
        base = base[:-9].rstrip("/")
    return f"{base}/verify-certificate/{cert_no}"


def get_certificate_record(cert_no):
    with db() as c:
        return c.execute(
            "SELECT name,student_no,display_student_no,certificate_number,certificate_issued_at,status FROM students WHERE certificate_number ILIKE ? AND certificate_issued_at IS NOT NULL",
            (cert_no.strip(),),
        ).fetchone()


def group_messages_enabled():
    default = "true" if GROUP_MESSAGES_DEFAULT_ENABLED else "false"
    return str(get_app_setting("group_messages_enabled", default)).lower() in {"1", "true", "yes", "on"}


WEEKDAY_NAMES = {0: "Monday", 1: "Tuesday", 3: "Thursday", 4: "Friday"}
CLASS_REMINDER_WEEKDAYS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
CLASS_REMINDER_OFFSETS = (60, 30, 10, 0)


def get_admin_class_reminders():
    try:
        with db() as c:
            return c.execute(
                "SELECT * FROM admin_class_reminders ORDER BY weekday,class_time,id"
            ).fetchall()
    except Exception as e:
        log.warning("Could not read admin class reminders: %s", e)
        return []


def _format_class_time(value):
    try:
        h, m = [int(x) for x in str(value).split(":", 1)]
        suffix = "AM" if h < 12 else "PM"
        display_h = h % 12 or 12
        return f"{display_h}:{m:02d} {suffix}"
    except Exception:
        return str(value)


def _valid_hhmm(value):
    try:
        h, m = [int(x) for x in value.strip().split(":", 1)]
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False


async def _send_admin_class_reminder(ctx, reminder, offset):
    title = (reminder.get("title") or "Class").strip()
    when = _format_class_time(reminder.get("class_time"))
    if offset == 60:
        timing = "starts in 1 hour"
    elif offset == 30:
        timing = "starts in 30 minutes"
    elif offset == 10:
        timing = "starts in 10 minutes"
    else:
        timing = "starts now"
    message = (
        f"⏰ CLASS REMINDER\n\n{title} {timing}.\n"
        f"Scheduled time: {when} (Nigeria time)."
    )
    recipients = list(ADMIN_IDS)
    if ADMIN_GROUP_ID:
        recipients.append(ADMIN_GROUP_ID)
    sent_to = set()
    for recipient in recipients:
        if recipient in sent_to:
            continue
        sent_to.add(recipient)
        try:
            await ctx.bot.send_message(recipient, message)
        except Exception as e:
            log.warning("Could not send class reminder to %s: %s", recipient, e)


async def check_admin_class_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    """Check editable class schedules and notify admins at 60/30/10/0 minutes."""
    current = now()
    rows = get_admin_class_reminders()
    for r in rows:
        if not r.get("enabled", True) or int(r.get("weekday")) != current.weekday():
            continue
        try:
            hh, mm = [int(x) for x in str(r.get("class_time")).split(":", 1)]
        except Exception:
            continue
        class_dt = current.replace(hour=hh, minute=mm, second=0, microsecond=0)
        minutes_to_class = (class_dt - current).total_seconds() / 60
        for offset in CLASS_REMINDER_OFFSETS:
            # Allow a twelve-minute grace window so a 5-10 minute external wake-up
            # can still deliver the reminder once after Render has been asleep.
            if offset - 12 < minutes_to_class <= offset:
                occurrence = current.date().isoformat()
                with db() as c:
                    row = c.execute(
                        "SELECT 1 FROM admin_class_reminder_log WHERE reminder_id=? AND occurrence_date=? AND offset_minutes=?",
                        (r["id"], occurrence, offset),
                    ).fetchone()
                    if row:
                        continue
                    c.execute(
                        "INSERT INTO admin_class_reminder_log(reminder_id,occurrence_date,offset_minutes,sent_at) VALUES(?,?,?,NOW())",
                        (r["id"], occurrence, offset),
                    )
                await _send_admin_class_reminder(ctx, r, offset)



def get_group_pack(kind, weekday):
    """Return admin-edited messages for a day, falling back to the built-in pack."""
    try:
        with db() as c:
            rows = c.execute(
                "SELECT message FROM group_message_pack WHERE kind=? AND weekday=? AND active=TRUE ORDER BY position,id",
                (kind, weekday),
            ).fetchall()
        if rows:
            return [r["message"] for r in rows]
    except Exception as e:
        log.warning("Could not read custom group message pack: %s", e)
    return list(GROUP_MESSAGE_PACK.get(kind, {}).get(weekday, []))


def save_group_pack(kind, weekday, messages):
    """Replace one day/category message pack with the supplied messages."""
    with db() as c:
        c.execute("DELETE FROM group_message_pack WHERE kind=? AND weekday=?", (kind, weekday))
        for pos, message in enumerate(messages):
            c.execute(
                "INSERT INTO group_message_pack(kind,weekday,position,message,active,updated_at) VALUES(?,?,?,?,TRUE,NOW())",
                (kind, weekday, pos, message),
            )


def reset_group_pack(kind, weekday):
    with db() as c:
        c.execute("DELETE FROM group_message_pack WHERE kind=? AND weekday=?", (kind, weekday))


def _message_for(kind, dt=None):
    dt = dt or now()
    weekday = dt.weekday()
    options = get_group_pack(kind, weekday)
    if not options:
        return None
    # Deterministic weekly rotation: changes each week but remains predictable.
    index = dt.isocalendar().week % len(options)
    return options[index]


def referral_count(student_no):
    with db() as c:
        return c.execute(
            "SELECT COUNT(*) n FROM students WHERE referred_by ILIKE ?",
            (student_no,),
        ).fetchone()["n"]


# ---------- registration form ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in REVIEWER_IDS:
        await send_admin_dashboard(ctx, uid)
        return ConversationHandler.END
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

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Register as a New Student", callback_data="register:new")],
        [InlineKeyboardButton("🔐 Recover Existing Student Account", callback_data="recover:start")],
    ])
    await update.message.reply_text(
        f"Welcome to the {PROGRAM}! 🎬\n\n"
        "If this is your first time here, choose Register as a New Student.\n\n"
        "If you registered before but now use a different Telegram account, choose Recover Existing Student Account.",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def begin_registration(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "Before anything else, we'd like to get to know you properly — this isn't just a "
        "mailing list signup, it's a short application so we understand who's joining us "
        "and can support you better.\n\n"
        "It takes about 2–3 minutes. Let's start:\n\nWhat's your full name?"
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
        "What do you currently do?\n\n"
        "For example: Student, Fashion Designer, Business Owner, Video Editor, Teacher, "
        "Photographer, Content Creator, Trader, Engineer, etc.\n\n"
        "Please type your actual occupation, profession, business, or current role. This will appear on your student ID card."
    )
    return OCCUPATION


async def got_occupation(update, ctx):
    occupation = (update.message.text or "").strip()[:120]
    if len(occupation) < 2:
        await update.message.reply_text("Please type what you currently do, for example: Student, Trader, Teacher, Video Editor or Content Creator.")
        return OCCUPATION
    ctx.user_data["occupation"] = occupation
    log.info("Registration occupation captured for Telegram user %s", update.effective_user.id)
    await update.message.reply_text(
        f"Got it: {occupation}. ✅\n\nWhy does this training matter to you right now? Tell us briefly what you hope it will help you achieve."
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
        # Use the highest existing student number instead of COUNT(*).
        # COUNT(*) can reuse an old number after a test/student record is deleted,
        # which can make registration fail at the final step because student_no is unique.
        row = c.execute(
            """SELECT COALESCE(MAX(CAST(SUBSTRING(student_no FROM 4) AS INTEGER)), 0) AS max_no
               FROM students
               WHERE student_no ~ '^HB-[0-9]+$'"""
        ).fetchone()
        next_no = int(row["max_no"] or 0) + 1
        # Keep student_no globally unique for legacy records/referral links.
        # display_student_no is the clean cohort-facing ID and restarts at 001.
        student_no = f"HB-{next_no:04d}"
        cohort_name = active_cohort()
        display_student_no = next_display_student_no(c, cohort_name)
        c.execute(
            """INSERT INTO students
               (user_id, username, name, age, phone, email, found_us, goal, occupation, motivation,
                category, source, plan, student_no, display_student_no, status, paid_amount, registered_at,
                referred_by, bonus_sent, cohort, archived)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,'registered',0,?,?,FALSE,?,FALSE)
               ON CONFLICT (user_id) DO UPDATE SET
                 username=EXCLUDED.username, name=EXCLUDED.name, age=EXCLUDED.age,
                 phone=EXCLUDED.phone, email=EXCLUDED.email, found_us=EXCLUDED.found_us,
                 goal=EXCLUDED.goal, occupation=EXCLUDED.occupation, motivation=EXCLUDED.motivation, category=EXCLUDED.category,
                 source=EXCLUDED.source, referred_by=EXCLUDED.referred_by""",
            (u.id, u.username, d["name"], d["age"], d["phone"], d["email"],
             d["found_us"], d["goal"], d["occupation"], d["motivation"], cat,
             d.get("source", "direct"), student_no, display_student_no, now().isoformat(), referred_by, cohort_name),
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
            "SELECT COUNT(*) n FROM students WHERE bonus_sent=TRUE"
        ).fetchone()["n"]

    if granted_so_far < REFERRAL_FREE_ACCESS_CAP:
        with db() as c:
            c.execute(
                "UPDATE students SET bonus_sent=TRUE, status='paid', paid_amount=?, second_due=NULL WHERE student_no=?",
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
            c.execute("UPDATE students SET bonus_sent=TRUE WHERE student_no=?", (referrer_no,))
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
        await ctx.bot.send_message(
            uid,
            "The curriculum file is temporarily unavailable. Please contact an Academy admin."
        )
        return False
    try:
        with open(CURRICULUM_FILE, "rb") as f:
            await ctx.bot.send_document(
                uid,
                f,
                filename="Heribhee_AI_Video_Making_Curriculum.pdf",
                caption="📄 Your official Heribhee AI Video & Movie Making Training curriculum.",
            )
        return True
    except Exception as e:
        log.warning("Could not send curriculum: %s", e)
        await ctx.bot.send_message(uid, "Sorry, I couldn't send the curriculum just now. Please try again shortly.")
        return False


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
        f"Rules accepted. Your registration is complete!\n\nStudent ID: {visible_student_no(s)}\n"
        "Here is your student ID card, official course outline, and crash-course WhatsApp link.",
    )
    try:
        id_card = cards.generate_id_card(s["name"], s.get("occupation") or s.get("category") or "Academy Student", visible_student_no(s), PROGRAM)
        await ctx.bot.send_photo(uid, id_card, caption=f"Your Heribhee Academy Student ID — {visible_student_no(s)}")
    except Exception as e:
        log.warning("Could not generate/send ID card: %s", e)
        await ctx.bot.send_message(uid, f"Your student ID is: {visible_student_no(s)}")
    await send_curriculum_to(ctx, uid)
    if CRASH_COURSE_LINK:
        await ctx.bot.send_message(
            uid,
            "🚀 FREE CRASH COURSE\n\nThis is your first classroom/landing group. Start here for the basics, orientation, and course introduction.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Crash Course", url=CRASH_COURSE_LINK)]])
        )
    else:
        await ctx.bot.send_message(uid, "Your crash-course group link is not configured yet. Please contact an Academy admin.")
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
            "INSERT INTO payments (user_id, amount, proof_file_id, created_at) VALUES (?,?,?,?) RETURNING id",
            (uid, amount, file_id, now().isoformat()),
        )
        pid = cur.fetchone()["id"]
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
            audit_log(q.from_user.id, "payment_rejected", "payment", pid, f"user_id={p['user_id']}", student_user_id=p["user_id"])
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
    audit_log(q.from_user.id, "payment_approved", "payment", pid, f"user_id={p['user_id']}; amount={p['amount']}; status={status}", student_user_id=p["user_id"])
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
    if s.get("free_access"):
        await update.message.reply_text(
            f"Student ID: {visible_student_no(s)}\nAccess: Complimentary paid-class access granted\nRecorded payment: ₦{int(s['paid_amount'] or 0):,}."
        )
        return
    await update.message.reply_text(
        f"Student ID: {visible_student_no(s)}\nStatus: {s['status']}\nPaid: ₦{s['paid_amount']:,} of ₦{PRICE_FULL:,}\nBalance: ₦{max(PRICE_FULL - s['paid_amount'], 0):,}\n\n{BANK_DETAILS}\n\nUse Payment & Status in the menu to submit your receipt."
    )


async def certificate_cmd(update, ctx):
    uid = update.effective_user.id
    if not get_student(uid):
        await update.message.reply_text("You're not registered yet. Send /start.")
        return
    await resend_issued_certificate(ctx, uid)


async def verify_certificate_cmd(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Usage: /verify <certificate number>\nExample: /verify HB-CERT-0007")
        return
    cert_no = ctx.args[0].strip().upper()
    r = get_certificate_record(cert_no)
    if not r:
        await update.message.reply_text("❌ No issued Heribhee certificate matches that certificate number.")
        return
    issued = datetime.fromisoformat(r["certificate_issued_at"]).strftime("%d %b %Y") if r.get("certificate_issued_at") else "-"
    await update.message.reply_text(
        f"✅ VERIFIED HERIBHEE CERTIFICATE\n\nCertificate No: {r['certificate_number']}\nRecipient: {r['name']}\nStudent ID: {visible_student_no(r)}\nProgram: {PROGRAM}\nIssued: {issued}\n\nIf the name or certificate number on the presented certificate does not match this record, treat that document as altered or invalid."
    )


async def review_cmd(update, ctx):
    if update.effective_user.id not in REVIEWER_IDS:
        await update.message.reply_text("This command is for assigned reviewers only.")
        return
    await update.message.reply_text("ASSIGNMENT REVIEWER DASHBOARD\nChoose pending assignments:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Pending reviews", callback_data="admin:pending:0")]]))


async def chatid_cmd(update, ctx):
    await update.effective_message.reply_text(
        f"Your Telegram user ID: {update.effective_user.id}\nThis chat ID is: {update.effective_chat.id}"
    )


async def id_cmd(update, ctx):
    if update.effective_user.id in ADMIN_IDS:
        await update.message.reply_text(f"Your Telegram user ID: {update.effective_user.id}")
        return
    if not get_student(update.effective_user.id):
        await update.message.reply_text("You're not registered yet. Send /start.")
        return
    await send_student_id_card(ctx, update.effective_user.id)


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
               GROUP BY referred_by ORDER BY n DESC LIMIT 10"""
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


async def send_student_id_card(ctx, uid):
    s = get_student(uid)
    if not s:
        return False
    try:
        id_card = cards.generate_id_card(
            s["name"],
            s.get("occupation") or s.get("category") or "Academy Student",
            visible_student_no(s) or "HB-000",
            PROGRAM,
        )
        await ctx.bot.send_photo(uid, id_card, caption=f"🪪 Your Heribhee Academy Student ID — {visible_student_no(s)}")
        return True
    except Exception as e:
        log.warning("Could not generate/send ID card: %s", e)
        await ctx.bot.send_message(uid, f"Your student ID is: {visible_student_no(s)}")
        return False


async def resend_issued_certificate(ctx, uid):
    s = get_student(uid)
    if not s:
        return False
    if not s.get("certificate_issued_at") or not s.get("certificate_number"):
        await ctx.bot.send_message(
            uid,
            "Your certificate has not been issued by the Academy yet. Once it has been officially issued, you can re-download it here anytime."
        )
        return False
    try:
        date_str = datetime.fromisoformat(s["certificate_issued_at"]).strftime("%d %b %Y")
        cert = cards.generate_certificate(s["name"], PROGRAM, date_str, s["certificate_number"])
        await ctx.bot.send_photo(
            uid, cert,
            caption=f"🎓 Your certificate — {s['certificate_number']}\nYou can request this again anytime if you lose it or change devices."
        )
        return True
    except Exception as e:
        log.warning("Could not regenerate certificate: %s", e)
        await ctx.bot.send_message(uid, "Sorry, something went wrong regenerating your certificate. Please try again later.")
        return False


def _clean_phone(value):
    return "".join(ch for ch in (value or "") if ch.isdigit())


def student_keyboard(uid=None):
    rows = [
        [InlineKeyboardButton("📚 My Classes", callback_data="menu:classes"), InlineKeyboardButton("📝 Assignments", callback_data="menu:assignments")],
    ]
    # Weekly tests are intentionally invisible until both conditions are true:
    # (1) paid/approved course access and (2) the admin has released the test after the live session.
    if uid is not None:
        s = get_student(uid)
        if has_course_access(s):
            rel = get_open_test_release(cohort=(s.get("cohort") or active_cohort()))
            if rel and int(rel["week_number"]) not in get_passed_test_weeks(uid):
                rows.append([InlineKeyboardButton(f"🧠 Week {rel['week_number']} Knowledge Test", callback_data=f"test:start:{rel['week_number']}")])
    rows += [
        [InlineKeyboardButton("🤖 Ask AI", callback_data="menu:assistant"), InlineKeyboardButton("💬 Ask Admin", callback_data="menu:ask")],
        [InlineKeyboardButton("❓ Help & FAQs", callback_data="menu:help"), InlineKeyboardButton("📖 Student Manual", callback_data="menu:manual")],
        [InlineKeyboardButton("📈 My Progress", callback_data="menu:progress"), InlineKeyboardButton("📜 Rules & Regulations", callback_data="menu:rules")],
        [InlineKeyboardButton("👥 Refer a Friend", callback_data="menu:refer"), InlineKeyboardButton("🎓 Certification", callback_data="menu:cert")],
        [InlineKeyboardButton("💳 Payment & Status", callback_data="menu:status"), InlineKeyboardButton("👤 My Profile & Documents", callback_data="menu:profile")],
    ]
    return InlineKeyboardMarkup(rows)


STUDENT_MANUAL = """📖 HERIBHEE STUDENT MANUAL

📚 My Classes
Opens your current class access. Before paid access is approved, it shows the free crash-course group. After approved payment or complimentary access, it shows the main paid-class link.

📝 Assignments
Shows assignment deadlines and the Submit Assignment button. After a weekly live session, paid/approved students complete the short knowledge test first; passing it unlocks that week’s project. Send your project/file/photo/video/text through the bot and include the assignment name.

🤖 Ask AI
A free Heribhee Academy assistant. Ask about registration, account recovery, rules, assignments, class access, certificates, profile/documents, referrals, payment procedure or how to use the bot. It uses Academy information only and will direct you to Ask Admin when human help is needed.

💬 Ask Admin
Use this for personal issues, unclear cases, corrections or anything the Academy assistant cannot resolve. Your question is sent privately to the admin/reviewer team.

❓ Help & FAQs
Quick answers to common questions about the training, assignments, certification, payments/referrals and conduct.

📖 Student Manual
Opens this guide again.

📈 My Progress
Shows assignments you have submitted, review status, and weekly knowledge-test results.

📜 Rules & Regulations
Opens the Academy rules. New students must read and accept them before receiving the registration pack.

👥 Refer a Friend
Shows your personal referral link and referral count.

🎓 Certification
Shows your certificate status. Once the Academy issues your certificate, you can download it again from My Profile & Documents.

💳 Payment & Status
Use this only when the Academy asks students to make payment. It shows your recorded payment status and lets you submit proof for verification.

👤 My Profile & Documents
Re-download your Student ID and curriculum, update your name or occupation once, and re-download an issued certificate.

🔐 Account Recovery
If you move to a new phone but keep the same Telegram account, nothing changes. If you use a completely new Telegram account, send /start and choose Recover Existing Account. You will need your Student ID plus the phone number or email used during registration."""


def academy_assistant_answer(question, student=None):
    """Free rule-based Academy assistant. It never calls a paid AI service."""
    q = " ".join((question or "").lower().strip().split())
    if not q:
        return "Please type a question about Heribhee Academy or how to use the bot."

    if any(k in q for k in ("recover", "recovery", "new phone", "new telegram", "lost account", "change account")):
        return (
            "For account recovery: if you only changed phones but kept the same Telegram account, your record stays linked automatically. "
            "If you now use a different Telegram account, send /start and choose Recover Existing Account. You will be asked for your Student ID and the phone number or email used during registration."
        )
    if any(k in q for k in ("sign up", "signup", "register", "registration", "join academy", "enrol", "enroll")):
        return (
            "To register, send /start and choose the new-student registration option. Complete the questions, then read and accept the Academy rules. "
            "After that, the bot sends your Student ID, curriculum and free crash-course access."
        )
    if any(k in q for k in ("rule", "conduct", "abuse", "language", "group rule")):
        return (
            "The Academy rules cover respectful behaviour, assignment/submission expectations, class access and responsible participation. "
            "Open Rules & Regulations from the student menu to read every section. If you need a ruling on a specific situation, use Ask Admin."
        )
    if any(k in q for k in ("assignment", "submit", "homework", "task", "deadline", "score", "mark")):
        return (
            "Open Assignments from the student menu. Current deadlines are: Monday task → Tuesday 6 PM, Tuesday task → Thursday 6 PM, "
            "Thursday task → Friday 5 PM, and Friday milestone → Sunday 11:59 PM, Nigeria time. Use Submit Assignment and include the assignment name. "
            "An authorized reviewer can score it and send feedback privately through the bot."
        )
    if any(k in q for k in ("class link", "my class", "paid class", "crash course", "class access", "access class")):
        if student and (student.get("status") == "paid" or student.get("free_access") or student.get("bonus_sent")):
            return "Your main class access is unlocked. Open My Classes and use the Join Paid Class button."
        return (
            "After registration and rules acceptance, My Classes gives you the free crash-course access. The separate main class appears after approved payment or complimentary/free access is granted by a full admin."
        )
    if any(k in q for k in ("certificate", "certification", "cert", "graduate", "completion")):
        return (
            "Certificates are issued after the required assignments/final project and Academy verification. Once yours has been issued, open My Profile & Documents → Get My Certificate to download it again anytime."
        )
    if any(k in q for k in ("id card", "student id", "curriculum", "profile", "document", "change name", "occupation", "role")):
        return (
            "Open My Profile & Documents. You can re-download your Student ID and curriculum there. You can also change your name once and your occupation/role once. "
            "For another correction after that, use Ask Admin."
        )
    if any(k in q for k in ("payment", "pay", "bank", "receipt", "proof", "balance", "fee")):
        return (
            "The Academy will tell students when payment is open. When instructed, open Payment & Status in the bot, choose the appropriate payment option and submit your receipt for admin verification. "
            "The bot does not send automatic payment reminders."
        )
    if any(k in q for k in ("free access", "complimentary", "referral", "refer", "friend")):
        return (
            "Open Refer a Friend to get your personal referral link and see your referral count. Complimentary paid-class access can also be granted directly by a full admin. "
            "If complimentary access has been granted, My Classes will show the paid-class link without changing your recorded payment amount."
        )
    if any(k in q for k in ("help", "how bot", "how does", "menu", "button", "manual", "what can")):
        return (
            "Use Student Manual for a button-by-button guide. You can also ask me about registration, recovery, rules, assignments, classes, certificates, profile/documents, referrals or payment procedure."
        )
    return (
        "I don't have a reliable Academy answer for that question. Please use Ask Admin so a person can help you rather than me guessing."
    )


async def send_student_manual(ctx, uid):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶ My Classes", callback_data="menu:classes"), InlineKeyboardButton("▶ Assignments", callback_data="menu:assignments")],
        [InlineKeyboardButton("▶ Ask AI", callback_data="menu:assistant"), InlineKeyboardButton("▶ Ask Admin", callback_data="menu:ask")],
        [InlineKeyboardButton("▶ Profile & Documents", callback_data="menu:profile"), InlineKeyboardButton("▶ My Progress", callback_data="menu:progress")],
        [InlineKeyboardButton("▶ Rules", callback_data="menu:rules"), InlineKeyboardButton("▶ Payment & Status", callback_data="menu:status")],
        [InlineKeyboardButton("▶ Refer a Friend", callback_data="menu:refer"), InlineKeyboardButton("▶ Help & FAQs", callback_data="menu:help")],
        [InlineKeyboardButton("⬅ Main Menu", callback_data="menu:home")],
    ])
    await ctx.bot.send_message(
        uid,
        STUDENT_MANUAL + "\n\nHOW TO USE THIS MANUAL\nTap any ▶ button below to open that function immediately. You can return to the Student Manual whenever you need guidance.",
        reply_markup=kb,
    )


async def send_student_menu(ctx, uid, intro="Heribhee Academy Student Menu"):
    await ctx.bot.send_message(uid, intro + "\n\nChoose an option:", reply_markup=student_keyboard(uid))


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


async def show_profile(ctx, uid):
    s = get_student(uid)
    if not s:
        await ctx.bot.send_message(uid, "Student record not found. Send /start.")
        return
    name_edit = "Used" if s.get("name_edit_used") else "Available once"
    occupation_edit = "Used" if s.get("occupation_edit_used") else "Available once"
    cert_status = "Issued — available for re-download" if s.get("certificate_issued_at") and s.get("certificate_number") else "Not issued yet"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🪪 Get My ID Card", callback_data="profile:id"), InlineKeyboardButton("📄 Get Curriculum", callback_data="profile:curriculum")],
        [InlineKeyboardButton("✏️ Edit Name", callback_data="profile:editname"), InlineKeyboardButton("💼 Edit Occupation", callback_data="profile:editoccupation")],
        [InlineKeyboardButton("🎓 Get My Certificate", callback_data="profile:certificate")],
        [InlineKeyboardButton("⬅ Main Menu", callback_data="menu:home")],
    ])
    await ctx.bot.send_message(
        uid,
        "MY PROFILE & DOCUMENTS\n\n"
        f"Name: {s['name']}\n"
        f"Occupation / Role: {s.get('occupation') or 'Not set'}\n"
        f"Student ID: {visible_student_no(s)}\n\n"
        f"Name change: {name_edit}\n"
        f"Occupation change: {occupation_edit}\n"
        f"Certificate: {cert_status}\n\n"
        "Your ID card can be re-downloaded anytime. Name and occupation can each be changed only once by the student. Admins can still correct genuine mistakes manually.",
        reply_markup=kb,
    )


async def account_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    data = q.data

    if data == "recover:start":
        if get_student(uid):
            await q.message.reply_text("This Telegram account is already linked to a student record.")
            return
        ctx.user_data.clear()
        ctx.user_data["awaiting_recovery_student_id"] = True
        await q.message.reply_text(
            "Enter your existing Student ID, for example HB-0041.\n\n"
            "For your security, the next step will also ask for the phone number or email used during registration."
        )
        return

    s = get_student(uid)
    if not s:
        await q.message.reply_text("Please register or recover your account first using /start.")
        return

    if data == "profile:id":
        await send_student_id_card(ctx, uid)
        return
    if data == "profile:curriculum":
        await send_curriculum_to(ctx, uid)
        return
    if data == "profile:certificate":
        await resend_issued_certificate(ctx, uid)
        return
    if data == "profile:editname":
        if s.get("name_edit_used"):
            await q.message.reply_text("You have already used your one student name change. Please contact an admin if a genuine correction is still needed.")
            return
        ctx.user_data["awaiting_profile_name"] = True
        await q.message.reply_text("Type your corrected full name. This student self-service name change can only be used once.")
        return
    if data == "profile:editoccupation":
        if s.get("occupation_edit_used"):
            await q.message.reply_text("You have already used your one occupation/role change. Please contact an admin if a genuine correction is still needed.")
            return
        ctx.user_data["awaiting_profile_occupation"] = True
        await q.message.reply_text("Type your corrected occupation, profession, business, or current role. This student self-service change can only be used once.")
        return


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
        # Registration gives the student their ID, curriculum and free crash-course link.
        # Do not prompt for payment here; the Academy will announce when payment opens.
        await send_registration_pack(ctx, uid)
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
        ctx.user_data.pop("awaiting_academy_assistant", None)
        await send_student_menu(ctx, uid); return
    if data == "menu:manual":
        await send_student_manual(ctx, uid); return
    if data == "menu:assistant":
        ctx.user_data.pop("awaiting_support", None)
        ctx.user_data["awaiting_academy_assistant"] = True
        await q.message.reply_text(
            "🤖 HERIBHEE ACADEMY ASSISTANT\n\nAsk me about registration, account recovery, rules, assignments, class access, certificates, profile/documents, referrals, payment procedure, or how to use the bot.\n\nI use Academy information only. For personal or unusual issues, I will direct you to Ask Admin.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="menu:home")]])
        ); return
    if data == "menu:help":
        kb = [[InlineKeyboardButton(v[0], callback_data=f"faq:{k}")] for k,v in FAQS.items()]
        kb.append([InlineKeyboardButton("Main menu", callback_data="menu:home")])
        await q.message.reply_text("Help & FAQs — choose a category:", reply_markup=InlineKeyboardMarkup(kb)); return
    if data == "menu:rules":
        await send_rules_page(ctx, uid, 0); return
    if data == "menu:profile":
        await show_profile(ctx, uid); return
    if data == "menu:classes":
        if not rules_accepted(uid):
            await send_rules_page(ctx, uid, 0); return
        await deliver_class_access(ctx, uid); return
    if data == "menu:assignments":
        s = get_student(uid)
        kb = []
        if has_course_access(s):
            for week in sorted(get_passed_test_weeks(uid)):
                kb.append([InlineKeyboardButton(f"🚀 Week {week} Project — Unlocked", callback_data=f"project:week:{week}")])
        kb.append([InlineKeyboardButton("Submit assignment", callback_data="assignment:submitinfo")])
        kb.append([InlineKeyboardButton("Main menu", callback_data="menu:home")])
        await q.message.reply_text(
            "ASSIGNMENTS & WEEKLY PROJECTS\n\n"
            "Regular assignments can be submitted here. Each major weekly project unlocks after you pass the short knowledge test released at the end of that week's live session.\n\n"
            "Use Ask Admin if you need help with a submission.",
            reply_markup=InlineKeyboardMarkup(kb)
        ); return
    if data == "assignment:submitinfo":
        ctx.user_data["awaiting_assignment"] = True
        await q.message.reply_text("Send your assignment as a document, photo, video, or text in this private chat. Include the assignment name in your message/caption. Your submission will be recorded for admin review.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="menu:home")]])); return
    if data == "menu:progress":
        with db() as c:
            rows = c.execute("SELECT assignment_key, submitted_at, review_status FROM assignment_submissions WHERE user_id=? ORDER BY submitted_at", (uid,)).fetchall()
        assignment_text = "\n".join(
            f"• {r['assignment_key']} — {r['submitted_at'][:16].replace('T',' ')} — {str(r['review_status'] or 'pending').replace('_',' ').title()}"
            for r in rows
        ) if rows else "No assignments recorded yet."
        test_rows = weekly_test_results(uid)
        test_text = "\n".join(
            f"• Week {r['week_number']} — {r['score']}/{r['total_questions']} ({float(r['percentage'] or 0):.1f}%) — {'PASS ✅' if r['passed'] else 'Not passed'}"
            for r in test_rows
        ) if test_rows else "No weekly test results yet."
        text = f"YOUR PROGRESS\n\nAssignments\n{assignment_text}\n\nWeekly Knowledge Tests\n{test_text}"
        await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main menu", callback_data="menu:home")]])); return
    if data == "menu:ask":
        ctx.user_data.pop("awaiting_academy_assistant", None)
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
        if s.get("certificate_issued_at") and s.get("certificate_number"):
            await q.message.reply_text("Your certificate has already been issued. You can re-download it anytime from My Profile & Documents.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎓 Get My Certificate", callback_data="profile:certificate")],[InlineKeyboardButton("Main menu", callback_data="menu:home")]])); return
        await q.message.reply_text("Your certificate has not been issued yet. Certification requires the Academy project requirements, all four weekly knowledge tests, and final Academy verification/oral defense where applicable."); return
    if data == "menu:status":
        s=get_student(uid)
        if not s:
            await q.message.reply_text("Please register first with /start."); return
        paid = int(s["paid_amount"] or 0)
        if s.get("free_access"):
            await q.message.reply_text(
                f"PAYMENT & STATUS\n\nStudent ID: {visible_student_no(s)}\nAccess status: Complimentary paid-class access granted\n"
                f"Recorded payment: ₦{paid:,}\n\nYou do not need to make a payment for class access.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open My Classes", callback_data="menu:classes")],[InlineKeyboardButton("Main menu", callback_data="menu:home")]])
            )
            return
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
        msg = (f"PAYMENT & STATUS\n\nStudent ID: {visible_student_no(s)}\nPayment status: {status_label}\n"
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
    if s["status"] != "paid" and not s["bonus_sent"] and not s.get("free_access"):
        # Before payment, My Classes should simply take students back to the free
        # crash-course group. Payment instructions are shown only when they
        # deliberately open Payment & Status / the payment flow.
        if CRASH_COURSE_LINK:
            await ctx.bot.send_message(
                uid,
                "🚀 FREE CRASH COURSE\n\nYour current class access is the free crash-course group.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Crash Course", url=CRASH_COURSE_LINK)]])
            )
        else:
            await ctx.bot.send_message(uid, "Your crash-course group link is not configured yet. Please contact an Academy admin.")
        return
    if PAID_CLASS_LINK:
        await ctx.bot.send_message(
            uid,
            "✅ PAYMENT CONFIRMED — PAID CLASS UNLOCKED\n\nThis is the separate main class for fully paid students. Please do not share the invite link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Paid Class", url=PAID_CLASS_LINK)]])
        )
    else:
        await ctx.bot.send_message(uid, "Your payment/rules status is confirmed, but the paid-class link has not been configured yet. Please contact an Academy admin.")


async def student_private_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    uid = update.effective_user.id
    if uid in REVIEWER_IDS:
        remember_staff(uid, update.effective_user.full_name)

    # Recovery must work before this Telegram account is linked to a student.
    if ctx.user_data.get("awaiting_recovery_student_id"):
        student_no = (msg.text or "").strip().upper()
        s = get_student_by_no(student_no)
        if not s:
            await msg.reply_text("I couldn't find that Student ID. Check it and try again, for example HB-0041.")
            return
        ctx.user_data.pop("awaiting_recovery_student_id", None)
        ctx.user_data["recovery_old_uid"] = s["user_id"]
        ctx.user_data["recovery_student_no"] = s["student_no"]
        ctx.user_data["awaiting_recovery_contact"] = True
        await msg.reply_text("Now enter the email address OR phone number you used when you registered.")
        return

    if ctx.user_data.get("awaiting_recovery_contact"):
        old_uid = ctx.user_data.get("recovery_old_uid")
        with db() as c:
            s = c.execute("SELECT * FROM students WHERE user_id=?", (old_uid,)).fetchone()
        supplied = (msg.text or "").strip()
        email_match = supplied.lower() == (s.get("email") or "").strip().lower() if s else False
        phone_match = _clean_phone(supplied) == _clean_phone(s.get("phone")) if s and _clean_phone(supplied) else False
        if not s or not (email_match or phone_match):
            await msg.reply_text("Those details don't match the registration record. Please try the registered email or phone number, or contact an admin.")
            return
        if get_student(uid):
            await msg.reply_text("This Telegram account is already linked to another student record. Please contact an admin.")
            ctx.user_data.clear()
            return
        # Foreign keys are configured with ON UPDATE CASCADE by the profile migration.
        with db() as c:
            c.execute("UPDATE students SET user_id=?, username=? WHERE user_id=?", (uid, update.effective_user.username, old_uid))
            c.execute("UPDATE moderation_reports SET user_id=? WHERE user_id=?", (uid, old_uid))
        audit_log(uid, "account_recovered", "student", s["student_no"], f"old_telegram_id={old_uid}; new_telegram_id={uid}", student_user_id=uid)
        ctx.user_data.clear()
        await msg.reply_text(f"✅ Account recovered successfully. Student ID {visible_student_no(s)} is now linked to this Telegram account.")
        if rules_accepted(uid):
            await send_student_menu(ctx, uid, f"Welcome back, {s['name']}!")
        else:
            await send_rules_page(ctx, uid, 0)
        return

    if uid in ADMIN_IDS and ctx.user_data.get("awaiting_class_reminder_time"):
        value = (msg.text or "").strip()
        if not _valid_hhmm(value):
            await msg.reply_text("Please use 24-hour HH:MM format, for example 09:30 or 19:00.")
            return
        state = ctx.user_data.get("new_class_reminder") or {}
        state["class_time"] = value
        ctx.user_data["new_class_reminder"] = state
        ctx.user_data.pop("awaiting_class_reminder_time", None)
        ctx.user_data["awaiting_class_reminder_title"] = True
        await msg.reply_text(
            "Now send a short class name, for example: Monday AI Video Class\n\n"
            "The bot will remind admins 1 hour, 30 minutes, 10 minutes before, and again when class starts."
        )
        return

    if uid in ADMIN_IDS and ctx.user_data.get("awaiting_class_reminder_title"):
        title = (msg.text or "").strip()[:120]
        if not title:
            await msg.reply_text("Please send a short class name.")
            return
        state = ctx.user_data.get("new_class_reminder") or {}
        weekday = state.get("weekday")
        class_time = state.get("class_time")
        if weekday is None or not class_time:
            ctx.user_data.pop("awaiting_class_reminder_title", None)
            ctx.user_data.pop("new_class_reminder", None)
            await msg.reply_text("That reminder setup expired. Open /admin → Class Reminders and try again.")
            return
        with db() as c:
            c.execute(
                "INSERT INTO admin_class_reminders(weekday,class_time,title,enabled,created_at) VALUES(?,?,?,TRUE,NOW())",
                (weekday, class_time, title),
            )
        ctx.user_data.pop("awaiting_class_reminder_title", None)
        ctx.user_data.pop("new_class_reminder", None)
        await msg.reply_text(
            f"✅ Class reminder saved.\n\n{CLASS_REMINDER_WEEKDAYS[int(weekday)]} at {_format_class_time(class_time)}\n{title}\n\n"
            "Admins will be reminded 1 hour, 30 minutes, 10 minutes before class, and at class start."
        )
        await send_admin_dashboard(ctx, uid)
        return

    if uid in REVIEWER_IDS and ctx.user_data.get("awaiting_pack_message"):
        state = ctx.user_data.get("pack_editor") or {}
        kind = state.get("kind")
        weekday = state.get("weekday")
        mode = state.get("mode")
        index = state.get("index")
        new_text = (msg.text or msg.caption or "").strip()
        if not new_text:
            await msg.reply_text("Please send the message text, or send /admin to cancel.")
            return
        messages = get_group_pack(kind, weekday)
        if mode == "edit" and isinstance(index, int) and 0 <= index < len(messages):
            messages[index] = new_text[:4000]
            action = "updated"
        else:
            messages.append(new_text[:4000])
            action = "added"
        save_group_pack(kind, weekday, messages)
        ctx.user_data.pop("awaiting_pack_message", None)
        ctx.user_data.pop("pack_editor", None)
        await msg.reply_text(f"✅ Message {action} in the {WEEKDAY_NAMES.get(weekday, weekday)} {kind} pack.")
        await send_admin_dashboard(ctx, uid)
        return

    if uid in REVIEWER_IDS and ctx.user_data.get("awaiting_class_group_message"):
        custom_text = (msg.text or msg.caption or "").strip()
        if not custom_text:
            await msg.reply_text("Please send a text message, or send /admin to cancel.")
            return
        try:
            await send_class_group_message(ctx, custom_text[:4000])
            ctx.user_data.pop("awaiting_class_group_message", None)
            await msg.reply_text("✅ Custom message sent to the class group.", reply_markup=dashboard_keyboard_for(uid))
        except Exception as e:
            await msg.reply_text(f"Could not send to the class group: {e}")
        return

    if uid in ADMIN_IDS and ctx.user_data.get("awaiting_free_access_student_id"):
        student_no = (msg.text or "").strip().upper()
        student = get_student_by_no(student_no)
        if not student:
            await msg.reply_text(
                "I couldn't find that Student ID. Please check it and send it again, for example HB-0007.\n\n"
                "Send /admin if you want to leave this screen."
            )
            return
        with db() as c:
            c.execute("UPDATE students SET free_access=TRUE WHERE user_id=?", (student["user_id"],))
        audit_log(uid, "free_access_granted", "student", student["student_no"], student["name"], student_user_id=student["user_id"])
        ctx.user_data.pop("awaiting_free_access_student_id", None)
        await msg.reply_text(
            f"✅ Complimentary paid-class access granted to {student['name']} ({student['student_no']}).\n"
            f"Their recorded payment remains ₦{int(student.get('paid_amount') or 0):,}.",
            reply_markup=dashboard_keyboard_for(uid),
        )
        if PAID_CLASS_LINK:
            try:
                await ctx.bot.send_message(
                    student["user_id"],
                    "🎁 COMPLIMENTARY ACCESS GRANTED\n\nYou've been granted free access to the main paid class by Heribhee Studio.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Paid Class", url=PAID_CLASS_LINK)]])
                )
            except Exception as e:
                log.warning("Could not send complimentary access link to %s: %s", student["user_id"], e)
                await msg.reply_text("Access was recorded, but Telegram could not deliver the class link. The student can open My Classes to retrieve it.")
        else:
            await msg.reply_text("Access was recorded, but PAID_CLASS_LINK is not configured in Render yet.")
        return

    if uid in REVIEWER_IDS and ctx.user_data.get("awaiting_review_score"):
        sid = int(ctx.user_data.get("awaiting_review_score"))
        raw = (msg.text or "").strip()
        try:
            score = int(raw)
        except ValueError:
            await msg.reply_text("Please send a whole-number score from 0 to 100.")
            return
        if score < 0 or score > 100:
            await msg.reply_text("Score must be between 0 and 100.")
            return
        ctx.user_data.pop("awaiting_review_score", None)
        ctx.user_data["awaiting_review_feedback"] = {"sid": sid, "status": "approved", "score": score}
        await msg.reply_text("Score saved. Now send short feedback for the student. Type SKIP if no feedback is needed.")
        return

    if uid in REVIEWER_IDS and ctx.user_data.get("awaiting_review_feedback"):
        state = ctx.user_data.get("awaiting_review_feedback") or {}
        sid = int(state.get("sid"))
        status = state.get("status") or "correction"
        score = state.get("score")
        feedback = (msg.text or msg.caption or "").strip()[:2000]
        if feedback.upper() == "SKIP":
            feedback = ""
        if status == "correction" and not feedback:
            await msg.reply_text("Please send a short correction note so the student knows what to fix.")
            return
        with db() as c:
            r = c.execute("SELECT a.*,s.name,s.student_no,s.user_id FROM assignment_submissions a JOIN students s ON s.user_id=a.user_id WHERE a.id=?", (sid,)).fetchone()
            if not r:
                ctx.user_data.pop("awaiting_review_feedback", None)
                await msg.reply_text("That submission could not be found.")
                return
            c.execute(
                "UPDATE assignment_submissions SET review_status=?,score=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?",
                (status, score, uid, now().isoformat(), feedback, sid),
            )
        ctx.user_data.pop("awaiting_review_feedback", None)
        audit_log(uid, "assignment_reviewed", "assignment", sid, f"student={r['student_no']}; status={status}; score={score}; feedback={feedback[:500]}", student_user_id=r["user_id"])
        reviewer_name = update.effective_user.full_name or str(uid)
        if status == "approved":
            student_notice = f"✅ Your assignment '{r['assignment_key']}' has been reviewed and approved.\nScore: {score}/100"
            if feedback:
                student_notice += f"\nFeedback: {feedback}"
            admin_note = f"✅ Assignment #{sid} reviewed by {reviewer_name}: {score}/100 — APPROVED"
        else:
            student_notice = f"🔁 Your assignment '{r['assignment_key']}' needs correction.\nFeedback: {feedback}"
            admin_note = f"🔁 Assignment #{sid} reviewed by {reviewer_name}: CORRECTION REQUESTED"
        try:
            await ctx.bot.send_message(r["user_id"], student_notice)
        except Exception as e:
            log.warning("Could not send review result to student %s: %s", r["user_id"], e)
        if ADMIN_GROUP_ID:
            try:
                await ctx.bot.send_message(ADMIN_GROUP_ID, admin_note)
            except Exception as e:
                log.warning("Could not post review result to admin group: %s", e)
        await msg.reply_text("✅ Review recorded and the student has been notified.")
        await send_admin_dashboard(ctx, uid)
        return

    if uid in ADMIN_IDS and ctx.user_data.get("awaiting_student_history_search"):
        query = (msg.text or "").strip().upper()[:80]
        st = get_student_by_no(query)
        ctx.user_data.pop("awaiting_student_history_search", None)
        if not st:
            await msg.reply_text("No exact student was found. Please use the Student ID shown in the bot.", reply_markup=admin_dashboard_keyboard())
            return
        with db() as c:
            events = c.execute(
                """SELECT actor_user_id,actor_name,actor_role,action,target_type,target_id,details,created_at
                   FROM audit_log WHERE student_user_id=? ORDER BY created_at DESC LIMIT 30""",
                (int(st["user_id"]),),
            ).fetchall()
            reviews = c.execute(
                """SELECT assignment_key,review_status,score,reviewed_by,reviewed_at,review_note
                   FROM assignment_submissions WHERE user_id=? AND reviewed_at IS NOT NULL
                   ORDER BY reviewed_at DESC LIMIT 15""",
                (int(st["user_id"]),),
            ).fetchall()
        reg = str(st.get("registered_at") or "-")[:16].replace("T", " ")
        lines = [
            f"🕘 STUDENT HISTORY — {visible_student_no(st)}",
            f"Name: {st.get('name') or '-'}",
            f"Registered: {reg}",
            f"Cohort: {st.get('cohort') or '-'}",
            "",
        ]
        if reviews:
            lines.append("ASSIGNMENT REVIEWS")
            for r in reviews:
                who = staff_name(r.get("reviewed_by"))
                when = str(r.get("reviewed_at") or "-")[:16].replace("T", " ")
                score = f" | {r['score']}/100" if r.get("score") is not None else ""
                lines.append(f"• {when} — {r.get('assignment_key') or 'Assignment'} — {str(r.get('review_status') or '').replace('_',' ').title()}{score} — by {who}")
            lines.append("")
        lines.append("ACTIVITY HISTORY")
        if not events:
            lines.append("No linked activity events recorded yet. New admin/reviewer actions will appear here automatically.")
        else:
            for r in events:
                who = r.get("actor_name") or staff_name(r.get("actor_user_id"))
                when = str(r.get("created_at") or "-")[:16].replace("T", " ")
                detail = (r.get("details") or "").replace("\n", " ")[:180]
                lines.append(f"• {when} — {r.get('action') or '-'} — by {who}{(' — '+detail) if detail else ''}")
        await msg.reply_text("\n".join(lines), reply_markup=admin_dashboard_keyboard())
        return

    if uid in ADMIN_IDS and ctx.user_data.get("awaiting_student_wipe_search"):
        query = (msg.text or "").strip()[:120]
        if not query:
            await msg.reply_text("Send the Student ID, for example HB-0001.")
            return
        st = get_student_by_no(query)
        if not st:
            try:
                st = get_student(int(query))
            except (ValueError, TypeError):
                st = None
        ctx.user_data.pop("awaiting_student_wipe_search", None)
        if not st:
            await msg.reply_text(
                "No exact student was found. For safety, Student Clearance requires an exact Student ID or Telegram numeric ID.",
                reply_markup=admin_dashboard_keyboard(),
            )
            return
        await msg.reply_text(
            f"🧹 STUDENT FOUND\n\nName: {st.get('name') or '-'}\nStudent ID: {visible_student_no(st)}\nStatus: {st.get('status') or '-'}\nPhone: {st.get('phone') or '-'}\nEmail: {st.get('email') or '-'}\nTelegram: {st.get('user_id')}\n\nDo you want to begin permanent clearance for this student?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Continue to wipe", callback_data=f"admin:wipe:confirm:{st['user_id']}")],
                [InlineKeyboardButton("Cancel", callback_data="admin:home")],
            ])
        )
        return

    if uid in REVIEWER_IDS and ctx.user_data.get("awaiting_student_search"):
        query = (msg.text or "").strip()[:120]
        if not query:
            await msg.reply_text("Enter a Student ID, name, phone number, or email address.")
            return
        like = f"%{query}%"
        with db() as c:
            rows = c.execute(
                """SELECT name,student_no,display_student_no,phone,email,occupation,category,status,cohort,archived,user_id,registered_at
                   FROM students
                   WHERE student_no ILIKE ? OR display_student_no ILIKE ? OR name ILIKE ? OR phone ILIKE ? OR email ILIKE ?
                   ORDER BY archived, COALESCE(CAST(NULLIF(REGEXP_REPLACE(COALESCE(display_student_no,student_no),'[^0-9]','','g'),'') AS INTEGER),999999), registered_at LIMIT 10""",
                (like, like, like, like, like),
            ).fetchall()
        ctx.user_data.pop("awaiting_student_search", None)
        if not rows:
            await msg.reply_text("No matching student was found.", reply_markup=dashboard_keyboard_for(uid))
            return
        lines = ["🔎 STUDENT SEARCH RESULTS", ""]
        for r in rows:
            archive_tag = " [ARCHIVED]" if r.get("archived") else ""
            if uid in ADMIN_IDS:
                lines.append(f"{visible_student_no(r)} — {r['name']}{archive_tag}\nRegistered: {str(r.get('registered_at') or '-')[:16].replace('T',' ')}\nStatus: {r.get('status') or '-'} | Cohort: {r.get('cohort') or '-'}\nPhone: {r.get('phone') or '-'} | Email: {r.get('email') or '-'}\nTelegram: {r.get('user_id')}")
            else:
                lines.append(f"{visible_student_no(r)} — {r['name']}{archive_tag}\nRegistered: {str(r.get('registered_at') or '-')[:16].replace('T',' ')}\nRole: {r.get('occupation') or r.get('category') or '-'}\nPhone: {r.get('phone') or '-'} | Email: {r.get('email') or '-'}")
            lines.append("")
        await msg.reply_text("\n".join(lines), reply_markup=dashboard_keyboard_for(uid))
        return

    if uid in ADMIN_IDS and ctx.user_data.get("awaiting_new_cohort_name"):
        new_name = (msg.text or "").strip()[:80]
        if len(new_name) < 2:
            await msg.reply_text("Please enter a short cohort name, for example October 2026 Cohort.")
            return
        old_name = active_cohort()
        with db() as c:
            c.execute("UPDATE students SET archived=TRUE, archived_at=NOW() WHERE COALESCE(archived,FALSE)=FALSE AND cohort=?", (old_name,))
        set_app_setting("active_cohort", new_name)
        audit_log(uid, "cohort_archived_and_new_started", "cohort", old_name, f"new_active_cohort={new_name}")
        ctx.user_data.pop("awaiting_new_cohort_name", None)
        await msg.reply_text(f"✅ '{old_name}' has been archived and '{new_name}' is now the active cohort. New registrations will be placed there automatically.", reply_markup=dashboard_keyboard_for(uid))
        return

    if uid in ADMIN_IDS:
        return
    if uid in REVIEWER_IDS:
        return
    s = get_student(uid)
    if not s:
        return

    if ctx.user_data.get("awaiting_academy_assistant"):
        question = (msg.text or msg.caption or "").strip()
        if not question:
            await msg.reply_text("Please type your question as text, or use the menu to cancel.")
            return
        answer = academy_assistant_answer(question, s)
        await msg.reply_text(
            answer,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Ask Another Question", callback_data="menu:assistant")],
                [InlineKeyboardButton("💬 Ask Admin", callback_data="menu:ask"), InlineKeyboardButton("Main Menu", callback_data="menu:home")],
            ]),
        )
        ctx.user_data.pop("awaiting_academy_assistant", None)
        return

    if ctx.user_data.get("awaiting_profile_name"):
        new_name = (msg.text or "").strip()[:80]
        if len(new_name) < 2:
            await msg.reply_text("Please enter a valid full name.")
            return
        if s.get("name_edit_used"):
            ctx.user_data.pop("awaiting_profile_name", None)
            await msg.reply_text("Your one self-service name change has already been used.")
            return
        with db() as c:
            c.execute("UPDATE students SET name=?, name_edit_used=TRUE WHERE user_id=?", (new_name, uid))
        audit_log(uid, "student_name_changed", "student", s["student_no"], f"new_name={new_name}", student_user_id=uid)
        ctx.user_data.pop("awaiting_profile_name", None)
        await msg.reply_text("✅ Your name has been updated. Your ID card will now use the new name.")
        await show_profile(ctx, uid)
        return

    if ctx.user_data.get("awaiting_profile_occupation"):
        new_role = (msg.text or "").strip()[:120]
        if len(new_role) < 2:
            await msg.reply_text("Please enter a valid occupation or current role.")
            return
        if s.get("occupation_edit_used"):
            ctx.user_data.pop("awaiting_profile_occupation", None)
            await msg.reply_text("Your one self-service occupation change has already been used.")
            return
        with db() as c:
            c.execute("UPDATE students SET occupation=?, occupation_edit_used=TRUE WHERE user_id=?", (new_role, uid))
        audit_log(uid, "student_occupation_changed", "student", s["student_no"], f"new_role={new_role}", student_user_id=uid)
        ctx.user_data.pop("awaiting_profile_occupation", None)
        await msg.reply_text("✅ Your occupation/role has been updated. Your ID card will now use the new role.")
        await show_profile(ctx, uid)
        return
    if ctx.user_data.get("awaiting_support"):
        text = (msg.text or msg.caption or "[attachment]")[:3500]
        with db() as c:
            cur = c.execute("INSERT INTO support_tickets(user_id,message,created_at) VALUES(?,?,?) RETURNING id", (uid,text,now().isoformat()))
            tid = cur.fetchone()["id"]
        s = get_student(uid)
        for admin in REVIEWER_IDS:
            await ctx.bot.send_message(admin, f"Support ticket #{tid}\nStudent: {s['name']} ({s['student_no']})\nTelegram: {uid}\n\n{text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Mark handled", callback_data=f"supportdone:{tid}")]]))
        ctx.user_data.pop("awaiting_support",None)
        await msg.reply_text("Your question has been sent to the Academy admins. We'll get back to you.")
        return
    if ctx.user_data.get("awaiting_assignment"):
        s = get_student(uid)
        caption = (msg.caption or msg.text or "").strip()
        key = caption[:100] if caption else "Unlabelled assignment"
        file_id = (
            msg.document.file_id if msg.document else
            (msg.photo[-1].file_id if msg.photo else
             (msg.video.file_id if msg.video else None))
        )
        with db() as c:
            c.execute("""INSERT INTO assignment_submissions(user_id,assignment_key,file_id,text,submitted_at) VALUES(?,?,?,?,?)
                       ON CONFLICT (user_id, assignment_key) DO UPDATE SET
                         file_id=EXCLUDED.file_id, text=EXCLUDED.text, submitted_at=EXCLUDED.submitted_at,
                         review_status='pending', score=NULL, reviewed_by=NULL, reviewed_at=NULL, review_note=NULL""",
                      (uid,key,file_id,caption,now().isoformat()))
        ctx.user_data.pop("awaiting_assignment",None)
        await msg.reply_text(f"Your submission for '{key}' has been recorded for review.")
        recipients = [ADMIN_GROUP_ID] if ADMIN_GROUP_ID else list(REVIEWER_IDS)
        header = (f"Assignment submission\nStudent: {s['name']} ({s['student_no']})\n"
                  f"Task: {key}\nSubmitted: {now().isoformat()}\nTelegram ID: {uid}")
        with db() as c:
            submission = c.execute(
                "SELECT id FROM assignment_submissions WHERE user_id=? AND assignment_key=?",
                (uid, key),
            ).fetchone()
        sid = submission["id"] if submission else None
        review_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📝 Open Review & Score", callback_data=f"reviewopen:{sid}"),
        ]]) if sid else None
        for recipient in recipients:
            await ctx.bot.send_message(recipient, header, reply_markup=review_kb)
            if file_id:
                if msg.document:
                    await ctx.bot.send_document(recipient, file_id, caption=f"{s['student_no']} — {key}")
                elif msg.photo:
                    await ctx.bot.send_photo(recipient, file_id, caption=f"{s['student_no']} — {key}")
                elif msg.video:
                    await ctx.bot.send_video(recipient, file_id, caption=f"{s['student_no']} — {key}")
            elif caption:
                await ctx.bot.send_message(recipient, caption)
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
        cur = c.execute("INSERT INTO moderation_reports(chat_id,message_id,user_id,username,display_name,message_text,detected_terms,created_at) VALUES(?,?,?,?,?,?,?,?) RETURNING id", (msg.chat_id,msg.message_id,user.id,user.username,display,text[:3000],", ".join(hits),now().isoformat()))
        rid = cur.fetchone()["id"]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Confirm removal", callback_data=f"mod:remove:{rid}"),InlineKeyboardButton("Dismiss", callback_data=f"mod:dismiss:{rid}")]])
    for admin in ADMIN_IDS:
        try:
            await ctx.bot.send_message(admin, f"⚠️ MODERATION REVIEW #{rid}\nStudent: {display} (@{user.username or 'no username'})\nUser ID: {user.id}\nGroup: {msg.chat.title or msg.chat_id}\nDetected: {', '.join(hits)}\n\nFlagged message:\n{text[:2500]}\n\nMessage was deleted pending review. Confirm removal or dismiss.", reply_markup=kb)
        except Exception as e:
            log.warning("Could not send moderation alert to admin %s: %s", admin,e)


async def moderation_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q.from_user.id not in ADMIN_IDS:
        await q.answer("Full admins only",show_alert=True); return
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
    if q.from_user.id not in REVIEWER_IDS:
        await q.answer("Authorized admins/reviewers only",show_alert=True); return
    tid=int(q.data.split(":")[1])
    with db() as c:
        c.execute("UPDATE support_tickets SET status='handled',handled_by=? WHERE id=?",(q.from_user.id,tid))
    await q.answer("Marked handled")
    await q.edit_message_text((q.message.text or "")+f"\n\nHandled by {q.from_user.full_name}")


# ---------- PDF student-record export ----------
def build_student_records_pdf(rows, include_sensitive=True):
    buf = io.BytesIO()
    buf.name = f"Heribhee_Student_Records_{now().strftime('%Y-%m-%d')}.pdf"
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm,
        title="Heribhee Studio Student Records",
        author="Heribhee Studio",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HeribheeTitle", parent=styles["Title"], alignment=TA_CENTER,
        fontSize=17, leading=20, textColor=colors.HexColor("#12213D"), spaceAfter=4*mm,
    )
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=7.3, leading=8.5)
    meta = ParagraphStyle("Meta", parent=styles["BodyText"], fontSize=8.5, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))

    story = []
    if os.path.exists("logo_shield.png"):
        try:
            story.append(RLImage("logo_shield.png", width=15*mm, height=15*mm))
        except Exception:
            pass
    story.append(Paragraph("HERIBHEE STUDIO - STUDENT RECORDS", title_style))
    if include_sensitive:
        free_count = sum(1 for r in rows if r.get("free_access"))
        paid_count = sum(1 for r in rows if r.get("status") == "paid")
        revenue = sum(int(r.get("paid_amount") or 0) for r in rows)
        meta_text = (
            f"Generated {now().strftime('%d %b %Y, %I:%M %p')} (Nigeria time) &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Students: {len(rows)} &nbsp;&nbsp;|&nbsp;&nbsp; Fully paid: {paid_count} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Free access: {free_count} &nbsp;&nbsp;|&nbsp;&nbsp; Confirmed revenue: ₦{revenue:,}"
        )
    else:
        meta_text = (
            f"Generated {now().strftime('%d %b %Y, %I:%M %p')} (Nigeria time) &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Students: {len(rows)} &nbsp;&nbsp;|&nbsp;&nbsp; Reviewer copy"
        )
    story.append(Paragraph(meta_text, meta))
    story.append(Spacer(1, 5*mm))

    if include_sensitive:
        headers = ["Student ID", "Name", "Phone", "Email", "Occupation / Role", "Access", "Paid", "Registered", "Certificate"]
    else:
        headers = ["Student ID", "Name", "Phone", "Email", "Occupation / Role", "Registered"]
    data = [[Paragraph(f"<b>{h}</b>", small) for h in headers]]
    for r in rows:
        reg = (r.get("registered_at") or "")[:10]
        if include_sensitive:
            if r.get("free_access"):
                access = "Complimentary"
            elif r.get("status") == "paid":
                access = "Paid"
            elif r.get("status") == "part_paid":
                access = "Part paid"
            else:
                access = "Registered"
            cert = r.get("certificate_number") or ("Eligible" if r.get("certificate_eligible") else "-")
            vals = [
                visible_student_no(r), r.get("name") or "-", r.get("phone") or "-",
                r.get("email") or "-", r.get("occupation") or r.get("category") or "-",
                access, f"₦{int(r.get('paid_amount') or 0):,}", reg or "-", cert,
            ]
        else:
            vals = [
                visible_student_no(r), r.get("name") or "-", r.get("phone") or "-",
                r.get("email") or "-", r.get("occupation") or r.get("category") or "-", reg or "-",
            ]
        data.append([Paragraph(escape(str(v)), small) for v in vals])

    widths = ([20*mm, 34*mm, 28*mm, 45*mm, 39*mm, 25*mm, 20*mm, 22*mm, 27*mm]
              if include_sensitive else [24*mm, 42*mm, 34*mm, 58*mm, 55*mm, 28*mm])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="CENTER")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#12213D")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#C8CDD6")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F5F2E9")]),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return buf


# ---------- class group messaging ----------
async def send_class_group_message(ctx, text):
    if not CLASS_GROUP_ID:
        raise RuntimeError("CLASS_GROUP_ID is not configured")
    await ctx.bot.send_message(CLASS_GROUP_ID, text)


def _time_to_minutes(value):
    try:
        h, m = [int(x) for x in str(value).split(":", 1)]
        return h * 60 + m
    except Exception:
        return None


async def _send_group_schedule_once(ctx, kind, scheduled_time, require_due_window=False):
    if not group_messages_enabled() or not CLASS_GROUP_ID:
        return False
    current = now()
    if current.weekday() not in {0, 1, 3, 4}:
        return False
    if require_due_window:
        target = _time_to_minutes(scheduled_time)
        current_minute = current.hour * 60 + current.minute
        if target is None or not (target <= current_minute <= target + 12):
            return False
    key = f"group_{kind}_sent_{current.date().isoformat()}"
    if get_app_setting(key, "") == "sent":
        return False
    text = _message_for(kind, current)
    if not text:
        return False
    try:
        await send_class_group_message(ctx, text)
        set_app_setting(key, "sent")
        return True
    except Exception as e:
        log.warning("Could not send scheduled %s group message: %s", kind, e)
        return False


async def scheduled_group_morning(ctx: ContextTypes.DEFAULT_TYPE):
    await _send_group_schedule_once(ctx, "morning", GROUP_MORNING_TIME, require_due_window=False)


async def scheduled_group_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    await _send_group_schedule_once(ctx, "reminder", GROUP_REMINDER_TIME, require_due_window=False)


FULL_ADMIN_MANUAL = """📖 HERIBHEE FULL ADMIN MANUAL

👨‍🎓 Students — Browse active-cohort students and their records.
🔎 Student Search — Find any current or archived student by ID, name, phone, or email.
💳 Payments — Review payment submissions and approve/reject them. Payment control is for full admins only.
📝 Assignments — See assignment totals/status overview.
✅ Pending Reviews — Open unmarked submissions. Full admins and authorized reviewers can review and score.
🎓 Certificates — View certification progress. Certificate issuing remains under full-admin control.
👥 Referrals — Review referral activity.
💬 Support Questions — Read student support tickets and mark handled items.
📢 Message Students — Send a private broadcast to the selected student audience.
📣 Group Messages — Send class-group messages, edit the message pack, test group connections, and turn automatic class messages on/off.
📄 Export PDF — Creates the full student-record PDF. Full-admin copies include payment/access/certificate information.
📈 Reviewer Performance — Shows marking totals, approvals, corrections, average scores and last activity.
🧾 Audit Log — Shows recent sensitive/admin actions and who performed them.
🗃 Cohorts / Archive — Archive a completed intake and start a new active cohort without deleting old records.
📊 Statistics — Academy totals, confirmed revenue, paid/free-access counts and assignment figures.
🎁 Free Access — Enter a Student ID to grant complimentary paid-class access without recording false revenue.
⏰ Class Reminders — Create admin-only class reminders. The bot sends alerts 1 hour, 30 minutes, 10 minutes and at class time.
🧠 Weekly Tests — After each live session, release that week’s 15-minute knowledge test. The bot randomizes questions/options, marks instantly, and unlocks the weekly project after a pass.
🆔 Show my Telegram ID — Shows your personal Telegram user ID.
📖 Admin Manual — Opens this guide.

Assignment review: open Pending Reviews or use the button attached to a submission in the review group. Choose Score & Approve, enter 0–100, then feedback. Request Correction sends correction feedback instead.

Security: never share your bot token, database URL, webhook secret or reminder trigger secret."""

REVIEWER_MANUAL = """📖 HERIBHEE REVIEWER MANUAL

👨‍🎓 Student Records — Browse active-cohort student records available to reviewers.
🔎 Student Search — Find a current or archived student by ID, name, phone, or email.
✅ Pending Reviews — Opens assignments waiting to be marked. Tap Open Review, then Score & Approve or Request Correction.
💬 Support Questions — Read student questions and mark handled items when resolved.
📣 Group Messages — Send approved class-group messages, use the message pack, and test group connections.
📄 Export PDF — Creates the reviewer copy of student records. Financial, free-access and certificate-control information is intentionally hidden.
📈 My Performance — Shows your own marking totals, approvals, correction requests and average score given.
🆔 My Telegram ID — Shows your Telegram user ID.
📖 Reviewer Manual — Opens this guide.

HOW TO MARK AN ASSIGNMENT
1. Open Pending Reviews, or tap Open Review & Score in the assignment-review group.
2. Read/view the student's submission.
3. Tap Score & Approve for completed work, enter a whole-number score from 0–100, then send short feedback.
4. Tap Request Correction if work must be fixed, then type exactly what the student should correct.
5. The bot records who reviewed it and sends the result privately to the student.

Reviewer accounts cannot control payments, Free Access, certificates, referrals, revenue/statistics, private student broadcasts or class-reminder settings. Those functions are reserved for full admins."""


async def send_admin_manual(ctx, uid):
    if uid in ADMIN_IDS:
        text = FULL_ADMIN_MANUAL + "\n\nHOW TO USE THIS MANUAL\nTap any ▶ button below to open the feature immediately. This lets you learn the dashboard by using it, not only by reading about it."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Students", callback_data="admin:students:0"), InlineKeyboardButton("▶ Search", callback_data="admin:search")],
            [InlineKeyboardButton("▶ Payments", callback_data="admin:payments:0"), InlineKeyboardButton("▶ Reviewer Performance", callback_data="admin:reviewerperf")],
            [InlineKeyboardButton("▶ Pending Reviews", callback_data="admin:pending:0"), InlineKeyboardButton("▶ Certificates", callback_data="admin:certs")],
            [InlineKeyboardButton("▶ Support", callback_data="admin:support:0"), InlineKeyboardButton("▶ Group Messages", callback_data="admin:groupmsg")],
            [InlineKeyboardButton("▶ Export PDF", callback_data="admin:export"), InlineKeyboardButton("▶ Free Access", callback_data="admin:freeaccess")],
            [InlineKeyboardButton("▶ Class Reminders", callback_data="admin:classreminders"), InlineKeyboardButton("▶ Statistics", callback_data="admin:stats")],
            [InlineKeyboardButton("▶ Audit Log", callback_data="admin:audit"), InlineKeyboardButton("▶ Cohorts / Archive", callback_data="admin:cohorts")],
            [InlineKeyboardButton("⬅ Dashboard", callback_data="admin:home")],
        ])
    else:
        text = REVIEWER_MANUAL + "\n\nHOW TO USE THIS MANUAL\nTap any ▶ button below to open an allowed reviewer function immediately. Restricted owner-only functions are not shown."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Student Records", callback_data="admin:students:0"), InlineKeyboardButton("▶ Search", callback_data="admin:search")],
            [InlineKeyboardButton("▶ Pending Reviews", callback_data="admin:pending:0"), InlineKeyboardButton("▶ My Performance", callback_data="admin:myperformance")],
            [InlineKeyboardButton("▶ Support Questions", callback_data="admin:support:0"), InlineKeyboardButton("▶ Group Messages", callback_data="admin:groupmsg")],
            [InlineKeyboardButton("▶ Export PDF", callback_data="admin:export"), InlineKeyboardButton("▶ My Telegram ID", callback_data="admin:myid")],
            [InlineKeyboardButton("⬅ Dashboard", callback_data="admin:home")],
        ])
    await ctx.bot.send_message(uid, text, reply_markup=kb)


# ---------- admin dashboard and assignment review ----------
def admin_dashboard_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍🎓 Students", callback_data="admin:students:0"), InlineKeyboardButton("🔎 Student Search", callback_data="admin:search")],
        [InlineKeyboardButton("🕘 Student History", callback_data="admin:history"), InlineKeyboardButton("🧾 Audit Log", callback_data="admin:audit")],
        [InlineKeyboardButton("💳 Payments", callback_data="admin:payments:0"), InlineKeyboardButton("📝 Assignments", callback_data="admin:assignments")],
        [InlineKeyboardButton("✅ Pending reviews", callback_data="admin:pending:0"), InlineKeyboardButton("📈 Reviewer Performance", callback_data="admin:reviewerperf")],
        [InlineKeyboardButton("🎓 Certificates", callback_data="admin:certs"), InlineKeyboardButton("🗃 Cohorts / Archive", callback_data="admin:cohorts")],
        [InlineKeyboardButton("👥 Referrals", callback_data="admin:referrals")],
        [InlineKeyboardButton("💬 Support questions", callback_data="admin:support:0"), InlineKeyboardButton("📢 Message students", callback_data="admin:message")],
        [InlineKeyboardButton("📣 Group Messages", callback_data="admin:groupmsg"), InlineKeyboardButton("📄 Export PDF", callback_data="admin:export")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin:stats"), InlineKeyboardButton("🎁 Free Access", callback_data="admin:freeaccess")],
        [InlineKeyboardButton("⏰ Class Reminders", callback_data="admin:classreminders"), InlineKeyboardButton("🧠 Weekly Tests", callback_data="admin:tests")],
        [InlineKeyboardButton("🧹 Student Clearance", callback_data="admin:clearance"), InlineKeyboardButton("🆔 Show my Telegram ID", callback_data="admin:myid")],
        [InlineKeyboardButton("📖 Admin Manual", callback_data="admin:manual")],
    ])


def reviewer_dashboard_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍🎓 Student Records", callback_data="admin:students:0"), InlineKeyboardButton("🔎 Student Search", callback_data="admin:search")],
        [InlineKeyboardButton("✅ Pending Reviews", callback_data="admin:pending:0"), InlineKeyboardButton("📈 My Performance", callback_data="admin:myperformance")],
        [InlineKeyboardButton("💬 Support Questions", callback_data="admin:support:0"), InlineKeyboardButton("📣 Group Messages", callback_data="admin:groupmsg")],
        [InlineKeyboardButton("📄 Export PDF", callback_data="admin:export"), InlineKeyboardButton("🆔 My Telegram ID", callback_data="admin:myid")],
        [InlineKeyboardButton("📖 Reviewer Manual", callback_data="admin:manual")],
    ])


def dashboard_keyboard_for(uid):
    return admin_dashboard_keyboard() if uid in ADMIN_IDS else reviewer_dashboard_keyboard()


async def send_admin_dashboard(ctx, uid):
    if uid in ADMIN_IDS:
        title = "HERIBHEE ACADEMY — ADMIN DASHBOARD"
    else:
        title = "HERIBHEE ACADEMY — REVIEWER DASHBOARD"
    await ctx.bot.send_message(uid, title + "\n\nChoose a function:", reply_markup=dashboard_keyboard_for(uid))


async def admin_dashboard_callback(update, ctx):
    q=update.callback_query
    uid=q.from_user.id
    data=q.data
    if uid in REVIEWER_IDS:
        remember_staff(uid, q.from_user.full_name)
    if uid not in REVIEWER_IDS:
        await q.answer("This admin function is not available to your account.", show_alert=True); return
    if uid not in ADMIN_IDS:
        reviewer_allowed = (
            data in {"admin:home", "admin:myid", "admin:manual", "admin:export", "admin:search", "admin:myperformance", "admin:groupmsg", "admin:groupmsg:edit",
                     "admin:groupmsg:morning", "admin:groupmsg:reminder", "admin:groupmsg:custom",
                     "admin:groupmsg:testclass", "admin:groupmsg:testreview", "admin:groupmsg:toggle"}
            or data.startswith("admin:students:")
            or data.startswith("admin:pending:")
            or data.startswith("admin:support:")
            or data.startswith("admin:pack:")
            or data.startswith("admin:groupmsg:")
        )
        if not reviewer_allowed:
            await q.answer("This function is reserved for full admins.", show_alert=True); return
    await q.answer()
    if data == "admin:home":
        await send_admin_dashboard(ctx,uid); return
    if data == "admin:myid":
        await q.message.reply_text(f"Your Telegram user ID: {uid}"); return
    if data == "admin:manual":
        await send_admin_manual(ctx, uid); return
    if data == "admin:search":
        ctx.user_data["awaiting_student_search"] = True
        await q.message.reply_text("🔎 STUDENT SEARCH\n\nSend a Student ID, student name, phone number, or email address.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:home")]]))
        return
    if data == "admin:history":
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        ctx.user_data["awaiting_student_history_search"] = True
        await q.message.reply_text(
            "🕘 STUDENT HISTORY\n\nSend the exact Student ID, for example HB-003.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:home")]])
        )
        return
    if data in {"admin:myperformance", "admin:reviewerperf"}:
        if data == "admin:reviewerperf" and uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        if data == "admin:myperformance":
            ids = [uid]
        else:
            ids = sorted(REVIEWER_IDS)
        lines = ["📈 REVIEWER PERFORMANCE", ""]
        with db() as c:
            for rid in ids:
                row = c.execute(
                    """SELECT COUNT(*) total,
                              COUNT(*) FILTER (WHERE review_status='approved') approved,
                              COUNT(*) FILTER (WHERE review_status='correction') corrections,
                              ROUND(AVG(score) FILTER (WHERE score IS NOT NULL),1) avg_score,
                              MAX(reviewed_at) last_review
                       FROM assignment_submissions WHERE reviewed_by=?""",
                    (rid,),
                ).fetchone()
                lines.append(f"Reviewer: {staff_name(rid)} ({rid})")
                lines.append(f"Reviewed: {row['total'] or 0} | Approved: {row['approved'] or 0} | Corrections: {row['corrections'] or 0}")
                lines.append(f"Average score given: {row['avg_score'] if row['avg_score'] is not None else '-'} | Last review: {str(row['last_review'])[:16] if row['last_review'] else '-'}")
                lines.append("")
        await q.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard", callback_data="admin:home")]]))
        return
    if data == "admin:audit":
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        with db() as c:
            rows = c.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 12").fetchall()
        lines = ["🧾 RECENT AUDIT LOG", ""]
        if not rows:
            lines.append("No audit entries yet.")
        for r in rows:
            who = r.get("actor_name") or staff_name(r.get("actor_user_id"))
            lines.append(f"{str(r['created_at'])[:16]} • {r['actor_role']} — {who} ({r['actor_user_id']})\n{r['action']} → {r.get('target_type') or '-'} {r.get('target_id') or ''}\n{(r.get('details') or '')[:140]}")
            lines.append("")
        await q.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard", callback_data="admin:home")]]))
        return
    if data == "admin:cohorts":
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        current = active_cohort()
        with db() as c:
            active_count = c.execute("SELECT COUNT(*) n FROM students WHERE COALESCE(archived,FALSE)=FALSE AND cohort=?", (current,)).fetchone()["n"]
            archived = c.execute("SELECT cohort,COUNT(*) n,MAX(archived_at) archived_at FROM students WHERE COALESCE(archived,FALSE)=TRUE GROUP BY cohort ORDER BY MAX(archived_at) DESC NULLS LAST").fetchall()
        lines = ["🗃 COHORTS / ARCHIVE", "", f"Active cohort: {current}", f"Active students: {active_count}", "Visible Student IDs restart from HB-001 for each new cohort.", "Deleted non-certified IDs are automatically reused from the lowest available gap.", ""]
        if archived:
            lines.append("Archived cohorts:")
            lines += [f"• {r.get('cohort') or 'Unlabelled'} — {r['n']} students" for r in archived[:15]]
        else:
            lines.append("No archived cohorts yet.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Archive Current & Start New", callback_data="admin:cohorts:new")],
            [InlineKeyboardButton("📄 Export Archived Records", callback_data="admin:cohorts:export")],
            [InlineKeyboardButton("Admin dashboard", callback_data="admin:home")],
        ])
        await q.message.reply_text("\n".join(lines), reply_markup=kb)
        return
    if data == "admin:cohorts:export":
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        with db() as c:
            rows = c.execute("SELECT * FROM students WHERE COALESCE(archived,FALSE)=TRUE ORDER BY cohort,student_no").fetchall()
        if not rows:
            await q.message.reply_text("There are no archived student records yet.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard", callback_data="admin:home")]]))
            return
        out = build_student_records_pdf(rows, include_sensitive=True)
        out.name = f"Heribhee_Archived_Student_Records_{now().strftime('%Y-%m-%d')}.pdf"
        await q.message.reply_document(out, caption="📦 Archived Heribhee student records")
        return
    if data == "admin:cohorts:new":
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        ctx.user_data["awaiting_new_cohort_name"] = True
        await q.message.reply_text(f"Current cohort: {active_cohort()}\n\nSend the NEW cohort name. Example: October 2026 Cohort.\n\nWhen you send it, the current cohort will be archived and all future registrations will go into the new cohort.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:home")]]))
        return
    if data == "admin:freeaccess":
        ctx.user_data["awaiting_free_access_student_id"] = True
        await q.message.reply_text(
            "🎁 GRANT FREE ACCESS\n\nSend the student's Heribhee Student ID, for example: HB-0007\n\n"
            "The student will be given complimentary access to the paid class without changing their payment amount or revenue records.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:home")]])
        )
        return
    if data == "admin:classreminders":
        rows = get_admin_class_reminders()
        lines = ["⏰ ADMIN CLASS REMINDERS", ""]
        if rows:
            for r in rows:
                status = "ON" if r.get("enabled", True) else "OFF"
                day = CLASS_REMINDER_WEEKDAYS.get(int(r.get("weekday")), str(r.get("weekday")))
                lines.append(f"#{r['id']} • {day} • {_format_class_time(r['class_time'])} • {r.get('title') or 'Class'} • {status}")
        else:
            lines.append("No class reminders have been created yet.")
        kb = [[InlineKeyboardButton("➕ Add Class Reminder", callback_data="admin:classreminders:add")]]
        for r in rows[:12]:
            kb.append([
                InlineKeyboardButton(f"{'⛔' if r.get('enabled', True) else '✅'} #{r['id']}", callback_data=f"admin:classreminders:toggle:{r['id']}"),
                InlineKeyboardButton(f"🗑 Delete #{r['id']}", callback_data=f"admin:classreminders:delete:{r['id']}")
            ])
        kb.append([InlineKeyboardButton("Admin dashboard", callback_data="admin:home")])
        await q.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return
    if data == "admin:classreminders:add":
        kb = []
        days = list(CLASS_REMINDER_WEEKDAYS.items())
        for i in range(0, len(days), 2):
            row = []
            for day_no, day_name in days[i:i+2]:
                row.append(InlineKeyboardButton(day_name, callback_data=f"admin:classreminders:day:{day_no}"))
            kb.append(row)
        kb.append([InlineKeyboardButton("Cancel", callback_data="admin:classreminders")])
        await q.message.reply_text("Choose the class day:", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("admin:classreminders:day:"):
        weekday = int(data.rsplit(":", 1)[1])
        ctx.user_data["new_class_reminder"] = {"weekday": weekday}
        ctx.user_data["awaiting_class_reminder_time"] = True
        await q.message.reply_text(
            f"Class day: {CLASS_REMINDER_WEEKDAYS[weekday]}\n\nSend the class time in 24-hour format, for example 19:00 for 7 PM."
        )
        return
    if data.startswith("admin:classreminders:toggle:"):
        rid = int(data.rsplit(":", 1)[1])
        with db() as c:
            r = c.execute("SELECT enabled FROM admin_class_reminders WHERE id=?", (rid,)).fetchone()
            if not r:
                await q.message.reply_text("Reminder not found.")
                return
            c.execute("UPDATE admin_class_reminders SET enabled=? WHERE id=?", (not bool(r["enabled"]), rid))
        await q.message.reply_text("✅ Reminder status updated.")
        await send_admin_dashboard(ctx, uid)
        return
    if data.startswith("admin:classreminders:delete:"):
        rid = int(data.rsplit(":", 1)[1])
        with db() as c:
            c.execute("DELETE FROM admin_class_reminders WHERE id=?", (rid,))
        await q.message.reply_text("🗑 Class reminder deleted.")
        await send_admin_dashboard(ctx, uid)
        return
    if data == "admin:tests":
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        await send_weekly_test_admin_panel(ctx, uid); return
    if data.startswith("admin:tests:release:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        week = int(data.rsplit(":", 1)[1])
        sent, closes = await release_weekly_test(ctx, uid, week)
        await q.message.reply_text(
            f"✅ Week {week} test released immediately.\nEligible students notified: {sent}\nCloses: {closes.strftime('%a, %d %b %Y %I:%M %p')} Nigeria time.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Weekly Tests", callback_data="admin:tests")]])
        )
        return
    if data.startswith("admin:tests:revoke_confirm:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        week = int(data.rsplit(":", 1)[1])
        revoke_weekly_test(uid, week, clear_attempts=False)
        await q.message.reply_text(
            f"🚫 Week {week} test has been revoked. It is hidden immediately and no new attempt can start. Existing completed results were preserved.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Weekly Tests", callback_data="admin:tests")]])
        )
        return
    if data.startswith("admin:tests:revoke:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        week = int(data.rsplit(":", 1)[1])
        await q.message.reply_text(
            f"Revoke Week {week} now?\n\nThis hides the test immediately and cancels any active attempt. Completed scores/results are NOT erased.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 YES, REVOKE", callback_data=f"admin:tests:revoke_confirm:{week}")],
                [InlineKeyboardButton("Cancel", callback_data="admin:tests")],
            ])
        )
        return
    if data.startswith("admin:tests:reset_confirm:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        week = int(data.rsplit(":", 1)[1])
        removed = revoke_weekly_test(uid, week, clear_attempts=True)
        await q.message.reply_text(
            f"🧹 Week {week} has been fully reset for {active_cohort()}.\n\nRemoved attempts: {removed}\nStatus is back to Not released. You can release it again later as a clean test.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Weekly Tests", callback_data="admin:tests")]])
        )
        return
    if data.startswith("admin:tests:reset:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        week = int(data.rsplit(":", 1)[1])
        await q.message.reply_text(
            f"⚠️ FULL RESET WEEK {week}\n\nThis is for testing/clearance. It will revoke Week {week} AND permanently erase every student's Week {week} attempts, answers and results for {active_cohort()}.\n\nUse Revoke instead if you only want to close the test.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧹 YES, RESET EVERYTHING", callback_data=f"admin:tests:reset_confirm:{week}")],
                [InlineKeyboardButton("Cancel", callback_data="admin:tests")],
            ])
        )
        return
    if data.startswith("admin:tests:results:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        week = int(data.rsplit(":", 1)[1])
        with db() as c:
            row = c.execute(
                "SELECT COUNT(DISTINCT user_id) started, COUNT(DISTINCT user_id) FILTER (WHERE passed=TRUE) passed, COUNT(*) attempts, COALESCE(AVG(percentage),0) avg_pct FROM weekly_test_attempts WHERE cohort=? AND week_number=?",
                (active_cohort(), week),
            ).fetchone()
        await q.message.reply_text(
            f"📊 WEEK {week} TEST RESULTS — {active_cohort()}\n\nStudents started: {row['started']}\nStudents passed: {row['passed']}\nTotal attempts: {row['attempts']}\nAverage attempt score: {float(row['avg_pct'] or 0):.1f}%",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Weekly Tests", callback_data="admin:tests")]])
        )
        return
    if data == "admin:clearance":
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        ctx.user_data["awaiting_student_wipe_search"] = True
        await q.message.reply_text(
            "🧹 STUDENT CLEARANCE\n\nSend the exact Student ID (recommended, e.g. HB-0001) or the student's Telegram numeric ID.\n\nThe bot will show the record and ask for confirmation before anything is deleted.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:home")]])
        )
        return
    if data.startswith("admin:wipe:cancel"):
        ctx.user_data.pop("awaiting_student_wipe_search", None)
        await send_admin_dashboard(ctx, uid); return
    if data.startswith("admin:wipe:confirm:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        target_uid = int(data.rsplit(":", 1)[1])
        st = get_student(target_uid)
        if not st:
            await q.message.reply_text("That student record no longer exists.", reply_markup=admin_dashboard_keyboard()); return
        await q.message.reply_text(
            f"⚠️ FINAL CONFIRMATION\n\nDelete {st.get('name')} ({st.get('student_no')}) completely?\n\nThis removes registration, payment records, assignments, support tickets and weekly-test records. The person will be treated as a brand-new user if they start the bot again.\n\nThis cannot be undone.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 PERMANENTLY WIPE STUDENT", callback_data=f"admin:wipe:final:{target_uid}")],
                [InlineKeyboardButton("Cancel", callback_data="admin:home")],
            ])
        )
        return
    if data.startswith("admin:wipe:final:"):
        if uid not in ADMIN_IDS:
            await q.answer("Full admins only.", show_alert=True); return
        target_uid = int(data.rsplit(":", 1)[1])
        snap = wipe_student_record(uid, target_uid)
        if not snap:
            await q.message.reply_text("That student record no longer exists.", reply_markup=admin_dashboard_keyboard()); return
        if snap.get("protected"):
            await q.message.reply_text(
                f"⚠️ {snap['name']} ({snap['student_no']}) already has an issued certificate. That academic identity is protected and cannot be permanently wiped or recycled.",
                reply_markup=admin_dashboard_keyboard()
            ); return
        await q.message.reply_text(
            f"✅ Student wiped successfully.\n\n{snap['name']} ({snap['student_no']}) has been removed. That visible number is now available for reuse inside this cohort, and the person can register again from scratch if needed.",
            reply_markup=admin_dashboard_keyboard()
        )
        return
    if data == "admin:stats":
        with db() as c:
            total=c.execute("SELECT COUNT(*) n FROM students").fetchone()["n"]
            paid=c.execute("SELECT COUNT(*) n FROM students WHERE status='paid'").fetchone()["n"]
            free_access=c.execute("SELECT COUNT(*) n FROM students WHERE COALESCE(free_access,FALSE)=TRUE").fetchone()["n"]
            revenue=c.execute("SELECT COALESCE(SUM(paid_amount),0) r FROM students").fetchone()["r"]
            subs=c.execute("SELECT COUNT(*) n FROM assignment_submissions").fetchone()["n"]
            pending=c.execute("SELECT COUNT(*) n FROM assignment_submissions WHERE review_status='pending'").fetchone()["n"]
        await q.message.reply_text(f"ACADEMY SNAPSHOT\nStudents: {total}\nFully paid: {paid}\nComplimentary access: {free_access}\nConfirmed revenue: ₦{revenue:,}\nAssignment submissions: {subs}\nPending reviews: {pending}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard",callback_data="admin:home")]])); return
    if data == "admin:export":
        with db() as c:
            rows=c.execute("""SELECT * FROM students WHERE COALESCE(archived,FALSE)=FALSE
                              ORDER BY COALESCE(CAST(NULLIF(REGEXP_REPLACE(COALESCE(display_student_no,student_no),'[^0-9]','','g'),'') AS INTEGER),999999), registered_at""").fetchall()
        out=build_student_records_pdf(rows, include_sensitive=(uid in ADMIN_IDS))
        caption = ("📄 Heribhee Studio student records - full admin export" if uid in ADMIN_IDS
                   else "📄 Heribhee Studio student records - reviewer export")
        await q.message.reply_document(
            out,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard", callback_data="admin:home")]])
        )
        return
    if data == "admin:groupmsg":
        enabled = group_messages_enabled()
        status = "ON ✅" if enabled else "OFF ⛔"
        kb = [
            [InlineKeyboardButton("Send Morning Message Now", callback_data="admin:groupmsg:morning")],
            [InlineKeyboardButton("Send Assignment Reminder Now", callback_data="admin:groupmsg:reminder")],
            [InlineKeyboardButton("✏️ Edit Message Pack", callback_data="admin:groupmsg:edit")],
            [InlineKeyboardButton("Write Custom Class Message", callback_data="admin:groupmsg:custom")],
            [InlineKeyboardButton("Test Class Group", callback_data="admin:groupmsg:testclass"), InlineKeyboardButton("Test Review Group", callback_data="admin:groupmsg:testreview")],
            [InlineKeyboardButton(("Turn OFF" if enabled else "Turn ON") + " Auto Messages", callback_data="admin:groupmsg:toggle")],
            [InlineKeyboardButton("Admin dashboard", callback_data="admin:home")],
        ]
        await q.message.reply_text(
            f"📣 GROUP MESSAGES\n\nAutomatic messages: {status}\n"
            f"Morning time: {GROUP_MORNING_TIME}\nReminder time: {GROUP_REMINDER_TIME}\n"
            "Days: Monday, Tuesday, Thursday, Friday\n\n"
            "No payment reminders are included in this message pack.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return
    if data == "admin:groupmsg:edit":
        kb = [
            [InlineKeyboardButton("☀️ Morning Messages", callback_data="admin:pack:kind:morning")],
            [InlineKeyboardButton("📝 Assignment Reminders", callback_data="admin:pack:kind:reminder")],
            [InlineKeyboardButton("Back", callback_data="admin:groupmsg")],
        ]
        await q.message.reply_text(
            "✏️ MESSAGE PACK EDITOR\n\nChoose which set of messages you want to edit.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return
    if data.startswith("admin:pack:kind:"):
        kind = data.rsplit(":", 1)[1]
        label = "Morning" if kind == "morning" else "Assignment reminder"
        kb = [[InlineKeyboardButton(WEEKDAY_NAMES[d], callback_data=f"admin:pack:day:{kind}:{d}")] for d in (0,1,3,4)]
        kb.append([InlineKeyboardButton("Back", callback_data="admin:groupmsg:edit")])
        await q.message.reply_text(f"{label} message pack\n\nChoose a day:", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("admin:pack:day:"):
        _, _, _, kind, weekday_s = data.split(":")
        weekday = int(weekday_s)
        messages = get_group_pack(kind, weekday)
        lines = [f"{i+1}. {m}" for i,m in enumerate(messages)] or ["No messages in this pack yet."]
        kb = []
        for i in range(len(messages)):
            kb.append([
                InlineKeyboardButton(f"Edit #{i+1}", callback_data=f"admin:pack:edit:{kind}:{weekday}:{i}"),
                InlineKeyboardButton(f"Delete #{i+1}", callback_data=f"admin:pack:delete:{kind}:{weekday}:{i}"),
            ])
        kb.append([InlineKeyboardButton("➕ Add Message", callback_data=f"admin:pack:add:{kind}:{weekday}")])
        kb.append([InlineKeyboardButton("↩ Reset to Defaults", callback_data=f"admin:pack:reset:{kind}:{weekday}")])
        kb.append([InlineKeyboardButton("Back", callback_data=f"admin:pack:kind:{kind}")])
        await q.message.reply_text(
            f"{WEEKDAY_NAMES.get(weekday)} — {'Morning' if kind=='morning' else 'Assignment reminder'} messages\n\n" + "\n\n".join(lines),
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return
    if data.startswith("admin:pack:add:"):
        _, _, _, kind, weekday_s = data.split(":")
        weekday = int(weekday_s)
        ctx.user_data["awaiting_pack_message"] = True
        ctx.user_data["pack_editor"] = {"kind": kind, "weekday": weekday, "mode": "add"}
        await q.message.reply_text(f"Send the new {WEEKDAY_NAMES.get(weekday)} message now. Send /admin to cancel.")
        return
    if data.startswith("admin:pack:edit:"):
        _, _, _, kind, weekday_s, index_s = data.split(":")
        weekday, index = int(weekday_s), int(index_s)
        messages = get_group_pack(kind, weekday)
        if index < 0 or index >= len(messages):
            await q.message.reply_text("That message is no longer available. Open the editor again.")
            return
        ctx.user_data["awaiting_pack_message"] = True
        ctx.user_data["pack_editor"] = {"kind": kind, "weekday": weekday, "mode": "edit", "index": index}
        await q.message.reply_text(f"Current message:\n\n{messages[index]}\n\nSend the replacement text now. Send /admin to cancel.")
        return
    if data.startswith("admin:pack:delete:"):
        _, _, _, kind, weekday_s, index_s = data.split(":")
        weekday, index = int(weekday_s), int(index_s)
        messages = get_group_pack(kind, weekday)
        if 0 <= index < len(messages):
            messages.pop(index)
            save_group_pack(kind, weekday, messages)
            await q.message.reply_text("✅ Message deleted.")
        else:
            await q.message.reply_text("That message is no longer available.")
        return
    if data.startswith("admin:pack:reset:"):
        _, _, _, kind, weekday_s = data.split(":")
        weekday = int(weekday_s)
        reset_group_pack(kind, weekday)
        await q.message.reply_text(f"✅ {WEEKDAY_NAMES.get(weekday)} pack reset to the built-in defaults.")
        return
    if data == "admin:groupmsg:toggle":
        new_state = not group_messages_enabled()
        set_app_setting("group_messages_enabled", "true" if new_state else "false")
        await q.message.reply_text(f"Automatic class-group messages are now {'ON ✅' if new_state else 'OFF ⛔'}.")
        await send_admin_dashboard(ctx, uid)
        return
    if data == "admin:groupmsg:morning":
        text = _message_for("morning") or GROUP_MESSAGE_PACK["morning"][0][0]
        try:
            await send_class_group_message(ctx, text)
            await q.message.reply_text("✅ Morning message sent to the class group.")
        except Exception as e:
            await q.message.reply_text(f"Could not send to the class group: {e}")
        return
    if data == "admin:groupmsg:reminder":
        text = _message_for("reminder") or GROUP_MESSAGE_PACK["reminder"][0][0]
        try:
            await send_class_group_message(ctx, text)
            await q.message.reply_text("✅ Assignment reminder sent to the class group.")
        except Exception as e:
            await q.message.reply_text(f"Could not send to the class group: {e}")
        return
    if data == "admin:groupmsg:custom":
        ctx.user_data["awaiting_class_group_message"] = True
        await q.message.reply_text("Type the message you want me to send to the class group. Send /admin to cancel.")
        return
    if data == "admin:groupmsg:testclass":
        if not CLASS_GROUP_ID:
            await q.message.reply_text("CLASS_GROUP_ID is not configured in Render.")
        else:
            try:
                await ctx.bot.send_message(CLASS_GROUP_ID, "✅ Heribhee bot class-group connection test successful.")
                await q.message.reply_text("✅ Test message sent to the class group.")
            except Exception as e:
                await q.message.reply_text(f"Class-group test failed: {e}")
        return
    if data == "admin:groupmsg:testreview":
        if not ADMIN_GROUP_ID:
            await q.message.reply_text("ADMIN_GROUP_ID is not configured in Render.")
        else:
            try:
                await ctx.bot.send_message(ADMIN_GROUP_ID, "✅ Heribhee bot assignment-review group connection test successful.")
                await q.message.reply_text("✅ Test message sent to the assignment-review group.")
            except Exception as e:
                await q.message.reply_text(f"Review-group test failed: {e}")
        return
    if data.startswith("admin:payments:"):
        offset=int(data.rsplit(":",1)[1])
        with db() as c:
            rows=c.execute("""SELECT p.id,p.amount,p.status,p.created_at,s.name,s.student_no
                              FROM payments p LEFT JOIN students s ON s.user_id=p.user_id
                              ORDER BY p.created_at DESC LIMIT 12 OFFSET ?""",(offset,)).fetchall()
        lines=[f"#{r['id']} — {r['name'] or 'Unknown'} ({r['student_no'] or '-'}) — ₦{r['amount']:,} — {r['status']}" for r in rows]
        kb=[]
        if offset: kb.append([InlineKeyboardButton("Previous",callback_data=f"admin:payments:{max(0,offset-12)}")])
        if len(rows)==12: kb.append([InlineKeyboardButton("Next",callback_data=f"admin:payments:{offset+12}")])
        kb.append([InlineKeyboardButton("Admin dashboard",callback_data="admin:home")])
        await q.message.reply_text("PAYMENTS\n\n"+("\n".join(lines) if lines else "No payment records yet."),reply_markup=InlineKeyboardMarkup(kb)); return
    if data == "admin:referrals":
        with db() as c:
            rows=c.execute("""SELECT referred_by,COUNT(*) n FROM students
                              WHERE referred_by IS NOT NULL AND referred_by!=''
                              GROUP BY referred_by ORDER BY n DESC LIMIT 30""").fetchall()
        lines=[]
        for r in rows:
            ref=get_student_by_no(r['referred_by'])
            lines.append(f"{ref['name'] if ref else r['referred_by']} ({r['referred_by']}) — {r['n']} referral(s)")
        await q.message.reply_text("REFERRALS\n\n"+("\n".join(lines) if lines else "No referrals yet."),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard",callback_data="admin:home")]])); return
    if data.startswith("admin:support:"):
        offset=int(data.rsplit(":",1)[1])
        with db() as c:
            rows=c.execute("""SELECT t.id,t.message,t.status,t.created_at,s.name,s.student_no
                              FROM support_tickets t LEFT JOIN students s ON s.user_id=t.user_id
                              ORDER BY CASE WHEN t.status='open' THEN 0 ELSE 1 END,t.created_at DESC
                              LIMIT 10 OFFSET ?""",(offset,)).fetchall()
        if not rows:
            await q.message.reply_text("No support tickets.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard",callback_data="admin:home")]])); return
        for r in rows:
            kb=[[InlineKeyboardButton("Mark handled",callback_data=f"supportdone:{r['id']}")]] if r['status']=='open' else []
            kb.append([InlineKeyboardButton("Admin dashboard",callback_data="admin:home")])
            await q.message.reply_text(f"Ticket #{r['id']} — {r['status'].upper()}\nStudent: {r['name'] or 'Unknown'} ({r['student_no'] or '-'})\nCreated: {r['created_at']}\n\n{r['message']}",reply_markup=InlineKeyboardMarkup(kb))
        return
    if data == "admin:message":
        await q.message.reply_text("MESSAGE STUDENTS\n\nUse one of these admin commands:\n/broadcast all <message>\n/broadcast paid <message>\n/broadcast unpaid <message>\n\nExample:\n/broadcast all Class starts by 8 PM tonight.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard",callback_data="admin:home")]])); return
    if data == "admin:assignments":
        with db() as c:
            rows=c.execute("SELECT review_status,COUNT(*) n FROM assignment_submissions GROUP BY review_status").fetchall()
            total=c.execute("SELECT COUNT(*) n FROM assignment_submissions").fetchone()["n"]
        counts={r["review_status"]:r["n"] for r in rows}
        await q.message.reply_text(f"Assignment submissions: {total}\nPending: {counts.get('pending',0)}\nApproved: {counts.get('approved',0)}\nNeeds correction: {counts.get('correction',0)}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Pending reviews",callback_data="admin:pending:0")],[InlineKeyboardButton("Admin dashboard",callback_data="admin:home")]])); return
    if data == "admin:certs":
        with db() as c:
            rows=c.execute("SELECT s.name,s.student_no,s.certificate_eligible,s.certificate_number,COUNT(a.id) total,SUM(CASE WHEN a.review_status='approved' THEN 1 ELSE 0 END) approved FROM students s LEFT JOIN assignment_submissions a ON a.user_id=s.user_id GROUP BY s.user_id ORDER BY s.name").fetchall()
        lines=["CERTIFICATION PROGRESS", "Verification: certificate numbers are checked against the live Heribhee issuance record. Use /verify CERTIFICATE-NUMBER, or open the public verification URL printed/sent with issued certificates.", ""]
        lines += [f"{r['name']} ({r['student_no']}): {r['approved'] or 0} approved / {r['total'] or 0} submitted — {'ELIGIBLE' if r['certificate_eligible'] else 'Not yet eligible'}{(' — '+r['certificate_number']) if r['certificate_number'] else ''}" for r in rows[:60]]
        await q.message.reply_text("\n".join(lines) if len(lines)>1 else "No student records yet.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard",callback_data="admin:home")]])); return
    if data.startswith("admin:students:"):
        offset=int(data.rsplit(":",1)[1])
        with db() as c:
            rows=c.execute("""SELECT name,student_no,display_student_no,status,user_id,phone,email,occupation,category,cohort,registered_at
                              FROM students WHERE COALESCE(archived,FALSE)=FALSE
                              ORDER BY COALESCE(CAST(NULLIF(REGEXP_REPLACE(COALESCE(display_student_no,student_no),'[^0-9]','','g'),'') AS INTEGER),999999), registered_at
                              LIMIT 15 OFFSET ?""",(offset,)).fetchall()
        if uid in ADMIN_IDS:
            lines=[f"{visible_student_no(r)} — {r['name']} — {r['status']}\nRegistered: {str(r.get('registered_at') or '-')[:16].replace('T',' ')} — Telegram {r['user_id']}" for r in rows]
        else:
            lines=[f"{visible_student_no(r)} — {r['name']}\nRegistered: {str(r.get('registered_at') or '-')[:16].replace('T',' ')}\nRole: {r.get('occupation') or r.get('category') or '-'}\nPhone: {r.get('phone') or '-'}\nEmail: {r.get('email') or '-'}" for r in rows]
        kb=[]
        if offset: kb.append([InlineKeyboardButton("Previous",callback_data=f"admin:students:{max(0,offset-15)}")])
        if len(rows)==15: kb.append([InlineKeyboardButton("Next",callback_data=f"admin:students:{offset+15}")])
        kb.append([InlineKeyboardButton("Admin dashboard",callback_data="admin:home")])
        await q.message.reply_text("STUDENTS\n\n"+("\n".join(lines) if lines else "No more students."),reply_markup=InlineKeyboardMarkup(kb)); return
    if data.startswith("admin:pending:"):
        offset=int(data.rsplit(":",1)[1])
        with db() as c:
            rows=c.execute("SELECT a.id,a.assignment_key,a.submitted_at,s.name,s.student_no FROM assignment_submissions a JOIN students s ON s.user_id=a.user_id WHERE a.review_status='pending' ORDER BY a.submitted_at LIMIT 10 OFFSET ?",(offset,)).fetchall()
        if not rows:
            await q.message.reply_text("No pending assignment reviews.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin dashboard",callback_data="admin:home")]])); return
        for r in rows:
            await q.message.reply_text(f"Submission #{r['id']}\nStudent: {r['name']} ({r['student_no']})\nAssignment: {r['assignment_key']}\nSubmitted: {r['submitted_at']}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open review",callback_data=f"reviewopen:{r['id']}")]]))
        return


async def review_open_callback(update,ctx):
    q=update.callback_query
    if q.from_user.id not in REVIEWER_IDS:
        await q.answer("Authorized assignment reviewers only.",show_alert=True); return
    sid=int(q.data.split(":")[1])
    with db() as c:
        r=c.execute("SELECT a.*,s.name,s.student_no,s.user_id FROM assignment_submissions a JOIN students s ON s.user_id=a.user_id WHERE a.id=?",(sid,)).fetchone()
    if not r:
        await q.answer("Submission not found.",show_alert=True); return
    await q.answer()
    current_score = f"{r.get('score')}/100" if r.get('score') is not None else "Not scored"
    await ctx.bot.send_message(
        q.from_user.id,
        f"REVIEW SUBMISSION #{sid}\nStudent: {r['name']} ({r['student_no']})\nAssignment: {r['assignment_key']}\nSubmitted: {r['submitted_at']}\nCurrent score: {current_score}\n\nSubmission text: {r['text'] or '(No text)'}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Score & Approve",callback_data=f"assignmentreview:approve:{sid}"),
            InlineKeyboardButton("🔁 Request Correction",callback_data=f"assignmentreview:correction:{sid}")
        ]])
    )
    if r['file_id']:
        try: await ctx.bot.send_document(q.from_user.id,r['file_id'],caption=f"Student {r['student_no']} — {r['assignment_key']}")
        except Exception:
            try: await ctx.bot.send_photo(q.from_user.id,r['file_id'],caption=f"Student {r['student_no']} — {r['assignment_key']}")
            except Exception: pass


async def assignment_review_decision(update,ctx):
    q=update.callback_query
    if q.from_user.id not in REVIEWER_IDS:
        await q.answer("Authorized assignment reviewers only.",show_alert=True); return
    _,decision,sid_s=q.data.split(":"); sid=int(sid_s)
    with db() as c:
        r=c.execute("SELECT a.id,a.assignment_key,s.name,s.student_no FROM assignment_submissions a JOIN students s ON s.user_id=a.user_id WHERE a.id=?",(sid,)).fetchone()
    if not r:
        await q.answer("Submission not found.",show_alert=True); return
    await q.answer()
    if decision == "approve":
        ctx.user_data["awaiting_review_score"] = sid
        ctx.user_data.pop("awaiting_review_feedback", None)
        await ctx.bot.send_message(q.from_user.id, f"Score {r['name']} ({r['student_no']}) for '{r['assignment_key']}'.\n\nSend a whole-number score from 0 to 100.")
    else:
        ctx.user_data["awaiting_review_feedback"] = {"sid": sid, "status": "correction", "score": None}
        ctx.user_data.pop("awaiting_review_score", None)
        await ctx.bot.send_message(q.from_user.id, f"Send the correction feedback for {r['name']} ({r['student_no']}). The student will receive this message privately.")


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
            "SELECT source, COUNT(*) n, COUNT(*) FILTER (WHERE paid_amount>0) payers FROM students GROUP BY source ORDER BY n DESC"
        ).fetchall()
        by_cat = c.execute(
            "SELECT category, COUNT(*) n, COUNT(*) FILTER (WHERE paid_amount>0) payers FROM students GROUP BY category"
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

    # New certificates require all four weekly knowledge tests. Existing issued
    # certificates remain permanent and are never invalidated by this new rule.
    if not (s.get("certificate_issued_at") and s.get("certificate_number")):
        missing_tests = missing_weekly_tests(uid)
        if missing_tests:
            await update.message.reply_text(
                f"Certificate not ready for {s['name']} ({s['student_no']}). Missing weekly test pass(es): "
                + ", ".join(f"Week {w}" for w in missing_tests)
                + ". Complete the weekly tests plus the Academy's project/oral-defense requirements before issuing the certificate."
            )
            return

    # Certificates are permanent documents. Re-running /complete must never
    # replace the original issue date or certificate number.
    existing_issued_at = s.get("certificate_issued_at")
    existing_cert_no = s.get("certificate_number")
    if existing_issued_at and existing_cert_no:
        issued_at = existing_issued_at
        cert_no = existing_cert_no
        with db() as c:
            c.execute(
                "UPDATE students SET status='completed', certificate_eligible=TRUE WHERE user_id=?",
                (uid,),
            )
    else:
        issued_at = now().isoformat()
        cert_no = f"HB-CERT-{s['student_no'].replace('HB-','')}"
        with db() as c:
            c.execute(
                "UPDATE students SET status='completed', completed_at=COALESCE(completed_at, ?), certificate_eligible=TRUE, certificate_issued_at=?, certificate_number=? WHERE user_id=?",
                (issued_at, issued_at, cert_no, uid),
            )

    issue_date = datetime.fromisoformat(issued_at).strftime("%d %b %Y")
    audit_log(update.effective_user.id, "certificate_issued", "student", s["student_no"], f"certificate={cert_no}; issued={issued_at}", student_user_id=uid)
    try:
        cert = cards.generate_certificate(s["name"], PROGRAM, issue_date, cert_no)
        verify_url = certificate_verify_url(cert_no)
        verify_line = f"\nVerify: {verify_url}" if verify_url else f"\nVerify in the bot with /verify {cert_no}"
        await ctx.bot.send_photo(
            uid, cert,
            caption=f"🎓 Congratulations — you've completed the program! Certificate No: {cert_no}{verify_line}"
        )
        await update.message.reply_text(f"Marked {s['name']} ({s['student_no']}) as completed and sent their certificate.")
    except Exception as e:
        log.warning("Could not send certificate to %s: %s", uid, e)
        await update.message.reply_text(f"Marked {s['name']} ({s['student_no']}) as completed, but sending the certificate failed.")


@admin_only
async def export_pdf(update, ctx):
    with db() as c:
        rows = c.execute("SELECT * FROM students WHERE COALESCE(archived,FALSE)=FALSE ORDER BY student_no").fetchall()
    out = build_student_records_pdf(rows)
    await update.message.reply_document(out, caption="📄 Heribhee Studio student records - clean PDF export")


@admin_only
async def broadcast(update, ctx):
    if len(ctx.args) < 2 or ctx.args[0] not in ("all", "unpaid", "paid"):
        await update.message.reply_text("Usage: /broadcast <all|unpaid|paid> <message>")
        return
    audience, text = ctx.args[0], " ".join(ctx.args[1:])
    query = "SELECT user_id FROM students"
    if audience == "unpaid":
        query += " WHERE status IN ('registered','part_paid') AND COALESCE(free_access,FALSE)=FALSE"
    elif audience == "paid":
        query += " WHERE status='paid' OR COALESCE(free_access,FALSE)=TRUE"
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


# ---------- legacy private payment reminders ----------
async def daily_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    # Intentionally disabled. Heribhee Studio announces payment manually in class.
    return


async def telegram_error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    """Log full callback/handler failures and stop buttons from failing silently."""
    log.error("Unhandled Telegram update error", exc_info=ctx.error)
    try:
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.answer(
                "Something went wrong while processing that action. Please try again.",
                show_alert=True,
            )
    except Exception:
        # Never let the error-notification path hide the original exception.
        pass


def build_telegram_application():
    app = Application.builder().token(BOT_TOKEN).build()
    form = ConversationHandler(
        entry_points=[CommandHandler("start", start), CallbackQueryHandler(begin_registration, pattern=r"^register:new$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_age)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_email)],
            FOUND_US: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_found_us)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_goal)],
            OCCUPATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_occupation)],
            MOTIVATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_motivation)],
            CATEGORY: [CallbackQueryHandler(got_category, pattern=r"^cat:\d+$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(form)
    app.add_handler(CommandHandler("pay", pay_cmd))
    app.add_handler(CommandHandler("curriculum", curriculum_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("chatid", chatid_cmd))
    app.add_handler(CommandHandler("review", review_cmd))
    app.add_handler(CommandHandler("admin", lambda update, ctx: send_admin_dashboard(ctx, update.effective_user.id) if update.effective_user.id in REVIEWER_IDS else None))
    app.add_handler(CommandHandler("certificate", certificate_cmd))
    app.add_handler(CommandHandler("verify", verify_certificate_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(account_callback, pattern=r"^(profile:|recover:).+"))
    app.add_handler(CallbackQueryHandler(weekly_test_callback, pattern=r"^(test:|project:).+"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^(menu:|rules:|faq:|faqanswer:|assignment:).+"))
    app.add_handler(CallbackQueryHandler(admin_dashboard_callback, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(review_open_callback, pattern=r"^reviewopen:\d+$"))
    app.add_handler(CallbackQueryHandler(assignment_review_decision, pattern=r"^assignmentreview:(approve|correction):\d+$"))
    app.add_handler(CallbackQueryHandler(moderation_decision, pattern=r"^mod:(remove|dismiss):\d+$"))
    app.add_handler(CallbackQueryHandler(support_decision, pattern=r"^supportdone:\d+$"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND, student_private_message), group=2)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & (filters.TEXT | filters.CAPTION), group_moderation), group=1)
    app.add_handler(CommandHandler("refer", refer_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CommandHandler("exportpdf", export_pdf))
    app.add_handler(CommandHandler("complete", complete_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(review_payment, pattern=r"^(ap|rj):\d+$"))
    app.add_handler(CallbackQueryHandler(choose_plan, pattern=r"^plan:(full|two)$"))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & filters.ChatType.PRIVATE, got_proof))
    # Automatic private payment reminders intentionally disabled.
    app.job_queue.run_daily(scheduled_group_morning, time=_parse_hhmm(GROUP_MORNING_TIME, "08:00"))
    app.job_queue.run_daily(scheduled_group_reminder, time=_parse_hhmm(GROUP_REMINDER_TIME, "17:00"))
    app.job_queue.run_repeating(check_admin_class_reminders, interval=60, first=15)
    app.job_queue.run_repeating(scheduled_expired_test_check, interval=30, first=20)
    app.add_error_handler(telegram_error_handler)
    return app


telegram_app = build_telegram_application()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Establish the pool once when Render starts the service.
    DB_POOL.open(wait=True, timeout=20)
    init_db()

    missing_card_assets = cards.validate_assets()
    if missing_card_assets:
        log.error("Missing card/certificate assets: %s", ", ".join(missing_card_assets))
    else:
        log.info("Certificate and student-card templates verified")

    if not os.path.exists(CURRICULUM_FILE):
        log.warning("Curriculum file not found at startup: %s", CURRICULUM_FILE)
    else:
        log.info("Curriculum file verified: %s", CURRICULUM_FILE)

    await telegram_app.initialize()
    await telegram_app.start()

    external_url = WEBHOOK_URL or os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if external_url:
        webhook_url = external_url if external_url.endswith("/telegram") else external_url + "/telegram"
        kwargs = {"url": webhook_url, "allowed_updates": Update.ALL_TYPES}
        if WEBHOOK_SECRET:
            kwargs["secret_token"] = WEBHOOK_SECRET
        await telegram_app.bot.set_webhook(**kwargs)
        log.info("Telegram webhook configured: %s", webhook_url)
    else:
        log.warning("No WEBHOOK_URL/RENDER_EXTERNAL_URL yet. Webhook will be set after Render provides the public URL.")

    yield

    await telegram_app.stop()
    await telegram_app.shutdown()
    DB_POOL.close()


web = FastAPI(title="Heribhee Academy Bot", lifespan=lifespan)


@web.get("/")
@web.get("/health")
async def health():
    return {"status": "ok", "service": "Heribhee Academy Bot"}


@web.api_route("/reminder-check", methods=["GET", "POST"])
async def reminder_check(request: Request):
    """External wake-up/check endpoint for free hosting.

    Configure an external cron service to call this every 5 minutes. The secret
    may be supplied as X-Reminder-Secret or ?secret=. Due sends are de-duplicated.
    """
    if not REMINDER_TRIGGER_SECRET:
        raise HTTPException(status_code=503, detail="Reminder trigger is not configured")
    supplied = request.headers.get("X-Reminder-Secret") or request.query_params.get("secret", "")
    if supplied != REMINDER_TRIGGER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid reminder trigger secret")

    class _Ctx:
        bot = telegram_app.bot

    ctx = _Ctx()
    await check_admin_class_reminders(ctx)
    expired_tests_submitted = await finalize_expired_test_attempts(ctx)
    morning_sent = await _send_group_schedule_once(ctx, "morning", GROUP_MORNING_TIME, require_due_window=True)
    reminder_sent = await _send_group_schedule_once(ctx, "reminder", GROUP_REMINDER_TIME, require_due_window=True)
    return {
        "ok": True,
        "checked_at": now().isoformat(),
        "expired_tests_submitted": expired_tests_submitted,
        "morning_sent": morning_sent,
        "class_group_reminder_sent": reminder_sent,
    }


@web.get("/verify-certificate/{certificate_number}", response_class=HTMLResponse)
async def verify_certificate_web(certificate_number: str):
    r = get_certificate_record(certificate_number)
    if not r:
        return HTMLResponse(
            "<html><body style='font-family:Arial;padding:40px'><h2>Certificate not verified</h2><p>No issued Heribhee Studio certificate matches this number.</p></body></html>",
            status_code=404,
        )
    issued = datetime.fromisoformat(r["certificate_issued_at"]).strftime("%d %b %Y") if r.get("certificate_issued_at") else "-"
    body = f"""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>Heribhee Certificate Verification</title></head>
    <body style='font-family:Arial,sans-serif;background:#f6f1e4;color:#12213d;padding:24px'>
    <div style='max-width:650px;margin:30px auto;background:white;border:2px solid #c39a43;border-radius:18px;padding:28px'>
    <h1 style='margin-top:0'>✅ Certificate Verified</h1>
    <p>This certificate number exists in the official Heribhee Studio issuance record.</p>
    <hr><p><b>Certificate No:</b> {escape(str(r['certificate_number']))}</p>
    <p><b>Recipient:</b> {escape(str(r['name']))}</p>
    <p><b>Student ID:</b> {escape(str(visible_student_no(r)))}</p>
    <p><b>Program:</b> {escape(PROGRAM)}</p>
    <p><b>Issue date:</b> {escape(issued)}</p>
    <hr><p style='font-size:14px'>Compare these details with the certificate presented to you. A changed name, number, or issue date means the document does not match the official record.</p>
    </div></body></html>"""
    return HTMLResponse(body)


@web.post("/telegram")
async def telegram_webhook(request: Request):
    if WEBHOOK_SECRET:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if supplied != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
