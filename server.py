#!/usr/bin/env python3
"""
SoundCloud Hub — Mass SoundCloud account management server.
Uses only pre-installed packages: tornado, cryptography.
Run: python3 server.py
Dashboard: http://localhost:8000
"""

import os, sys, json, uuid, sqlite3, hashlib, base64, time, random
import logging, asyncio, threading, secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import wraps

import tornado.ioloop
import tornado.web
import tornado.httpserver
from cryptography.fernet import Fernet

# ── Configuration ────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
RUNTIME_DIR = Path(os.environ.get("RUNTIME_DIR", "/tmp/socialhub"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = RUNTIME_DIR / "socialhub.db"
COOKIE_DIR = RUNTIME_DIR / "cookies"
STATIC_DIR = BASE_DIR / "dashboard"
PORT = int(os.environ.get("PORT", 8000))

ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "socialhub-encryption-key-32bytes!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("soundcloudhub")

# ── Encryption ───────────────────────────────────────────────────────────────

def _get_fernet():
    key = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_credential(plaintext):
    return _get_fernet().encrypt(plaintext.encode()).decode()

def decrypt_credential(ciphertext):
    return _get_fernet().decrypt(ciphertext.encode()).decode()

# ── Database ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS proxies (
        id TEXT PRIMARY KEY,
        protocol TEXT NOT NULL DEFAULT 'http' CHECK(protocol IN ('http','https','socks4','socks5')),
        host TEXT NOT NULL,
        port INTEGER NOT NULL,
        username TEXT,
        password TEXT,
        label TEXT,
        status TEXT DEFAULT 'active' CHECK(status IN ('active','dead','slow','banned')),
        last_checked TEXT,
        response_time_ms INTEGER,
        country TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        encrypted_password TEXT NOT NULL,
        username TEXT,
        display_name TEXT,
        avatar_url TEXT,
        bio TEXT,
        profile_url TEXT,
        city TEXT,
        country TEXT,
        status TEXT DEFAULT 'active' CHECK(status IN ('active','paused','suspended','needs_reauth','disabled','banned','logged_in')),
        login_status TEXT DEFAULT 'not_logged_in' CHECK(login_status IN ('not_logged_in','logging_in','logged_in','failed')),
        proxy_id TEXT REFERENCES proxies(id) ON DELETE SET NULL,
        rate_limit_config TEXT DEFAULT '{"actions_per_hour":30}',
        metadata TEXT DEFAULT '{}',
        follower_count INTEGER DEFAULT 0,
        following_count INTEGER DEFAULT 0,
        track_count INTEGER DEFAULT 0,
        playlist_count INTEGER DEFAULT 0,
        repost_count INTEGER DEFAULT 0,
        likes_count INTEGER DEFAULT 0,
        is_verified INTEGER DEFAULT 0,
        is_pro INTEGER DEFAULT 0,
        cookie_file TEXT,
        last_active_at TEXT,
        last_health_check TEXT,
        last_login_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS campaigns (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'draft' CHECK(status IN ('draft','active','paused','completed','archived')),
        tags TEXT DEFAULT '[]',
        start_date TEXT,
        end_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        campaign_id TEXT REFERENCES campaigns(id) ON DELETE SET NULL,
        post_type TEXT NOT NULL DEFAULT 'audio' CHECK(post_type IN ('audio','repost','playlist_add','comment')),
        status TEXT DEFAULT 'draft' CHECK(status IN ('draft','scheduled','queued','publishing','published','failed','cancelled')),
        content_text TEXT,
        content_metadata TEXT DEFAULT '{}',
        platform_post_id TEXT,
        platform_post_url TEXT,
        scheduled_at TEXT,
        published_at TEXT,
        error_message TEXT,
        likes_count INTEGER DEFAULT 0,
        comments_count INTEGER DEFAULT 0,
        reposts_count INTEGER DEFAULT 0,
        plays_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );

    -- Track uploads (audio files to be uploaded to SoundCloud)
    CREATE TABLE IF NOT EXISTS uploads (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        track_title TEXT NOT NULL,
        track_description TEXT,
        tags TEXT DEFAULT '[]',
        genre TEXT,
        audio_filename TEXT NOT NULL,
        audio_path TEXT NOT NULL,
        audio_size INTEGER DEFAULT 0,
        artwork_filename TEXT,
        artwork_path TEXT,
        use_account_avatar INTEGER DEFAULT 1,
        privacy TEXT DEFAULT 'public' CHECK(privacy IN ('public','private')),
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','uploading','uploaded','failed','scheduled')),
        scheduled_at TEXT,
        platform_track_id TEXT,
        platform_track_url TEXT,
        error_message TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    -- Task groups track bulk operations with progress
    CREATE TABLE IF NOT EXISTS task_groups (
        id TEXT PRIMARY KEY,
        action_type TEXT NOT NULL,
        target_url TEXT,
        comment_text TEXT,
        total_tasks INTEGER NOT NULL DEFAULT 0,
        completed_tasks INTEGER NOT NULL DEFAULT 0,
        failed_tasks INTEGER NOT NULL DEFAULT 0,
        status TEXT DEFAULT 'running' CHECK(status IN ('running','completed','failed','cancelled')),
        created_at TEXT DEFAULT (datetime('now')),
        completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS engagement_actions (
        id TEXT PRIMARY KEY,
        task_group_id TEXT REFERENCES task_groups(id) ON DELETE SET NULL,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        action_type TEXT NOT NULL CHECK(action_type IN ('like','unlike','repost','unrepost','comment','follow','unfollow','play','save','add_to_playlist')),
        target_url TEXT,
        target_id TEXT,
        comment_text TEXT,
        playlist_id TEXT,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','running','completed','failed')),
        scheduled_at TEXT,
        executed_at TEXT,
        error_message TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
        id TEXT PRIMARY KEY,
        account_id TEXT,
        action TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'success',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now'))
    );

    -- Engagement stats: cumulative per-account action counters
    CREATE TABLE IF NOT EXISTS engagement_stats (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        action_type TEXT NOT NULL,
        total_completed INTEGER DEFAULT 0,
        total_failed INTEGER DEFAULT 0,
        last_executed TEXT,
        UNIQUE(account_id, action_type)
    );

    CREATE INDEX IF NOT EXISTS idx_accounts_org ON accounts(organization_id);
    CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
    CREATE INDEX IF NOT EXISTS idx_accounts_proxy ON accounts(proxy_id);
    CREATE INDEX IF NOT EXISTS idx_proxies_status ON proxies(status);
    CREATE INDEX IF NOT EXISTS idx_posts_account ON posts(account_id);
    CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
    CREATE INDEX IF NOT EXISTS idx_engagement_account ON engagement_actions(account_id);
    CREATE INDEX IF NOT EXISTS idx_engagement_status ON engagement_actions(status);
    CREATE INDEX IF NOT EXISTS idx_engagement_group ON engagement_actions(task_group_id);
    CREATE INDEX IF NOT EXISTS idx_task_groups_status ON task_groups(status);
    """)

    existing = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO organizations (id, name, slug, description) VALUES (?, ?, ?, ?)",
            ("00000000-0000-0000-0000-000000000001", "1BStar Agency", "1bstar", "1BStar Artist Management"),
        )
    conn.commit()
    conn.close()
    logger.info(f"Database ready at {DB_PATH}")


def seed_real_accounts():
    """Seed the 45 real SoundCloud accounts on first startup. No fake data."""
    conn = get_db()
    if conn.execute("SELECT COUNT(*) as c FROM accounts").fetchone()["c"] > 0:
        conn.close()
        return

    org_id = "00000000-0000-0000-0000-000000000001"

    # 45 real accounts — all share the same password
    real_accounts = [
        "boypig@nekosan.uk",
        "nowlruboat@nekosan.uk",
        "ndenpigoak@instaddr.uk",
        "ntee472@nekosan.uk",
        "nas520@meruado.uk",
        "nhopnunsix@meruado.uk",
        "npiekeyoar@nekosan.uk",
        "nmetinbed@nekosan.uk",
        "npaycophot@nekosan.uk",
        "nnidgo922@nekosan.uk",
        "nbinhitway@meruado.uk",
        "npeptagwet@instaddr.uk",
        "nragagonow@nekosan.uk",
        "nfunkit256@meruado.uk",
        "nebbdid829@meruado.uk",
        "nbogear297@instaddr.uk",
        "ntoopen928@meruado.uk",
        "npetair819@meruado.uk",
        "nlaypar798@meruado.uk",
        "nsiprig264@instaddr.uk",
        "nfadoh4@meruado.uk",
        "nhue770@instaddr.uk",
        "ngummeage@instaddr.uk",
        "nryecabthe@nekosan.uk",
        "nladbeown@instaddr.uk",
        "nfeefix738@meruado.uk",
        "ndiginkpro@instaddr.uk",
        "nhogkin523@instaddr.uk",
        "npawbograg@nekosan.uk",
        "ntomopicy@instaddr.uk",
        "nfoxaretry@instaddr.uk",
        "nhuecon293@nekosan.uk",
        "nantnipit@nekosan.uk",
        "nputfat906@instaddr.uk",
        "nfitbypie@meruado.uk",
        "ndr360@meruado.uk",
        "nmarallfax@nekosan.uk",
        "ngumdew76@meruado.uk",
        "nviaeggant@instaddr.uk",
        "nmaymixtry@meruado.uk",
        "ncanicejoy@instaddr.uk",
        "ngodasherr@nekosan.uk",
        "nsowdigtry@nekosan.uk",
        "nivytarman@instaddr.uk",
        "nfeeaimpot@nekosan.uk",
    ]
    password = "@1.Q2.w3.e"

    for email in real_accounts:
        aid = str(uuid.uuid4())
        cookie_file = f"{COOKIE_DIR}/{aid}.json"
        conn.execute(
            """INSERT INTO accounts
               (id, organization_id, email, encrypted_password,
                status, login_status, cookie_file)
               VALUES (?,?,?,?,?,?,?)""",
            (aid, org_id, email, encrypt_credential(password),
             "active", "not_logged_in", cookie_file),
        )

    conn.commit()
    conn.close()
    logger.info(f"Seeded {len(real_accounts)} real accounts — no fake data")


# ── JSON helpers ─────────────────────────────────────────────────────────────

def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for key in ("rate_limit_config", "metadata", "tags", "content_metadata"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d

def rows_to_list(rows):
    return [row_to_dict(r) for r in rows]


# ── Base Handler ─────────────────────────────────────────────────────────────

class APIHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()

    def get_json_body(self):
        try:
            return json.loads(self.request.body)
        except Exception:
            return {}

    def write_json(self, data, status=200):
        self.set_status(status)
        self.write(json.dumps(data, default=str))

    def write_error(self, status_code, **kwargs):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"detail": self._reason or "Error", "status": status_code}))


# ── Proxy Endpoints ──────────────────────────────────────────────────────────

class ProxiesHandler(APIHandler):
    def get(self):
        db = get_db()
        status_filter = self.get_argument("status", None)
        q = "SELECT * FROM proxies"
        params = []
        if status_filter:
            q += " WHERE status = ?"
            params.append(status_filter)
        q += " ORDER BY created_at DESC"
        rows = db.execute(q, params).fetchall()
        result = []
        for r in rows:
            d = row_to_dict(r)
            d["accounts_using"] = db.execute("SELECT COUNT(*) as c FROM accounts WHERE proxy_id = ?", (d["id"],)).fetchone()["c"]
            result.append(d)
        db.close()
        self.write_json(result)

    def post(self):
        data = self.get_json_body()
        db = get_db()
        added = []
        lines = data.get("proxies_text", "").strip().split("\n") if data.get("proxies_text") else []
        if lines:
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                proxy = _parse_proxy_line(line)
                if proxy:
                    pid = str(uuid.uuid4())
                    db.execute(
                        "INSERT INTO proxies (id, protocol, host, port, username, password, label) VALUES (?,?,?,?,?,?,?)",
                        (pid, proxy["protocol"], proxy["host"], proxy["port"],
                         proxy.get("username"), proxy.get("password"), line[:60]),
                    )
                    added.append(pid)
        else:
            pid = str(uuid.uuid4())
            db.execute(
                "INSERT INTO proxies (id, protocol, host, port, username, password, label, country) VALUES (?,?,?,?,?,?,?,?)",
                (pid, data.get("protocol", "http"), data["host"], int(data["port"]),
                 data.get("username"), data.get("password"), data.get("label"), data.get("country")),
            )
            added.append(pid)
        db.commit()
        db.close()
        self.write_json({"added": len(added), "proxy_ids": added}, 201)


def _parse_proxy_line(line):
    try:
        protocol = "http"
        username = password = None
        if "://" in line:
            protocol, rest = line.split("://", 1)
            protocol = protocol.lower()
        else:
            rest = line
        if "@" in rest:
            auth, hostport = rest.rsplit("@", 1)
            if ":" in auth:
                username, password = auth.split(":", 1)
            parts = hostport.split(":")
            host, port = parts[0], int(parts[1])
        else:
            parts = rest.split(":")
            if len(parts) == 2:
                host, port = parts[0], int(parts[1])
            elif len(parts) == 4:
                host, port = parts[0], int(parts[1])
                username, password = parts[2], parts[3]
            else:
                return None
        return {"protocol": protocol, "host": host, "port": port, "username": username, "password": password}
    except Exception:
        return None


class ProxyDetailHandler(APIHandler):
    def get(self, pid):
        db = get_db()
        row = db.execute("SELECT * FROM proxies WHERE id = ?", (pid,)).fetchone()
        db.close()
        if not row:
            return self.write_json({"detail": "Not found"}, 404)
        self.write_json(row_to_dict(row))

    def patch(self, pid):
        data = self.get_json_body()
        db = get_db()
        sets, params = [], []
        for f in ("protocol", "host", "port", "username", "password", "label", "status", "country"):
            if f in data:
                sets.append(f"{f} = ?")
                params.append(data[f])
        if not sets:
            return self.write_json({"detail": "Nothing to update"}, 400)
        params.append(pid)
        db.execute(f"UPDATE proxies SET {', '.join(sets)} WHERE id = ?", params)
        db.commit()
        row = db.execute("SELECT * FROM proxies WHERE id = ?", (pid,)).fetchone()
        db.close()
        self.write_json(row_to_dict(row))

    def delete(self, pid):
        db = get_db()
        db.execute("UPDATE accounts SET proxy_id = NULL WHERE proxy_id = ?", (pid,))
        db.execute("DELETE FROM proxies WHERE id = ?", (pid,))
        db.commit()
        db.close()
        self.set_status(204)
        self.finish()


class ProxyRandomizeHandler(APIHandler):
    def post(self):
        data = self.get_json_body()
        db = get_db()
        proxies = db.execute("SELECT id FROM proxies WHERE status = 'active'").fetchall()
        if not proxies:
            db.close()
            return self.write_json({"detail": "No active proxies"}, 400)
        proxy_ids = [p["id"] for p in proxies]
        account_ids = data.get("account_ids")
        if account_ids:
            accounts = db.execute(f"SELECT id FROM accounts WHERE id IN ({','.join('?'*len(account_ids))})", account_ids).fetchall()
        else:
            accounts = db.execute("SELECT id FROM accounts").fetchall()
        for acc in accounts:
            db.execute("UPDATE accounts SET proxy_id = ? WHERE id = ?", (random.choice(proxy_ids), acc["id"]))
        db.commit()
        db.close()
        self.write_json({"assigned": len(accounts), "proxy_count": len(proxy_ids),
                         "message": f"Randomly assigned {len(proxy_ids)} proxies across {len(accounts)} accounts"})


class ProxyClearHandler(APIHandler):
    def post(self):
        db = get_db()
        db.execute("UPDATE accounts SET proxy_id = NULL")
        db.commit()
        db.close()
        self.write_json({"message": "Cleared"})


# ── Account Endpoints ────────────────────────────────────────────────────────

class AccountsHandler(APIHandler):
    def get(self):
        db = get_db()
        q = """SELECT a.*, p.host as proxy_host, p.port as proxy_port, p.protocol as proxy_protocol
               FROM accounts a LEFT JOIN proxies p ON a.proxy_id = p.id WHERE 1=1"""
        params = []
        status = self.get_argument("status", None)
        if status:
            q += " AND a.status = ?"
            params.append(status)
        q += " ORDER BY a.follower_count DESC LIMIT 500"
        rows = db.execute(q, params).fetchall()
        db.close()
        self.write_json(rows_to_list(rows))

    def post(self):
        data = self.get_json_body()
        db = get_db()
        org_id = data.get("organization_id", "00000000-0000-0000-0000-000000000001")
        added = []
        lines = data.get("accounts_text", "").strip().split("\n") if data.get("accounts_text") else []

        if lines:
            proxies = db.execute("SELECT id FROM proxies WHERE status = 'active'").fetchall()
            proxy_ids = [p["id"] for p in proxies] if proxies else []
            for line in lines:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                email, password = line.split(":", 1)
                email, password = email.strip(), password.strip()
                if not email or not password:
                    continue
                aid = str(uuid.uuid4())
                proxy_id = random.choice(proxy_ids) if proxy_ids else None
                conn_cookie = f"{COOKIE_DIR}/{aid}.json"
                db.execute(
                    """INSERT INTO accounts (id, organization_id, email, encrypted_password,
                       username, proxy_id, cookie_file, status) VALUES (?,?,?,?,?,?,?,'active')""",
                    (aid, org_id, email, encrypt_credential(password),
                     email.split("@")[0], proxy_id, conn_cookie),
                )
                added.append(aid)
        else:
            email = data.get("email", "")
            password = data.get("password", "")
            if not email or not password:
                db.close()
                return self.write_json({"detail": "email and password required"}, 400)
            aid = str(uuid.uuid4())
            proxy_id = data.get("proxy_id")
            if not proxy_id and data.get("auto_proxy"):
                p = db.execute("SELECT id FROM proxies WHERE status='active' ORDER BY RANDOM() LIMIT 1").fetchone()
                proxy_id = p["id"] if p else None
            cookie_file = f"{COOKIE_DIR}/{aid}.json"
            db.execute(
                """INSERT INTO accounts (id, organization_id, email, encrypted_password,
                   username, display_name, proxy_id, cookie_file, status) VALUES (?,?,?,?,?,?,?,?,'active')""",
                (aid, org_id, email, encrypt_credential(password),
                 data.get("username", email.split("@")[0]), data.get("display_name"),
                 proxy_id, cookie_file),
            )
            added.append(aid)
        db.commit()

        if len(added) == 1:
            row = db.execute("SELECT a.*, p.host as proxy_host, p.port as proxy_port, p.protocol as proxy_protocol FROM accounts a LEFT JOIN proxies p ON a.proxy_id = p.id WHERE a.id = ?", (added[0],)).fetchone()
            db.close()
            self.write_json(row_to_dict(row), 201)
        else:
            db.close()
            self.write_json({"added": len(added), "account_ids": added}, 201)


class AccountDetailHandler(APIHandler):
    def get(self, aid):
        db = get_db()
        row = db.execute("SELECT a.*, p.host as proxy_host, p.port as proxy_port, p.protocol as proxy_protocol FROM accounts a LEFT JOIN proxies p ON a.proxy_id = p.id WHERE a.id = ?", (aid,)).fetchone()
        if not row:
            db.close()
            return self.write_json({"detail": "Not found"}, 404)
        d = row_to_dict(row)
        # Include engagement stats
        stats = db.execute("SELECT action_type, total_completed, total_failed FROM engagement_stats WHERE account_id = ?", (aid,)).fetchall()
        d["engagement_stats"] = {s["action_type"]: {"completed": s["total_completed"], "failed": s["total_failed"]} for s in stats}
        db.close()
        self.write_json(d)

    def patch(self, aid):
        data = self.get_json_body()
        db = get_db()
        sets, params = [], []
        for f in ("username", "display_name", "status", "bio", "proxy_id", "login_status",
                   "follower_count", "following_count", "track_count", "playlist_count",
                   "repost_count", "likes_count", "profile_url", "city", "country"):
            if f in data:
                sets.append(f"{f} = ?")
                params.append(data[f])
        if "password" in data:
            sets.append("encrypted_password = ?")
            params.append(encrypt_credential(data["password"]))
        if not sets:
            return self.write_json({"detail": "Nothing"}, 400)
        params.append(aid)
        db.execute(f"UPDATE accounts SET {', '.join(sets)} WHERE id = ?", params)
        db.commit()
        row = db.execute("SELECT * FROM accounts WHERE id = ?", (aid,)).fetchone()
        db.close()
        self.write_json(row_to_dict(row))

    def delete(self, aid):
        db = get_db()
        db.execute("DELETE FROM accounts WHERE id = ?", (aid,))
        db.commit()
        db.close()
        self.set_status(204)
        self.finish()


class AccountHealthCheckHandler(APIHandler):
    """POST /api/v1/accounts/<id>/health-check — refresh profile stats for one account."""
    def post(self, aid):
        db = get_db()
        row = db.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
        if not row:
            db.close()
            return self.write_json({"detail": "Not found"}, 404)
        acc = row_to_dict(row)
        db.close()
        meta = json.loads(acc.get("metadata") or "{}")
        oauth_token = meta.get("oauth_token")
        _login_executor.submit(_run_refresh, aid, acc["cookie_file"], oauth_token)
        self.write_json({"account_id": aid, "status": "refresh_queued"})


class HealthCheckAllHandler(APIHandler):
    """POST /api/v1/accounts/health-check/all — refresh all logged-in accounts."""
    def post(self):
        db = get_db()
        accounts = db.execute(
            "SELECT id, cookie_file, metadata FROM accounts "
            "WHERE login_status IN ('logged_in', 'failed', 'not_logged_in') AND status != 'disabled'"
        ).fetchall()
        queued = 0
        for acc in accounts:
            meta = json.loads(acc["metadata"] or "{}")
            oauth_token = meta.get("oauth_token")
            _login_executor.submit(_run_refresh, acc["id"], acc["cookie_file"], oauth_token)
            queued += 1
        db.close()
        self.write_json({"queued": queued, "message": f"Profile refresh queued for {queued} accounts"})


# ── SoundCloud Login (Playwright) ────────────────────────────────────────────

import concurrent.futures as _futures
_login_executor = _futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="sc-login")

async def _playwright_sc_login(email, password, cookie_file):
    """Headless Chromium login to SoundCloud. Returns dict {success, cookies, error}."""
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                "--disable-setuid-sandbox", "--single-process",
                "--disable-extensions", "--disable-background-networking",
            ],
        )
        try:
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            await ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                "window.chrome={runtime:{}};"
            )
            page = await ctx.new_page()

            await page.goto("https://soundcloud.com/signin", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Step 1: fill email
            email_sel = 'input[type="email"], input[name="email"], input[autocomplete="email"]'
            try:
                await page.wait_for_selector(email_sel, timeout=8000)
                await page.fill(email_sel, email)
            except PWTimeout:
                pass  # may already be on combined form

            # Click Continue / Next
            for btn_sel in [
                'button[type="submit"]',
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'button:has-text("Sign in")',
            ]:
                try:
                    btn = page.locator(btn_sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        await page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass

            # Step 2: fill password
            pwd_sel = 'input[type="password"], input[name="password"], input[autocomplete="current-password"]'
            await page.wait_for_selector(pwd_sel, timeout=10000)
            await page.fill(pwd_sel, password)

            # Submit
            for btn_sel in [
                'button[type="submit"]',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'input[type="submit"]',
            ]:
                try:
                    btn = page.locator(btn_sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        break
                except Exception:
                    pass

            # Wait for redirect away from auth pages
            await page.wait_for_function(
                "!window.location.href.includes('/signin') && "
                "!window.location.href.includes('/login') && "
                "!window.location.href.includes('auth0') && "
                "window.location.href !== 'about:blank'",
                timeout=20000,
            )

            cookies = await ctx.cookies()
            Path(cookie_file).parent.mkdir(parents=True, exist_ok=True)
            with open(cookie_file, "w") as f:
                json.dump(cookies, f)

            # ── Scrape profile data from authenticated session ──────────────
            profile = None
            oauth_token = None
            try:
                await page.goto("https://soundcloud.com/me", timeout=15000)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                result_data = await page.evaluate("""() => {
                    const h = window.__sc_hydration;
                    const me = h ? h.find(e => e.hydratable === 'me')?.data : null;
                    // Try to extract OAuth token from cookies or localStorage
                    const token = (
                        document.cookie.match(/oauth_token=([^;]+)/)?.[1] ||
                        localStorage.getItem('oauth_token') ||
                        localStorage.getItem('sc:access_token') ||
                        localStorage.getItem('sc_access_token') ||
                        null
                    );
                    return { profile: me, token };
                }""")
                profile = result_data.get("profile") if result_data else None
                oauth_token = result_data.get("token") if result_data else None
            except Exception as pe:
                logging.warning(f"[login] profile scrape failed: {pe}")

            await ctx.close()
            return {"success": True, "cookies": len(cookies), "profile": profile, "oauth_token": oauth_token}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        finally:
            await browser.close()


def _run_login(account_id, email, password, cookie_file):
    """Thread worker — runs async Playwright login and writes result to DB."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_playwright_sc_login(email, password, cookie_file))
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    finally:
        loop.close()

    db = get_db()
    if result.get("success"):
        p = result.get("profile") or {}
        # SoundCloud API fields: permalink=URL slug, username=display name
        username     = p.get("permalink")          # e.g. "john-doe"
        display_name = p.get("username")           # e.g. "John Doe"
        avatar_url   = p.get("avatar_url") or ""
        if avatar_url and "-large." in avatar_url:
            avatar_url = avatar_url.replace("-large.", "-t500x500.")  # get bigger image
        bio          = p.get("description")
        profile_url  = p.get("permalink_url")
        city         = p.get("city")
        followers    = p.get("followers_count")
        following    = p.get("followings_count")
        track_count  = p.get("track_count")
        reposts      = p.get("reposts_count")
        likes        = p.get("likes_count")
        is_verified  = 1 if p.get("verified") else 0
        # Store oauth_token in metadata JSON for lightweight API calls later
        oauth_token  = result.get("oauth_token")
           meta = {"oauth_token": oauth_token} if oauth_token else {}

        db.execute(
            """UPDATE accounts SET
               login_status   = 'logged_in',
               last_login_at  = ?,
               username       = COALESCE(?, username),
               display_name   = COALESCE(?, display_name),
               avatar_url     = COALESCE(NULLIF(?,  ''), avatar_url),
               bio            = COALESCE(?, bio),
               profile_url    = COALESCE(?, profile_url),
               city           = COALESCE(?, city),
               follower_count = COALESCE(?, follower_count),
               following_count= COALESCE(?, following_count),
               track_count    = COALESCE(?, track_count),
               repost_count   = COALESCE(?, repost_count),
               likes_count    = COALESCE(?, likes_count),
               is_verified    = ?,
               metadata       = json_patch(COALESCE(metadata,'{}'), ?)
             WHERE id = ?""",
            (
                datetime.now(timezone.utc).isoformat(),
                username, display_name, avatar_url, bio, profile_url, city,
                followers, following, track_count, reposts, likes,
                is_verified, json.dumps(meta),
                account_id,
            ),
        )
        logging.info(
            f"[login] {account_id} OK  @{username or '?'}  "
            f"followers:{followers or 0}  tracks:{track_count or 0}"
        )
    else:
        db.execute("UPDATE accounts SET login_status='failed' WHERE id=?", (account_id,))
        logging.warning(f"[login] {account_id} FAILED: {result.get('error')}")
    db.commit()
    db.close()
    return result


async def _playwright_sc_refresh(account_id, cookie_file, oauth_token=None):
    """
    Refresh profile data for an already-logged-in account.
    1. If we have an oauth_token, use the lightweight REST API (no browser needed).
    2. Otherwise, load saved cookies in headless Chromium and navigate to /me.
    Returns dict {success, profile, session_valid, error}.
    """
    import urllib.request, urllib.error

    # ── Fast path: OAuth token REST call ─────────────────────────────────────
    if oauth_token:
        try:
            req = urllib.request.Request(
                "https://api.soundcloud.com/me",
                headers={
                    "Authorization": f"OAuth {oauth_token}",
                    "Accept": "application/json; charset=utf-8",
                    "User-Agent": "Mozilla/5.0",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            return {"success": True, "profile": data, "session_valid": True}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                # Token expired — fall through to Playwright
                logging.info(f"[refresh] {account_id} token expired, trying cookies")
            else:
                return {"success": False, "error": f"HTTP {e.code}", "session_valid": False}
        except Exception as e:
            logging.warning(f"[refresh] {account_id} API error: {e}")

    # ── Slow path: Playwright with saved cookies ──────────────────────────────
    if not Path(cookie_file).exists():
        return {"success": False, "error": "no_cookie_file", "session_valid": False}

    try:
        cookies = json.loads(Path(cookie_file).read_text())
    except Exception:
        return {"success": False, "error": "bad_cookie_file", "session_valid": False}

    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-setuid-sandbox", "--single-process"],
        )
        try:
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            await ctx.add_cookies(cookies)
            await ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )
            page = await ctx.new_page()
            await page.goto("https://soundcloud.com/me", timeout=20000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)

            current_url = page.url
            if "signin" in current_url or "login" in current_url:
                return {"success": False, "error": "session_expired", "session_valid": False}

            result_data = await page.evaluate("""() => {
                const h = window.__sc_hydration;
                const me = h ? h.find(e => e.hydratable === 'me')?.data : null;
                const token = (
                    document.cookie.match(/oauth_token=([^;]+)/)?.[1] ||
                    localStorage.getItem('oauth_token') ||
                    localStorage.getItem('sc:access_token') ||
                    null
                );
                return { profile: me, token };
            }""")
            profile    = result_data.get("profile") if result_data else None
            new_token  = result_data.get("token")   if result_data else None
            if not profile:
                return {"success": False, "error": "no_profile_data", "session_valid": True}
            return {"success": True, "profile": profile, "session_valid": True,
                    "new_token": new_token}
        except Exception as exc:
            return {"success": False, "error": str(exc), "session_valid": False}
        finally:
            await browser.close()


def _run_refresh(account_id, cookie_file, oauth_token=None):
    """Thread worker — refresh profile stats for one account."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _playwright_sc_refresh(account_id, cookie_file, oauth_token)
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc), "session_valid": False}
    finally:
        loop.close()

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    if result.get("success"):
        p = result.get("profile") or {}
        avatar_url = p.get("avatar_url") or ""
        if avatar_url and "-large." in avatar_url:
            avatar_url = avatar_url.replace("-large.", "-t500x500.")
        meta_patch = {}
        if result.get("new_token"):
            meta_patch["oauth_token"] = result["new_token"]
        db.execute(
            """UPDATE accounts SET
               last_health_check = ?,
               username          = COALESCE(?, username),
               display_name      = COALESCE(?, display_name),
               avatar_url        = COALESCE(NULLIF(?, ''), avatar_url),
               bio               = COALESCE(?, bio),
               profile_url       = COALESCE(?, profile_url),
               city              = COALESCE(?, city),
               follower_count    = COALESCE(?, follower_count),
               following_count   = COALESCE(?, following_count),
               track_count       = COALESCE(?, track_count),
               repost_count      = COALESCE(?, repost_count),
               likes_count       = COALESCE(?, likes_count),
               is_verified       = ?,
               metadata          = CASE WHEN ? != '{}' THEN json_patch(COALESCE(metadata,'{}'), ?) ELSE COALESCE(metadata,'{}') END
             WHERE id = ?""",
            (
                now,
                p.get("permalink"), p.get("username"),
                avatar_url, p.get("description"), p.get("permalink_url"),
                p.get("city"),
                p.get("followers_count"), p.get("followings_count"),
                p.get("track_count"), p.get("reposts_count"),
                p.get("likes_count"),
                1 if p.get("verified") else 0,
                json.dumps(meta_patch), json.dumps(meta_patch),
                account_id,
            ),
        )
        logging.info(
            f"[refresh] {account_id} OK  @{p.get('permalink','?')}  "
            f"followers:{p.get('followers_count', 0)}"
        )
    else:
        # Session expired — mark for re-auth
        if not result.get("session_valid"):
            db.execute(
                "UPDATE accounts SET login_status='failed', status='needs_reauth', "
                "last_health_check=? WHERE id=?",
                (now, account_id),
            )
            logging.warning(f"[refresh] {account_id} session expired → needs_reauth")
        else:
            db.execute(
                "UPDATE accounts SET last_health_check=? WHERE id=?",
                (now, account_id),
            )
            logging.warning(f"[refresh] {account_id} refresh error: {result.get('error')}")

    db.commit()
    db.close()
    return result


class AccountLoginHandler(APIHandler):
    """POST /api/v1/accounts/<id>/login — background login for one account."""
    def post(self, aid):
        db = get_db()
        row = db.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
        if not row:
            db.close()
            return self.write_json({"detail": "Not found"}, 404)
        acc = row_to_dict(row)
        try:
            password = decrypt_credential(acc["encrypted_password"])
        except Exception as exc:
            db.close()
            return self.write_json({"detail": f"Decrypt error: {exc}"}, 500)
        db.execute("UPDATE accounts SET login_status='logging_in' WHERE id=?", (aid,))
        db.commit()
        db.close()
        _login_executor.submit(_run_login, aid, acc["email"], password, acc["cookie_file"])
        self.write_json({"account_id": aid, "status": "logging_in", "message": "Login started"})


class BulkLoginHandler(APIHandler):
    """POST /api/v1/accounts/login/bulk — queue login for every active account."""
    def post(self):
        db = get_db()
        accounts = db.execute(
            "SELECT id, email, encrypted_password, cookie_file FROM accounts WHERE status='active'"
        ).fetchall()
        queued = 0
        for row in accounts:
            acc = row_to_dict(row)
            try:
                password = decrypt_credential(acc["encrypted_password"])
            except Exception:
                continue
            db.execute("UPDATE accounts SET login_status='logging_in' WHERE id=?", (acc["id"],))
            _login_executor.submit(_run_login, acc["id"], acc["email"], password, acc["cookie_file"])
            queued += 1
        db.commit()
        db.close()
        self.write_json({"queued": queued, "message": f"Login queued for {queued} accounts (3 at a time)"})


# ── Campaign Endpoints ───────────────────────────────────────────────────────

class CampaignsHandler(APIHandler):
    def get(self):
        db = get_db()
        rows = db.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        db.close()
        self.write_json(rows_to_list(rows))

    def post(self):
        data = self.get_json_body()
        db = get_db()
        cid = str(uuid.uuid4())
        db.execute("INSERT INTO campaigns (id, organization_id, name, description, status, tags) VALUES (?,?,?,?,?,?)",
            (cid, data.get("organization_id", "00000000-0000-0000-0000-000000000001"),
             data["name"], data.get("description"), data.get("status", "draft"), json.dumps(data.get("tags", []))))
        db.commit()
        row = db.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
        db.close()
        self.write_json(row_to_dict(row), 201)


class CampaignDetailHandler(APIHandler):
    def patch(self, cid):
        data = self.get_json_body()
        db = get_db()
        sets, params = [], []
        for f in ("name", "description", "status"):
            if f in data:
                sets.append(f"{f} = ?")
                params.append(data[f])
        sets.append("updated_at = datetime('now')")
        params.append(cid)
        db.execute(f"UPDATE campaigns SET {', '.join(sets)} WHERE id = ?", params)
        db.commit()
        row = db.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
        db.close()
        self.write_json(row_to_dict(row))

    def delete(self, cid):
        db = get_db()
        db.execute("DELETE FROM campaigns WHERE id = ?", (cid,))
        db.commit()
        db.close()
        self.set_status(204)
        self.finish()


# ── Post Endpoints ───────────────────────────────────────────────────────────

class PostsHandler(APIHandler):
    def get(self):
        db = get_db()
        q = "SELECT * FROM posts WHERE 1=1"
        params = []
        for f in ("account_id", "campaign_id", "status"):
            v = self.get_argument(f, None)
            if v:
                q += f" AND {f} = ?"
                params.append(v)
        q += " ORDER BY COALESCE(scheduled_at, created_at) DESC LIMIT 100"
        rows = db.execute(q, params).fetchall()
        db.close()
        self.write_json(rows_to_list(rows))

    def post(self):
        data = self.get_json_body()
        db = get_db()
        pid = str(uuid.uuid4())
        status = "scheduled" if data.get("scheduled_at") else "draft"
        db.execute("INSERT INTO posts (id, account_id, campaign_id, post_type, status, content_text, content_metadata, scheduled_at) VALUES (?,?,?,?,?,?,?,?)",
            (pid, data["account_id"], data.get("campaign_id"), data.get("post_type", "audio"),
             status, data.get("content_text"), json.dumps(data.get("content_metadata", {})), data.get("scheduled_at")))
        db.commit()
        row = db.execute("SELECT * FROM posts WHERE id = ?", (pid,)).fetchone()
        db.close()
        self.write_json(row_to_dict(row), 201)


class PostDetailHandler(APIHandler):
    def delete(self, pid):
        db = get_db()
        db.execute("DELETE FROM posts WHERE id = ?", (pid,))
        db.commit()
        db.close()
        self.set_status(204)
        self.finish()


# ── Upload Endpoints ─────────────────────────────────────────────────────────

UPLOAD_DIR = RUNTIME_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class UploadsHandler(APIHandler):
    """List uploads or create a new upload via multipart form."""
    def get(self):
        db = get_db()
        q = "SELECT u.*, a.email, a.username, a.display_name, a.avatar_url FROM uploads u JOIN accounts a ON u.account_id = a.id"
        params = []
        status = self.get_argument("status", None)
        if status:
            q += " WHERE u.status = ?"
            params.append(status)
        q += " ORDER BY u.created_at DESC LIMIT 100"
        rows = db.execute(q, params).fetchall()
        db.close()
        self.write_json(rows_to_list(rows))

    def post(self):
        # Multipart form upload
        account_id = self.get_argument("account_id", "")
        track_title = self.get_argument("track_title", "")
        track_desc = self.get_argument("track_description", "")
        tags = self.get_argument("tags", "")
        genre = self.get_argument("genre", "")
        privacy = self.get_argument("privacy", "public")
        scheduled_at = self.get_argument("scheduled_at", "")
        use_avatar = self.get_argument("use_account_avatar", "1")

        if not account_id or not track_title:
            return self.write_json({"detail": "account_id and track_title required"}, 400)

        uid = str(uuid.uuid4())
        db = get_db()

        # Save audio file
        audio_file = self.request.files.get("audio_file", [None])[0] if self.request.files.get("audio_file") else None
        if audio_file:
            audio_filename = audio_file["filename"]
            audio_path = str(UPLOAD_DIR / f"{uid}_audio_{audio_filename}")
            with open(audio_path, "wb") as f:
                f.write(audio_file["body"])
            audio_size = len(audio_file["body"])
        else:
            audio_filename = self.get_argument("audio_filename", "pending.mp3")
            audio_path = ""
            audio_size = 0

        # Save artwork file
        artwork_file = self.request.files.get("artwork_file", [None])[0] if self.request.files.get("artwork_file") else None
        artwork_filename = artwork_path = None
        if artwork_file:
            artwork_filename = artwork_file["filename"]
            artwork_path = str(UPLOAD_DIR / f"{uid}_art_{artwork_filename}")
            with open(artwork_path, "wb") as f:
                f.write(artwork_file["body"])

        tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        db.execute(
            """INSERT INTO uploads (id, account_id, track_title, track_description, tags, genre,
               audio_filename, audio_path, audio_size, artwork_filename, artwork_path,
               use_account_avatar, privacy, status, scheduled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (uid, account_id, track_title, track_desc, json.dumps(tags_list), genre,
             audio_filename, audio_path, audio_size, artwork_filename, artwork_path,
             int(use_avatar), privacy, "scheduled" if scheduled_at else "pending",
             scheduled_at if scheduled_at else None),
        )

        db.execute("INSERT INTO activity_logs (id, account_id, action, description, status) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), account_id, "upload.queued",
             f"Upload queued: {track_title}", "queued"))
        db.commit()

        row = db.execute("SELECT * FROM uploads WHERE id = ?", (uid,)).fetchone()
        