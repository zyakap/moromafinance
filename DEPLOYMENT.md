# Moroma Finance Ltd — Deployment & Operations

Whitelabelled LoanMasta tenant for **Moroma Finance Ltd** ("Your Local Finance
Partner") — Port Moresby (Gordons) & Banz, PNG.

Target stack: **pipenv → gunicorn → nginx** with MySQL and Redis/Celery.

> After any code/settings change, restart gunicorn so workers reload:
> `sudo systemctl restart gunicorn`

---

## 0. Before go-live — tenant data checklist

This codebase was whitelabelled from the LoanMasta tenant template. These items
are **placeholders inherited from the template** and must be replaced with
Moroma's own data before taking real applications:

- [x] **Repayment schedule** — DONE: `custom/functions.py` `REPAYMENT_TABLE`
      regenerated from the client's deduction schedule (`client_documents/`
      "1 Updated Ded Sch 2026.pdf", effective 1 Dec 2025): K500–K5,000 in K50
      steps, 7–36 fortnights (min term 14 below K1,000, 9 below K2,000).
      `static_files/clientfiles/RepaymentTable.pdf` replaced with the client PDF.
- [ ] **Bank account details** — prefilled from the client's application form
      (BSP Waterfront Branch, Cheque Account No. 7016639473, Deduction Code
      `DMAWE`). **Verify with the client at go-live**; the admin
      **Settings → AdminSettings** screen overrides the settings.py fallback.
- [x] **Loan limits** — DONE: K500–K5,000, K50 steps, 7–36 fortnights in
      `moromafinance/settings.py` and across website copy.
- [ ] **Logo artwork** — `static_files/clientfiles/moroma_logo.svg`,
      `static_files/img/moroma_favicon.svg` and
      `static_files/clientfiles/brandlogo.png` are recreated approximations of
      the client mark (`client_documents/5.Moroma Logo.jpg`). Swap in
      professional artwork when supplied, keeping the same file names/paths.
- [x] **ALESCO deduction code** — DONE: `DMAWE` (printed on the client's in-use
      application form) is the settings.py default; override via `.env` if it
      changes.
- [ ] **DCC onboarding** — set `DCC_TENANT_LUID` / `DCC_API_KEY` /
      `DCC_PROFILE_ID` in `.env` once Moroma is registered in the DCC control
      panel. Blank values keep DCC dormant.
- [ ] **reCAPTCHA keys** — generate for `moromafinance.com.pg` and set
      `RECAPTCHA_PUBLIC_KEY` / `RECAPTCHA_PRIVATE_KEY`.

## 1. Environment & secrets (`.env`)

All secrets live in `.env` at the project root (git-ignored, `chmod 600`). The
app loads it automatically (`moromafinance/settings.py`). Template: `.env.example`.

```bash
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# paste into DJANGO_SECRET_KEY, fill in DB / email / reCAPTCHA values
chmod 600 .env
```

Production identity settings (already defaulted in `.env.example`):

| Key | Value |
| --- | --- |
| `DJANGO_ALLOWED_HOSTS` | `moromafinance.com.pg,www.moromafinance.com.pg` |
| `DJANGO_DOMAIN` | `https://www.moromafinance.com.pg` |
| `DJANGO_DOMAIN_DNS` | `moromafinance.com.pg` |
| `MOROMA_CODE_PREFIX` | `MFX` |

Tenant mailboxes (from client documents): `sales@moromafinance.com.pg`
(public/sender), `mktosa@moromafinance.com.pg` (admin notifications).

## 2. Database

```sql
CREATE DATABASE moromafinance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'moromafinance_app'@'localhost' IDENTIFIED BY 'a-strong-password';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES
  ON moromafinance.* TO 'moromafinance_app'@'localhost';
FLUSH PRIVILEGES;
```
Then set `DB_USER` / `DB_PASSWORD` in `.env` and run:

```bash
pipenv run python manage.py migrate
pipenv run python manage.py createsuperuser
pipenv run python manage.py collectstatic
```

## 3. Celery + Redis

Reminders, default runs and classification fire via Celery. To enable:

```bash
sudo apt-get install -y redis-server weasyprint
sudo systemctl enable --now redis-server
redis-cli ping   # -> PONG
```
`.env` points the broker at `redis://127.0.0.1:6379/0`. Add systemd units:

```ini
# /etc/systemd/system/moromafinance-celery.service
[Unit]
Description=Moroma Finance Celery worker
After=network.target redis-server.service
[Service]
WorkingDirectory=/path/to/moromafinance
ExecStart=/path/to/virtualenv/bin/celery -A moromafinance worker -l info
Restart=always
[Install]
WantedBy=multi-user.target
```
```ini
# /etc/systemd/system/moromafinance-celerybeat.service
[Unit]
Description=Moroma Finance Celery beat
After=network.target redis-server.service
[Service]
WorkingDirectory=/path/to/moromafinance
ExecStart=/path/to/virtualenv/bin/celery -A moromafinance beat -l info
Restart=always
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now moromafinance-celery moromafinance-celerybeat
```
Until then, bulk messaging still works — it falls back to running synchronously
in the web request (`message/tasks.dispatch_task`).

## 4. nginx: static, media, and protecting uploaded KYC documents

Uploaded IDs/payslips must **not** be world-readable. Serve them only through
the authenticated Django view `/media/<path>` and make the raw directory internal:

```nginx
# Static files
location /static/ { alias /path/to/moromafinance/static/; }

# Raw uploads: reachable ONLY via Django's X-Accel-Redirect (never public)
location /protected-uploads/ {
    internal;
    alias /path/to/moromafinance/uploads/;
}
```
Then set `USE_X_ACCEL_REDIRECT=True` in `.env`. Until configured, the `/media/`
view still streams files itself (just less efficiently), and access is gated by login.

## 5. DCC API (machine-to-machine)

`/API/profiles/`, `/API/loans/`, `/API/statements/` require the header
`X-API-KEY: <DCC_API_KEY>` (value in `.env`). Once Moroma is onboarded, the DCC
control panel (Tenants & API Setup) must hold the same LUID/key pair, or the
feed returns HTTP 403. Leave blank to keep DCC dormant.

## 6. Going to production (`DEBUG=False`)

1. Confirm nginx serves `/static/` (section 4) and run `python manage.py collectstatic`.
2. Confirm uploads are protected (section 4).
3. Confirm `python manage.py check --deploy` shows only the HSTS/SSL-redirect warnings.
4. Ensure nginx sets `proxy_set_header X-Forwarded-Proto $scheme;`.
5. Set `DJANGO_DEBUG=False`, then optionally `DJANGO_SECURE_SSL_REDIRECT=True` and
   raise `DJANGO_SECURE_HSTS_SECONDS` gradually (3600 → 31536000).
6. Keep `DJANGO_SESSION_COOKIE_SECURE` / `DJANGO_CSRF_COOKIE_SECURE` unset (they
   default to secure once DEBUG=False). Only override them for a temporary
   HTTP-only preview before TLS is issued — logins silently fail otherwise.
7. `sudo systemctl restart gunicorn` and smoke-test login, a loan view, and a PDF.

## 7. Backups

```bash
# Database — nightly, kept 14 days
mysqldump -u root -p moromafinance | gzip > /var/backups/moromafinance-$(date +\%F).sql.gz

# Uploaded documents
tar czf /var/backups/moromafinance-uploads-$(date +\%F).tar.gz -C /path/to/moromafinance uploads
```
Add both to root's crontab and **test a restore** at least once. Store copies off-box.

## 8. Tests

```bash
DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: DJANGO_DEBUG=False \
    pipenv run python manage.py test loan
```
Runs against in-memory SQLite, so it never touches the production database.
