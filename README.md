# ZedBinaryOption — Flask Edition

A demo broker-like web app inspired by Deriv, rebuilt with **HTML + CSS +
vanilla JavaScript** on the frontend and **Python (Flask) + SQLite** on the
backend.

> Demo only — M-Pesa is **simulated**, the trading engine is a **mock**.
> Do not use for real money.

## Features

- Email/password signup + login (passwords hashed with scrypt)
- Optional **Google OAuth** sign-in (set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
  Without those env vars, a "Continue with Google" demo button signs you in as
  a stub Google user.
- KYC submission form with ID document upload
- Trading account auto-provisioned per user (KES, demo)
- Simulated M-Pesa STK Push deposit
- Mock trading on Volatility / Boom / Crash indices (Rise/Fall, 5–600s)
- Trader dashboard: profile, balance, recent transactions & trades

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

The SQLite database and uploads live in `instance/` (auto-created).

## Optional: real Google OAuth

```bash
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
export SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
python app.py
```

Authorized redirect URI in Google Cloud Console:
`http://localhost:5000/auth/google/callback`

## Project layout

```
app.py                  Flask app + all API endpoints
templates/              Jinja HTML pages
static/css/styles.css   Dark fintech theme
static/js/              Page-specific JS modules
instance/               SQLite DB + uploaded files (gitignored)
```
