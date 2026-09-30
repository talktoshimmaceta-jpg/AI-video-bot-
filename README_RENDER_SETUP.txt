HERIBHEE ACADEMY BOT - RENDER + SUPABASE

Files Render needs:
- bot.py
- cards.py
- requirements.txt
- curriculum.pdf (optional but recommended)
- logo.png (optional)

Render service settings:
Runtime: Python
Build command: pip install -r requirements.txt
Start command: uvicorn bot:web --host 0.0.0.0 --port $PORT

Required environment variables:
BOT_TOKEN
DATABASE_URL
ADMIN_IDS
WEBHOOK_SECRET

Useful optional variables:
ASSIGNMENT_REVIEWER_IDS
ADMIN_GROUP_ID
CLASS_GROUP_ID
PROGRAM_NAME
PRICE_FULL
PRICE_HALF
BANK_DETAILS
PAY_LINK
CLASS_LINK
CLASS_LINK_2
WHATSAPP_LINK
BOT_USERNAME
REFERRAL_BONUS_THRESHOLD
REFERRAL_FREE_ACCESS_CAP
RULES_VERSION

DATABASE_URL should be the Supabase Shared Pooler connection string.
Replace [YOUR-PASSWORD] in Supabase's displayed string with your actual database password before saving it in Render.
Never commit the actual DATABASE_URL or BOT_TOKEN to GitHub.

Health check path: /health
Telegram webhook path: /telegram
The app automatically uses RENDER_EXTERNAL_URL to register the Telegram webhook after startup.
