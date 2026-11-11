# Spendora — Full-stack subscription manager

## Run locally (Windows)
Install Python 3.11+. Open a terminal in this folder:
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```
Visit http://127.0.0.1:5000. SQLite database is created automatically.

## Recurring billing
Monthly plan: billing day `25` means every 25th. No year is entered.
Yearly plan: select a day and month. Days unavailable in a month are clamped to its last day.
Dashboard converts yearly prices to monthly equivalents for budgeting.

## Deploy to Render
1. Push this folder to a GitHub repository.
2. Create a Render Web Service from that repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Create a Render PostgreSQL database and set `DATABASE_URL` to its Internal Database URL.
6. Set `SECRET_KEY` to a long random value and `ENABLE_SCHEDULER=true` for a single web instance.
7. Deploy and open the HTTPS URL.

Do not use ephemeral SQLite storage for production. Use PostgreSQL and configure backups.

## Phone/browser push reminders
Push requires HTTPS, browser permission, and VAPID keys. Generate a key pair using a VAPID key generator or pywebpush tooling. Set `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_SUBJECT` in the deployment environment, redeploy, sign in, then use Enable browser push. Test on each device/browser.

The built-in APScheduler checks every 30 minutes. It is suitable only for a single web instance. For multiple workers/instances, set `ENABLE_SCHEDULER=false` and run the reminder job in a dedicated worker/cron process to avoid duplicate jobs.

## Before public production
Add CSRF protection, rate limiting, email verification, password reset, backups, monitoring and security review. The app tracks expected renewal dates; it does not verify actual charges or cancel provider subscriptions automatically. Currency is a display setting, not FX conversion.
