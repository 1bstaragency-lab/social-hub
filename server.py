#!/usr/bin/env python3
"""
SoundCloud Hub â€” Mass SoundCloud account management server.
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

# â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

# â”€â”€ Encryption â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _get_fernet():
    key = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_credential(plaintext):
    return _get_fernet().encrypt(plaintext.encode()).decode()

def decrypt_credential(ciphertext):
    return _get_fernet().decrypt(ciphertext.encode()).decode()

# â”€â”€ Database â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    # 45 real accounts â€” all share the same password
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
    logger.info(f"Seeded {len(real_accounts)} real accounts â€” no fake data")


# â”€â”€ JSON helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Base Handler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Proxy Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Account Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    def post(self, aid):
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE accounts SET last_health_check = ? WHERE id = ?", (now, aid))
        db.commit()
        db.close()
        self.write_json({"account_id": aid, "checked": now})


class HealthCheckAllHandler(APIHandler):
    def post(self):
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        accounts = db.execute("SELECT id FROM accounts").fetchall()
        for acc in accounts:
            db.execute("UPDATE accounts SET last_health_check = ? WHERE id = ?", (now, acc["id"]))
        db.commit()
        db.close()
        self.write_json({"message": f"Checked {len(accounts)} accounts"})


# â”€â”€ SoundCloud Login (Playwright) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

            await ctx.close()
            return {"success": True, "cookies": len(cookies)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        finally:
            await browser.close()


def _run_login(account_id, email, password, cookie_file):
    """Thread worker â€” runs async Playwright login and writes result to DB."""
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
        db.execute(
            "UPDATE accounts SET login_status='logged_in', last_login_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), account_id),
        )
        logging.info(f"[login] {account_id} OK ({result.get('cookies', 0)} cookies)")
    else:
        db.execute("UPDATE accounts SET login_status='failed' WHERE id=?", (account_id,))
        logging.warning(f"[login] {account_id} FAILED: {result.get('error')}")
    db.commit()
    db.close()
    return result


class AccountLoginHandler(APIHandler):
    """POST /api/v1/accounts/<id>/login â€” background login for one account."""
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
    """POST /api/v1/accounts/login/bulk â€” queue login for every active account."""
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


# â”€â”€ Campaign Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Post Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Upload Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        db.close()
        logger.info(f"Upload queued: {track_title} for account {account_id}")
        self.write_json(row_to_dict(row), 201)


class UploadDetailHandler(APIHandler):
    def get(self, uid):
        db = get_db()
        row = db.execute("SELECT u.*, a.email, a.username FROM uploads u JOIN accounts a ON u.account_id = a.id WHERE u.id = ?", (uid,)).fetchone()
        db.close()
        if not row:
            return self.write_json({"detail": "Not found"}, 404)
        self.write_json(row_to_dict(row))

    def delete(self, uid):
        db = get_db()
        upload = db.execute("SELECT audio_path, artwork_path FROM uploads WHERE id = ?", (uid,)).fetchone()
        if upload:
            for path in (upload["audio_path"], upload["artwork_path"]):
                if path and os.path.exists(path):
                    os.remove(path)
        db.execute("DELETE FROM uploads WHERE id = ?", (uid,))
        db.commit()
        db.close()
        self.set_status(204)
        self.finish()


# â”€â”€ Task Group / Engagement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TaskGroupsHandler(APIHandler):
    """List all task groups with progress info."""
    def get(self):
        db = get_db()
        status_filter = self.get_argument("status", None)
        q = "SELECT * FROM task_groups"
        params = []
        if status_filter:
            q += " WHERE status = ?"
            params.append(status_filter)
        q += " ORDER BY created_at DESC LIMIT 50"
        rows = db.execute(q, params).fetchall()
        result = []
        for r in rows:
            d = row_to_dict(r)
            d["progress_pct"] = round((d["completed_tasks"] + d["failed_tasks"]) / max(d["total_tasks"], 1) * 100, 1)
            result.append(d)
        db.close()
        self.write_json(result)


class TaskGroupDetailHandler(APIHandler):
    def get(self, gid):
        db = get_db()
        group = db.execute("SELECT * FROM task_groups WHERE id = ?", (gid,)).fetchone()
        if not group:
            db.close()
            return self.write_json({"detail": "Not found"}, 404)
        d = row_to_dict(group)
        tasks = db.execute(
            """SELECT e.*, a.email, a.username FROM engagement_actions e
               JOIN accounts a ON e.account_id = a.id WHERE e.task_group_id = ?
               ORDER BY e.status""", (gid,)
        ).fetchall()
        d["tasks"] = rows_to_list(tasks)
        d["progress_pct"] = round((d["completed_tasks"] + d["failed_tasks"]) / max(d["total_tasks"], 1) * 100, 1)
        db.close()
        self.write_json(d)


class EngagementActionHandler(APIHandler):
    def post(self):
        data = self.get_json_body()
        db = get_db()
        eid = str(uuid.uuid4())
        db.execute(
            """INSERT INTO engagement_actions (id, account_id, action_type, target_url, target_id, comment_text, playlist_id, status) VALUES (?,?,?,?,?,?,?,?)""",
            (eid, data["account_id"], data["action_type"], data.get("target_url"),
             data.get("target_id"), data.get("comment_text"), data.get("playlist_id"), "pending"))
        db.execute("INSERT INTO activity_logs (id, account_id, action, description, status) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), data["account_id"], f"engagement.{data['action_type']}",
             f"{data['action_type']} on {data.get('target_url', 'unknown')}", "queued"))
        db.commit()
        db.close()
        self.write_json({"task_id": eid, "status": "queued"})


class BulkEngagementHandler(APIHandler):
    def post(self):
        data = self.get_json_body()
        db = get_db()
        account_ids = data.get("account_ids", [])

        # Create task group
        gid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO task_groups (id, action_type, target_url, comment_text, total_tasks, status) VALUES (?,?,?,?,?,?)",
            (gid, data["action_type"], data.get("target_url"), data.get("comment_text"), len(account_ids), "running"),
        )

        for acc_id in account_ids:
            eid = str(uuid.uuid4())
            db.execute(
                "INSERT INTO engagement_actions (id, task_group_id, account_id, action_type, target_url, comment_text, status) VALUES (?,?,?,?,?,	Ü[™[™ÉÊH‹ˆ
ZYÚYXØ×ÚY]VÈ˜Xİ[Û—İ\H—K]K™Ù]
\™Ù]İ\›ŠK]K™Ù]
˜ÛÛ[Y[İ^ŠJKˆ
Bˆ‹˜ÛÛ[Z]

Bˆ‹˜ÛÜÙJ
BˆÙ[‹Üš]WÚœÛÛŠÈ\Ú×ÙÜ›İ\ÚYˆÚYœİ]\Èˆœ[›š[™È‹İ[ˆ[ŠXØÛİ[ÚYÊ_JB‚‚˜Û\ÜÈ[™ØYÙ[Y[İ]Ò[™\ŠTR[™\ŠN‚ˆˆˆ‘ÛØ˜[[™ØYÙ[Y[İ]ÈXÜ›ÜÜÈ[XØÛİ[Ëˆˆˆ‚ˆYˆÙ]
Ù[ŠN‚ˆˆHÙ]ÙŠ
Bˆ›İÜÈH‹™^Xİ]Jˆˆ‚ˆÑSPÕXİ[Û—İ\KÕSJİ[ØÛÛ\]Y
H\ÈÛÛ\]YÕSJİ[Ù˜Z[Y
H\È˜Z[Yˆ”“ÓH[™ØYÙ[Y[Üİ]ÈÔ“ÕT–HXİ[Û—İ\HÔ‘Tˆ–HÛÛ\]YTĞÂˆˆˆŠK™™]Ú[

Bˆ‹˜ÛÜÙJ
BˆÙ[‹Üš]WÚœÛÛŠ›İÜ×İ×Û\İ
›İÜÊJB‚‚ˆÈ8¥ 8¥ [˜[]XÜÈÈ\Ú›Ø\™8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ ‚˜Û\ÜÈ\Ú›Ø\™[™\ŠTR[™\ŠN‚ˆYˆÙ]
Ù[ŠN‚ˆˆHÙ]ÙŠ
Bˆİ[H‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓHXØÛİ[ÈŠK™™]ÚÛ™J
VÈ˜È—BˆXİ]™HH‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓHXØÛİ[ÈÒT‘Hİ]\ÏIØXİ]™IÈŠK™™]ÚÛ™J
VÈ˜È—BˆÙÙÙYÚ[ˆH‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓHXØÛİ[ÈÒT‘HÙÚ[—Üİ]\ÏIÛÙÙÙYÚ[‰ÈŠK™™]ÚÛ™J
VÈ˜È—Bˆ™X]]H‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓHXØÛİ[ÈÒT‘Hİ]\ÏIÛ™YY×Ü™X]]	ÈŠK™™]ÚÛ™J
VÈ˜È—Bˆ›ÛİÙ\œÈH‹™^Xİ]J”ÑSPÕÓĞSTĞÑJÕSJ›ÛİÙ\—ØÛİ[
K
H\ÈÈ”“ÓHXØÛİ[ÈŠK™™]ÚÛ™J
VÈ˜È—Bˆİ[Ù›ÛİÚ[™ÈH‹™^Xİ]J”ÑSPÕÓĞSTĞÑJÕSJ›ÛİÚ[™×ØÛİ[
K
H\ÈÈ”“ÓHXØÛİ[ÈŠK™™]ÚÛ™J
VÈ˜È—Bˆİ[İ˜XÚÜÈH‹™^Xİ]J”ÑSPÕÓĞSTĞÑJÕSJ˜XÚ×ØÛİ[
K
H\ÈÈ”“ÓHXØÛİ[ÈŠK™™]ÚÛ™J
VÈ˜È—Bˆİ[Ü™\ÜİÈH‹™^Xİ]J”ÑSPÕÓĞSTĞÑJÕSJ™\ÜİØÛİ[
K
H\ÈÈ”“ÓHXØÛİ[ÈŠK™™]ÚÛ™J
VÈ˜È—BˆØÚY[YH‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓHÜİÈÒT‘Hİ]\ÏIÜØÚY[Y	ÈŠK™™]ÚÛ™J
VÈ˜È—Bˆ[™[™×Ù[™ÈH‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓH[™ØYÙ[Y[ØXİ[ÛœÈÒT‘Hİ]\ÏIÜ[™[™ÉÈŠK™™]ÚÛ™J
VÈ˜È—Bˆİ[Ü›ŞY\ÈH‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓH›ŞY\ÈÒT‘Hİ]\ÏIØXİ]™IÈŠK™™]ÚÛ™J
VÈ˜È—BˆXØÛİ[×İÚ]Ü›ŞHH‹™^Xİ]J”ÑSPÕÓÕS•

ŠH\ÈÈ”“ÓHXØÛİ[ÈÒT‘H›ŞWÚYTÈ“Õ•SŠK™™]ÚÛ™J
VÈ˜È—B‚ˆÈ[™ØYÙ[Y[İ[Âˆ[™×Üİ]ÈH‹™^Xİ]Jˆˆ‚ˆÑSPÕXİ[Û—İ\KÕSJİ[ØÛÛ\]Y
H\ÈÛÛ\]YÕSJİ[Ù˜Z[Y
H\È˜Z[Yˆ”“ÓH[™ØYÙ[Y[Üİ]ÈÔ“ÕT–HXİ[Û—İ\BˆˆˆŠK™™]Ú[

Bˆ[™ØYÙ[Y[İİ[ÈHÜÖÈ˜Xİ[Û—İ\H—NˆÈ˜ÛÛ\]YˆÖÈ˜ÛÛ\]Y—K™˜Z[YˆÖÈ™˜Z[Y—_H›ÜˆÈ[ˆ[™×Üİ]ßB‚ˆÈ[›š[™È\ÚÈÜ›İ\Âˆ[›š[™×İ\ÚÜÈH‹™^Xİ]J”ÑSPÕ
ˆ”“ÓH\Ú×ÙÜ›İ\ÈÒT‘Hİ]\ÈH	Ü[›š[™ÉÈÔ‘Tˆ–HÜ™X]YØ]TĞÈŠK™™]Ú[

Bˆ™XÙ[ØÛÛ\]YH‹™^Xİ]J”ÑSPÕ
ˆ”“ÓH\Ú×ÙÜ›İ\ÈÒT‘Hİ]\ÈH	ØÛÛ\]Y	ÈÔ‘Tˆ–HÜ™X]YØ]TĞÈSRUHŠK™™]Ú[

B‚ˆ\Ú×ÙÜ›İ\×Ù]HH×Bˆ›ÜˆÈ[ˆ\İ
[›š[™×İ\ÚÜÊH
È\İ
™XÙ[ØÛÛ\]Y
N‚ˆH›İ×İ×ÙXİ
ÊBˆÈœ›ÙÜ™\Ü×Üİ—HH›İ[™

È˜ÛÛ\]Yİ\ÚÜÈ—H
ÈÈ™˜Z[Yİ\ÚÜÈ—JHÈX^
Èİ[İ\ÚÜÈ—KJH
ˆLJBˆ\Ú×ÙÜ›İ\×Ù]K˜\[™

B‚ˆÈXØÛİ[İ[[X\šY\ÈÚ]šXÚ]BˆXØÛİ[ÈH‹™^Xİ]Jˆˆ‚ˆÑSPÕKŠ‹šÜİ\È›ŞWÚÜİœÜ\È›ŞWÜÜœ›İØÛÛ\È›ŞWÜ›İØÛÛˆ”“ÓHXØÛİ[ÈHQ•“ÒSˆ›ŞY\ÈÓˆKœ›ŞWÚYHšYˆÔ‘Tˆ–HK™›ÛİÙ\—ØÛİ[TĞÈSRULˆˆˆŠK™™]Ú[

Bˆİ[[X\šY\ÈH×Bˆ›ÜˆXØÈ[ˆXØÛİ[Î‚ˆHH›İ×İ×ÙXİ
XØÊBˆ›ŞWÜİˆHˆØK™Ù]
	Ü›ŞWÜ›İØÛÛ	Ë	Ü	Ê_N‹ËŞØK™Ù]
	Ü›ŞWÚÜİ	Ë	ÉÊ_NØK™Ù]
	Ü›ŞWÜÜ	Ë	ÉÊ_HˆYˆK™Ù]
œ›ŞWÚÜİŠH[ÙH›Û™Bˆİ[[X\šY\Ë˜\[™
Âˆ˜XØÛİ[ÚYˆVÈšY—K™[XZ[ˆVÈ™[XZ[—K\Ù\›˜[YHˆVÈ\Ù\›˜[YH—Kˆ™\Ü^WÛ˜[YHˆK™Ù]
™\Ü^WÛ˜[YHŠK˜š[ÈˆK™Ù]
˜š[ÈŠKˆœ›Ùš[Wİ\›ˆK™Ù]
œ›Ùš[Wİ\›ŠK˜Ú]HˆK™Ù]
˜Ú]HŠKˆœİ]\ÈˆVÈœİ]\È—K›ÙÚ[—Üİ]\ÈˆK™Ù]
›ÙÚ[—Üİ]\ÈŠKˆ™›ÛİÙ\œÈˆVÈ™›ÛİÙ\—ØÛİ[—K™›ÛİÚ[™ÈˆVÈ™›ÛİÚ[™×ØÛİ[—Kˆ˜XÚÜÈˆVÈ˜XÚ×ØÛİ[—Kœ^[\İÈˆVÈœ^[\İØÛİ[—Kˆœ™\ÜİÈˆVÈœ™\ÜİØÛİ[—K›ZÙ\ÈˆVÈ›ZÙ\×ØÛİ[—Kˆœ›ŞHˆ›ŞWÜİ‹ˆJB‚ˆ‹˜ÛÜÙJ
BˆÙ[‹Üš]WÚœÛÛŠÂˆİ[ØXØÛİ[Èˆİ[˜Xİ]™WØXØÛİ[ÈˆXİ]™K›ÙÙÙYÚ[—ØXØÛİ[ÈˆÙÙÙYÚ[‹ˆİ[ÜÜİ×ÜØÚY[YˆØÚY[Yİ[Ù›ÛİÙ\œÈˆ›ÛİÙ\œËˆİ[Ù›ÛİÚ[™Èˆİ[Ù›ÛİÚ[™Ëİ[İ˜XÚÜÈˆİ[İ˜XÚÜËˆİ[Ü™\ÜİÈˆİ[Ü™\ÜİËˆœ[™[™×ØXİ[ÛœÈˆ[™[™×Ù[™Ë˜XØÛİ[×Û™YY[™×Ü™X]]ˆ™X]]ˆİ[Ü›ŞY\Èˆİ[Ü›ŞY\Ë˜XØÛİ[×İÚ]Ü›ŞHˆXØÛİ[×İÚ]Ü›ŞKˆ™[™ØYÙ[Y[İİ[Èˆ[™ØYÙ[Y[İİ[Ëˆ\Ú×ÙÜ›İ\Èˆ\Ú×ÙÜ›İ\×Ù]Kˆ˜XØÛİ[Üİ[[X\šY\Èˆİ[[X\šY\ËˆJB‚‚˜Û\ÜÈXİ]š]SÙÒ[™\ŠTR[™\ŠN‚ˆYˆÙ]
Ù[ŠN‚ˆˆHÙ]ÙŠ
Bˆ›İÜÈH‹™^Xİ]J”ÑSPÕ
ˆ”“ÓHXİ]š]WÛÙÜÈÔ‘Tˆ–HÜ™X]YØ]TĞÈSRULŠK™™]Ú[

Bˆ‹˜ÛÜÙJ
BˆÙ[‹Üš]WÚœÛÛŠ›İÜ×İ×Û\İ
›İÜÊJB‚‚˜Û\ÜÈX[[™\ŠTR[™\ŠN‚ˆYˆÙ]
Ù[ŠN‚ˆÙ[‹Üš]WÚœÛÛŠÈœİ]\Èˆ›ÚÈ‹™\œÚ[ÛˆˆŒËŒŒ‹œ]›Ü›HˆœÛİ[™ÛİYŸJB‚‚ˆÈ8¥ 8¥ \8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ 8¥ ‚™YˆXZÙWØ\

N‚ˆÕUP×ÑT‹›ZÙ\Š^\İÛÚÏUYJBˆ™]\›ˆÜ›˜YËÙX‹\XØ][ÛŠÂˆ
ˆ‹ÚX[‹X[[™\ŠKˆ
ˆ‹Ø\KİŒKÜ›ŞY\ËÏÈ‹›ŞY\Ò[™\ŠKˆ
ˆ‹Ø\KİŒKÜ›ŞY\ËÜ˜[™ÛZ^™H‹›ŞT˜[™ÛZ^™R[™\ŠKˆ
ˆ‹Ø\KİŒKÜ›ŞY\ËØÛX\ˆ‹›ŞPÛX\’[™\ŠKˆ
ˆ‹Ø\KİŒKÜ›ŞY\ËÊØKYŒNKWJÊH‹›ŞQ]Z[[™\ŠKˆ
ˆ‹Ø\KİŒKØXØÛİ[ËÏÈ‹XØÛİ[Ò[™\ŠKˆ
ˆ‹Ø\KİŒKØXØÛİ[ËÛÙÚ[‹Ø[È‹[ÓÙÚ[’[™\ŠKˆ
ˆ‹Ø\KİŒKØXØÛİ[ËÚX[XÚXÚËØ[‹X[ÚXÚĞ[[™\ŠKˆ
ˆ‹Ø\KİŒKØXØÛİ[ËÊØKYŒNKWJÊH‹XØÛİ[]Z[[™\ŠKˆ
ˆ‹Ø\KİŒKØXØÛİ[ËÊØKYŒNKWJÊKÛÙÚ[ˆ‹XØÛİ[ÙÚ[’[™\ŠKˆ
ˆ‹Ø\KİŒKØXØÛİ[ËÊØKYŒNKWJÊKÚX[XÚXÚÈ‹XØÛİ[X[ÚXÚÒ[™\ŠKˆ
ˆ‹Ø\KİŒKØØ[\ZYÛœËÏÈ‹Ø[\ZYÛœÒ[™\ŠKˆ
ˆ‹Ø\KİŒKØØ[\ZYÛœËÊØKYŒNKWJÊH‹Ø[\ZYÛ‘]Z[[™\ŠKˆ
ˆ‹Ø\KİŒKÜÜİËÏÈ‹ÜİÒ[™\ŠKˆ
ˆ‹Ø\KİŒKÜÜİËÊØKYŒNKWJÊH‹Üİ]Z[[™\ŠKˆ
ˆ‹Ø\KİŒKİ\ØYËÏÈ‹\ØYÒ[™\ŠKˆ
ˆ‹Ø\KİŒKİ\ØYËÊØKYŒNKWJÊH‹\ØY]Z[[™\ŠKˆ
ˆ‹Ø\KİŒKÙ[™ØYÙ[Y[ØXİ[Ûˆ‹[™ØYÙ[Y[Xİ[Û’[™\ŠKˆ
ˆ‹Ø\KİŒKÙ[™ØYÙ[Y[Ø[È‹[Ñ[™ØYÙ[Y[[™\ŠKˆ
ˆ‹Ø\KİŒKÙ[™ØYÙ[Y[Üİ]È‹[™ØYÙ[Y[İ]Ò[™\ŠKˆ
ˆ‹Ø\KİŒKİ\ÚËYÜ›İ\ËÏÈ‹\ÚÑÜ›İ\Ò[™\ŠKˆ
ˆ‹Ø\KİŒKİ\ÚËYÜ›İ\ËÊØKYŒNKWJÊH‹\ÚÑÜ›İ\]Z[[™\ŠKˆ
ˆ‹Ø\KİŒKØ[˜[]XÜËÙ\Ú›Ø\™‹\Ú›Ø\™[™\ŠKˆ
ˆ‹Ø\KİŒKØXİ]š]K[ÙÜËÏÈ‹Xİ]š]SÙÒ[™\ŠKˆ
ˆ‹ÊŠŠH‹Ü›˜YËÙX‹”İ]XÑš[R[™\‹Èœ]ˆİŠÕUP×ÑTŠK™Y˜][Ùš[[˜[YHˆš[™^š[ŸJKˆKXYÏUYK]]Ü™[ØYQ˜[ÙKX^Ø›ÙWÜÚ^™OML
ŒL
ŒL
HÈLPˆX^\ØY‚‚šYˆ×Û˜[YW×ÈOH—×ÛXZ[—×È‚ˆ[š]ÙŠ
BˆÙYYÜ™X[ØXØÛİ[Ê
Bˆ\HXZÙWØ\

Bˆ\›\İ[ŠÔ•Y™\ÜÏHŒŒŒŒŠBˆÙÙÙ\‹š[™›ÊˆŠBˆÙÙÙ\‹š[™›Êˆ8¥e8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥eÈŠBˆÙÙÙ\‹š[™›Êˆˆ8¥dHÛİ[™ÛİYXˆŒËŒ8 %ÜÔÔ•MŸH8¥dHŠBˆÙÙÙ\‹š[™›Êˆˆ8¥dH\Ú›Ø\™ˆ‹ËÛØØ[ÜİÔÔ•M_x¥dHŠBˆÙÙÙ\‹š[™›Êˆ8¥f¸¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥d8¥gHŠBˆÙÙÙ\‹š[™›ÊˆŠBˆÜ›˜YËš[ÛÛÜ’SÓÛÜ˜İ\œ™[

Kœİ\

B