"""
ZedBinaryOption - Flask backend
Pure HTML/CSS/JS frontend, Flask + SQLite backend.
Demo only: M-Pesa is simulated, trading engine is mocked.
"""
import os
import sqlite3
import secrets
import hashlib
import time
import random
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, g, request, jsonify, render_template,
    session, redirect, url_for, send_from_directory, abort
)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "zedbinary.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "instance", "uploads")
AVATAR_DIR = os.path.join(BASE_DIR, "instance", "avatars")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-zedbinary-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB uploads

# Optional Google OAuth (only active if env vars provided)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")


# ---------- DB helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        full_name TEXT,
        avatar TEXT,
        provider TEXT DEFAULT 'email',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS kyc_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        full_name TEXT, dob TEXT, country TEXT, id_number TEXT,
        address TEXT, phone TEXT,
        document_path TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS trading_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        currency TEXT DEFAULT 'KES',
        balance REAL DEFAULT 0,
        account_type TEXT DEFAULT 'demo',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        type TEXT NOT NULL,             -- deposit | withdraw | trade
        amount REAL NOT NULL,
        method TEXT,                    -- mpesa, internal
        reference TEXT,
        status TEXT DEFAULT 'completed',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,        -- rise | fall
        stake REAL NOT NULL,
        duration INTEGER NOT NULL,      -- seconds
        entry_price REAL,
        exit_price REAL,
        payout REAL DEFAULT 0,
        result TEXT DEFAULT 'pending',  -- win | lose | pending
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        settled_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    db.commit()
    db.close()


# ---------- auth helpers ----------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64).hex()
    return f"scrypt${salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, h = stored.split("$")
        if scheme != "scrypt":
            return False
        check = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64).hex()
        return secrets.compare_digest(check, h)
    except Exception:
        return False


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login_page"))
        return fn(*a, **kw)
    return wrapper


def ensure_account(user_id: int):
    db = get_db()
    acc = db.execute("SELECT * FROM trading_accounts WHERE user_id = ?", (user_id,)).fetchone()
    if not acc:
        db.execute(
            "INSERT INTO trading_accounts (user_id, currency, balance, account_type) VALUES (?, 'KES', 0, 'demo')",
            (user_id,),
        )
        db.commit()
        acc = db.execute("SELECT * FROM trading_accounts WHERE user_id = ?", (user_id,)).fetchone()
    return acc


# ---------- Page routes ----------
@app.route("/")
def index():
    return render_template("index.html", user=current_user())


@app.route("/about")
def about():
    return render_template("about.html", user=current_user())


@app.route("/markets")
def markets():
    return render_template("markets.html", user=current_user())


@app.route("/login")
def login_page():
    return render_template("login.html", user=current_user(), google_enabled=bool(GOOGLE_CLIENT_ID))


@app.route("/signup")
def signup_page():
    return render_template("signup.html", user=current_user(), google_enabled=bool(GOOGLE_CLIENT_ID))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user())


@app.route("/kyc")
@login_required
def kyc_page():
    return render_template("kyc.html", user=current_user())


@app.route("/deposit")
@login_required
def deposit_page():
    return render_template("deposit.html", user=current_user())


@app.route("/trade")
@login_required
def trade_page():
    return render_template("trade.html", user=current_user())


@app.route("/profile")
@login_required
def profile_page():
    return render_template("profile.html", user=current_user())


# ---------- Auth API ----------
@app.post("/api/signup")
def api_signup():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    if not email or not password or len(password) < 6:
        return jsonify({"error": "Provide email and password (min 6 chars)"}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return jsonify({"error": "Email already registered"}), 409
    db.execute(
        "INSERT INTO users (email, password_hash, full_name, provider) VALUES (?, ?, ?, 'email')",
        (email, hash_password(password), full_name),
    )
    db.commit()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    ensure_account(user["id"])
    session["user_id"] = user["id"]
    return jsonify({"ok": True, "redirect": "/dashboard"})


@app.post("/api/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not user["password_hash"] or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password"}), 401
    ensure_account(user["id"])
    session["user_id"] = user["id"]
    return jsonify({"ok": True, "redirect": "/dashboard"})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# ---- Google OAuth (optional) ----
@app.route("/auth/google")
def auth_google():
    if not GOOGLE_CLIENT_ID:
        # Demo fallback: create/login a demo google user
        email = "demo.google@zedbinary.app"
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            db.execute(
                "INSERT INTO users (email, full_name, provider) VALUES (?, 'Demo Google User', 'google')",
                (email,),
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        ensure_account(user["id"])
        session["user_id"] = user["id"]
        return redirect("/dashboard")
    # Real OAuth flow
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    redirect_uri = url_for("auth_google_callback", _external=True)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    from urllib.parse import urlencode
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.route("/auth/google/callback")
def auth_google_callback():
    import urllib.request, urllib.parse, json as _json
    if request.args.get("state") != session.get("oauth_state"):
        return "Invalid state", 400
    code = request.args.get("code")
    if not code:
        return "Missing code", 400
    redirect_uri = url_for("auth_google_callback", _external=True)
    token_data = urllib.parse.urlencode({
        "code": code, "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    try:
        with urllib.request.urlopen("https://oauth2.googleapis.com/token", token_data, timeout=10) as r:
            tok = _json.loads(r.read())
        with urllib.request.urlopen(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tok['access_token']}"} if False else None,
        ) as r:
            info = _json.loads(r.read())
    except Exception:
        # urllib doesn't accept headers in urlopen; do it properly
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tok['access_token']}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            info = _json.loads(r.read())
    email = (info.get("email") or "").lower()
    name = info.get("name") or ""
    if not email:
        return "Google did not return an email", 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        db.execute(
            "INSERT INTO users (email, full_name, provider) VALUES (?, ?, 'google')",
            (email, name),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    ensure_account(user["id"])
    session["user_id"] = user["id"]
    return redirect("/dashboard")


# ---------- Account / dashboard API ----------
@app.get("/api/me")
@login_required
def api_me():
    user = current_user()
    acc = ensure_account(user["id"])
    db = get_db()
    kyc = db.execute(
        "SELECT status FROM kyc_submissions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user["id"],),
    ).fetchone()
    txs = db.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (user["id"],),
    ).fetchall()
    trades = db.execute(
        "SELECT * FROM trades WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (user["id"],),
    ).fetchall()
    return jsonify({
        "user": {
            "id": user["id"], "email": user["email"],
            "full_name": user["full_name"], "avatar": user["avatar"],
            "provider": user["provider"],
        },
        "account": dict(acc),
        "kyc_status": kyc["status"] if kyc else "not_submitted",
        "transactions": [dict(t) for t in txs],
        "trades": [dict(t) for t in trades],
    })


@app.post("/api/profile")
@login_required
def api_profile_update():
    user = current_user()
    db = get_db()
    full_name = request.form.get("full_name", user["full_name"])
    avatar_path = user["avatar"]
    f = request.files.get("avatar")
    if f and f.filename:
        ext = os.path.splitext(secure_filename(f.filename))[1].lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            return jsonify({"error": "Unsupported image"}), 400
        name = f"u{user['id']}_{int(time.time())}{ext}"
        f.save(os.path.join(AVATAR_DIR, name))
        avatar_path = f"/uploads/avatars/{name}"
    db.execute("UPDATE users SET full_name = ?, avatar = ? WHERE id = ?",
               (full_name, avatar_path, user["id"]))
    db.commit()
    return jsonify({"ok": True})


@app.get("/uploads/avatars/<path:filename>")
def serve_avatar(filename):
    return send_from_directory(AVATAR_DIR, filename)


# ---------- KYC ----------
@app.post("/api/kyc")
@login_required
def api_kyc_submit():
    user = current_user()
    fields = ["full_name", "dob", "country", "id_number", "address", "phone"]
    data = {k: request.form.get(k, "").strip() for k in fields}
    if not all(data.values()):
        return jsonify({"error": "All fields are required"}), 400
    doc = request.files.get("document")
    doc_path = None
    if doc and doc.filename:
        ext = os.path.splitext(secure_filename(doc.filename))[1].lower()
        if ext not in {".png", ".jpg", ".jpeg", ".pdf", ".webp"}:
            return jsonify({"error": "Unsupported document type"}), 400
        name = f"kyc_u{user['id']}_{int(time.time())}{ext}"
        doc.save(os.path.join(UPLOAD_DIR, name))
        doc_path = name
    db = get_db()
    db.execute("""INSERT INTO kyc_submissions
        (user_id, full_name, dob, country, id_number, address, phone, document_path, status)
        VALUES (?,?,?,?,?,?,?,?,'pending')""",
        (user["id"], data["full_name"], data["dob"], data["country"],
         data["id_number"], data["address"], data["phone"], doc_path))
    db.commit()
    return jsonify({"ok": True, "status": "pending"})


# ---------- Deposit (simulated M-Pesa STK Push) ----------
@app.post("/api/deposit/mpesa")
@login_required
def api_deposit_mpesa():
    data = request.get_json(force=True, silent=True) or {}
    try:
        amount = float(data.get("amount") or 0)
    except ValueError:
        amount = 0
    phone = (data.get("phone") or "").strip()
    if amount < 10:
        return jsonify({"error": "Minimum deposit is KES 10"}), 400
    if not phone or len(phone) < 9:
        return jsonify({"error": "Enter a valid M-Pesa phone number"}), 400
    user = current_user()
    acc = ensure_account(user["id"])
    db = get_db()
    ref = "MPESA-" + secrets.token_hex(4).upper()
    # simulate STK push success
    db.execute("UPDATE trading_accounts SET balance = balance + ? WHERE id = ?",
               (amount, acc["id"]))
    db.execute("""INSERT INTO transactions
        (user_id, account_id, type, amount, method, reference, status)
        VALUES (?,?,?,?,?,?,?)""",
        (user["id"], acc["id"], "deposit", amount, "mpesa", ref, "completed"))
    db.commit()
    return jsonify({"ok": True, "reference": ref, "message": "STK push approved (simulated)"})


# ---------- Trading (mock engine) ----------
SYMBOLS = {
    "VOL10":  {"name": "Volatility 10 Index",  "vol": 0.10},
    "VOL25":  {"name": "Volatility 25 Index",  "vol": 0.25},
    "VOL50":  {"name": "Volatility 50 Index",  "vol": 0.50},
    "VOL75":  {"name": "Volatility 75 Index",  "vol": 0.75},
    "VOL100": {"name": "Volatility 100 Index", "vol": 1.00},
    "BOOM500":  {"name": "Boom 500 Index",   "vol": 0.60},
    "CRASH500": {"name": "Crash 500 Index",  "vol": 0.60},
}


def tick_price(symbol: str) -> float:
    cfg = SYMBOLS.get(symbol, {"vol": 0.5})
    base = 1000 + (hash(symbol) % 500)
    drift = (time.time() % 600) * 0.05
    noise = random.gauss(0, cfg["vol"] * 5)
    return round(base + drift + noise, 4)


@app.get("/api/symbols")
def api_symbols():
    return jsonify([{"id": k, **v, "price": tick_price(k)} for k, v in SYMBOLS.items()])


@app.get("/api/tick/<symbol>")
def api_tick(symbol):
    if symbol not in SYMBOLS:
        return jsonify({"error": "unknown symbol"}), 404
    return jsonify({"symbol": symbol, "price": tick_price(symbol), "ts": int(time.time())})


@app.post("/api/trade")
@login_required
def api_trade():
    data = request.get_json(force=True, silent=True) or {}
    symbol = data.get("symbol")
    direction = data.get("direction")
    try:
        stake = float(data.get("stake") or 0)
        duration = int(data.get("duration") or 0)
    except ValueError:
        return jsonify({"error": "Invalid stake/duration"}), 400
    if symbol not in SYMBOLS or direction not in ("rise", "fall"):
        return jsonify({"error": "Invalid trade params"}), 400
    if stake < 10 or duration < 5 or duration > 600:
        return jsonify({"error": "Stake >= 10, duration 5-600 seconds"}), 400
    user = current_user()
    acc = ensure_account(user["id"])
    if acc["balance"] < stake:
        return jsonify({"error": "Insufficient balance"}), 400
    db = get_db()
    entry = tick_price(symbol)
    db.execute("UPDATE trading_accounts SET balance = balance - ? WHERE id = ?",
               (stake, acc["id"]))
    cur = db.execute("""INSERT INTO trades
        (user_id, account_id, symbol, direction, stake, duration, entry_price, result)
        VALUES (?,?,?,?,?,?,?,'pending')""",
        (user["id"], acc["id"], symbol, direction, stake, duration, entry))
    trade_id = cur.lastrowid
    db.execute("""INSERT INTO transactions
        (user_id, account_id, type, amount, method, reference, status)
        VALUES (?,?,?,?,?,?,?)""",
        (user["id"], acc["id"], "trade", -stake, "internal",
         f"TRADE-{trade_id}", "completed"))
    db.commit()
    return jsonify({"ok": True, "trade_id": trade_id, "entry_price": entry,
                    "settles_in": duration})


@app.post("/api/trade/<int:trade_id>/settle")
@login_required
def api_trade_settle(trade_id):
    user = current_user()
    db = get_db()
    t = db.execute("SELECT * FROM trades WHERE id = ? AND user_id = ?",
                   (trade_id, user["id"])).fetchone()
    if not t:
        return jsonify({"error": "Trade not found"}), 404
    if t["result"] != "pending":
        return jsonify({"ok": True, "already": True, "trade": dict(t)})
    exit_price = tick_price(t["symbol"])
    won = (exit_price > t["entry_price"]) if t["direction"] == "rise" else (exit_price < t["entry_price"])
    payout = round(t["stake"] * 1.85, 2) if won else 0.0
    result = "win" if won else "lose"
    if won:
        db.execute("UPDATE trading_accounts SET balance = balance + ? WHERE id = ?",
                   (payout, t["account_id"]))
        db.execute("""INSERT INTO transactions
            (user_id, account_id, type, amount, method, reference, status)
            VALUES (?,?,?,?,?,?,?)""",
            (user["id"], t["account_id"], "trade", payout, "internal",
             f"PAYOUT-{trade_id}", "completed"))
    db.execute("""UPDATE trades SET exit_price=?, payout=?, result=?, settled_at=CURRENT_TIMESTAMP
        WHERE id = ?""", (exit_price, payout, result, trade_id))
    db.commit()
    t = db.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    return jsonify({"ok": True, "trade": dict(t)})


# ---------- Bootstrap ----------
@app.cli.command("init-db")
def init_db_cmd():
    init_db()
    print("DB initialized at", DB_PATH)


with app.app_context():
    init_db()

