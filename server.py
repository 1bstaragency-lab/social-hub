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


def seed_demo_data():
    """Seed rich demo data to show the dashboard populated."""
    conn = get_db()
    if conn.execute("SELECT COUNT(*) as c FROM accounts").fetchone()["c"] > 0:
        conn.close()
        return

    org_id = "00000000-0000-0000-0000-000000000001"

    # ── Proxies ──
    proxy_data = [
        ("http", "154.12.87.23", 8080, None, None, "US East", "active", "US"),
        ("socks5", "45.67.89.101", 1080, "proxyuser1", "pxpass123", "EU Residential", "active", "DE"),
        ("http", "103.28.44.55", 3128, "admin", "secret99", "Asia Datacenter", "active", "SG"),
        ("https", "198.51.100.78", 443, None, None, "US West", "active", "US"),
        ("socks5", "91.108.12.34", 9050, "socks_user", "s0cksP!", "EU Mix", "active", "NL"),
        ("http", "172.67.88.200", 8888, "resi_user", "rpass456", "US Residential", "active", "US"),
        ("socks5", "185.220.33.44", 1080, None, None, "Nordic", "active", "SE"),
        ("http", "23.94.56.78", 31280, None, None, "Backup 1", "slow", "US"),
    ]
    proxy_ids = []
    for p in proxy_data:
        pid = str(uuid.uuid4())
        proxy_ids.append(pid)
        conn.execute(
            "INSERT INTO proxies (id, protocol, host, port, username, password, label, status, country) VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, *p)
        )

    active_proxies = [pid for pid, p in zip(proxy_ids, proxy_data) if p[6] == "active"]

    # ── Accounts with rich profile data ──
    accounts_data = [
        {
            "email": "jay_beats@gmail.com", "password": "JayBeats2026!",
            "username": "jay_beats", "display_name": "Jay Beats",
            "bio": "Producer & beatmaker from Atlanta. Trap, R&B, and everything in between.",
            "profile_url": "https://soundcloud.com/jay_beats",
            "city": "Atlanta", "country": "US",
            "follower_count": 12840, "following_count": 3421, "track_count": 67,
            "playlist_count": 12, "repost_count": 234, "likes_count": 1567,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "studio_one_music@outlook.com", "password": "Studi0One!",
            "username": "studio_one_official", "display_name": "Studio One",
            "bio": "Independent label. New music every Friday. Submissions open.",
            "profile_url": "https://soundcloud.com/studio_one_official",
            "city": "Los Angeles", "country": "US",
            "follower_count": 45200, "following_count": 890, "track_count": 234,
            "playlist_count": 28, "repost_count": 1102, "likes_count": 4230,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "nightowl_music@yahoo.com", "password": "N1ghtOwl!!",
            "username": "nightowl_beats", "display_name": "NightOwl",
            "bio": "Late night vibes. Lo-fi, ambient, chill beats. DM for collabs.",
            "profile_url": "https://soundcloud.com/nightowl_beats",
            "city": "Chicago", "country": "US",
            "follower_count": 8930, "following_count": 2100, "track_count": 45,
            "playlist_count": 8, "repost_count": 189, "likes_count": 890,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "1bstar_official@gmail.com", "password": "1BStar2026#",
            "username": "1bstar_official", "display_name": "1BStar",
            "bio": "1BStar Agency. Artist management & music distribution. #1BStar",
            "profile_url": "https://soundcloud.com/1bstar_official",
            "city": "Miami", "country": "US",
            "follower_count": 78500, "following_count": 1200, "track_count": 156,
            "playlist_count": 34, "repost_count": 2890, "likes_count": 8900,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "beatmaker_pro@hotmail.com", "password": "BeatMaker!!",
            "username": "beatmaker_pro", "display_name": "BeatMaker Pro",
            "bio": "Type beats daily. Free for non-profit. Lease beats on my website.",
            "profile_url": "https://soundcloud.com/beatmaker_pro",
            "city": "Houston", "country": "US",
            "follower_count": 23100, "following_count": 5600, "track_count": 312,
            "playlist_count": 45, "repost_count": 670, "likes_count": 3400,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "sound_wave_x@gmail.com", "password": "WaveX456!!",
            "username": "sound_wave_x", "display_name": "SoundWaveX",
            "bio": "Electronic music producer. Future bass / dubstep / house.",
            "profile_url": "https://soundcloud.com/sound_wave_x",
            "city": "Denver", "country": "US",
            "follower_count": 5670, "following_count": 1890, "track_count": 28,
            "playlist_count": 6, "repost_count": 145, "likes_count": 567,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "trap_lord_99@gmail.com", "password": "TrapL0rd99",
            "username": "trap_lord_99", "display_name": "TRAP LORD",
            "bio": "Hard hitting 808s. Dark trap beats. Underground.",
            "profile_url": "https://soundcloud.com/trap_lord_99",
            "city": "Detroit", "country": "US",
            "follower_count": 3450, "following_count": 980, "track_count": 89,
            "playlist_count": 5, "repost_count": 78, "likes_count": 340,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "melodyqueen@gmail.com", "password": "Mel0dyQn!!",
            "username": "melodyqueen", "display_name": "MelodyQueen",
            "bio": "Vocalist & songwriter. R&B, soul, pop. Available for features.",
            "profile_url": "https://soundcloud.com/melodyqueen",
            "city": "New York", "country": "US",
            "follower_count": 15800, "following_count": 2340, "track_count": 42,
            "playlist_count": 9, "repost_count": 312, "likes_count": 2100,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "bass_drop_king@outlook.com", "password": "Ba$$Dr0p!",
            "username": "bass_drop_king", "display_name": "Bass Drop King",
            "bio": "If the bass doesn't drop, I don't care. EDM / Dubstep / DNB",
            "profile_url": "https://soundcloud.com/bass_drop_king",
            "city": "Las Vegas", "country": "US",
            "follower_count": 9200, "following_count": 1450, "track_count": 56,
            "playlist_count": 11, "repost_count": 234, "likes_count": 1230,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "lofi_dreamer@yahoo.com", "password": "L0fiDream!",
            "username": "lofi_dreamer", "display_name": "lofi dreamer",
            "bio": "beats to study/relax to. 24/7 chill vibes.",
            "profile_url": "https://soundcloud.com/lofi_dreamer",
            "city": "Portland", "country": "US",
            "follower_count": 31200, "following_count": 780, "track_count": 189,
            "playlist_count": 22, "repost_count": 890, "likes_count": 5600,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "underground_hiphop@gmail.com", "password": "UndGrnd!!",
            "username": "underground_hiphop", "display_name": "Underground HipHop",
            "bio": "Curating the best underground hip-hop. Submit your tracks.",
            "profile_url": "https://soundcloud.com/underground_hiphop",
            "city": "Philadelphia", "country": "US",
            "follower_count": 67800, "following_count": 4500, "track_count": 0,
            "playlist_count": 56, "repost_count": 5600, "likes_count": 12000,
            "login_status": "logged_in", "status": "active",
        },
        {
            "email": "synth_master_x@gmail.com", "password": "SynthM@str",
            "username": "synth_master_x", "display_name": "Synth Master",
            "bio": "Analog synth enthusiast. Modular patches and electronic experiments.",
            "profile_url": "https://soundcloud.com/synth_master_x",
            "city": "Austin", "country": "US",
            "follower_count": 4120, "following_count": 890, "track_count": 34,
            "playlist_count": 4, "repost_count": 56, "likes_count": 280,
            "login_status": "not_logged_in", "status": "needs_reauth",
        },
    ]

    account_ids = []
    for a in accounts_data:
        aid = str(uuid.uuid4())
        account_ids.append(aid)
        proxy_id = random.choice(active_proxies)
        cookie_file = f"{COOKIE_DIR}/{aid}.json"
        conn.execute(
            """INSERT INTO accounts
               (id, organization_id, email, encrypted_password, username, display_name,
                bio, profile_url, city, country, status, login_status, proxy_id,
                follower_count, following_count, track_count, playlist_count,
                repost_count, likes_count, cookie_file, last_login_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (aid, org_id, a["email"], encrypt_credential(a["password"]),
             a["username"], a["display_name"], a["bio"], a["profile_url"],
             a["city"], a["country"], a["status"], a["login_status"], proxy_id,
             a["follower_count"], a["following_count"], a["track_count"],
             a["playlist_count"], a["repost_count"], a["likes_count"],
             cookie_file, datetime.now(timezone.utc).isoformat() if a["login_status"] == "logged_in" else None),
        )

        # Seed engagement stats per account
        for action in ["like", "repost", "follow", "play", "comment"]:
            completed = random.randint(10, 400)
            failed = random.randint(0, int(completed * 0.05))
            conn.execute(
                "INSERT INTO engagement_stats (id, account_id, action_type, total_completed, total_failed, last_executed) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), aid, action, completed, failed,
                 datetime.now(timezone.utc).isoformat()),
            )

    # ── Seed task groups with progress ──
    task_groups = [
        ("like", "https://soundcloud.com/artist/new-single", None, 12, 10, 1, "running"),
        ("repost", "https://soundcloud.com/artist/hot-track", None, 12, 12, 0, "completed"),
        ("follow", "https://soundcloud.com/target-artist", None, 12, 8, 2, "running"),
        ("play", "https://soundcloud.com/artist/latest-drop", None, 12, 12, 0, "completed"),
        ("comment", "https://soundcloud.com/artist/fire-beat", "This is fire! Great work!", 12, 5, 0, "running"),
        ("like", "https://soundcloud.com/artist/second-wave", None, 12, 12, 0, "completed"),
    ]
    for tg in task_groups:
        gid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO task_groups (id, action_type, target_url, comment_text,
               total_tasks, completed_tasks, failed_tasks, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (gid, *tg, (datetime.now(timezone.utc) - timedelta(minutes=random.randint(5, 120))).isoformat()),
        )
        # Create individual tasks
        for i, aid in enumerate(account_ids[:tg[3]]):
            eid = str(uuid.uuid4())
            if i < tg[4]:
                st = "completed"
            elif i < tg[4] + tg[5]:
                st = "failed"
            else:
                st = "pending"
            conn.execute(
                """INSERT INTO engagement_actions
                   (id, task_group_id, account_id, action_type, target_url, comment_text, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (eid, gid, aid, tg[0], tg[1], tg[2], st, datetime.now(timezone.utc).isoformat()),
            )

    conn.commit()
    conn.close()
    logger.info(f"Seeded {len(accounts_data)} accounts, {len(proxy_data)} proxies, {len(task_groups)} task groups")


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


# ── Task Group / Engagement ──────────────────────────────────────────────────

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
                "INSERT INTO engagement_actions (id, task_group_id, account_id, action_type, target_url, comment_text, status) VALUES (?,?,?,?,?,?,'pending')",
                (eid, gid, acc_id, data["action_type"], data.get("target_url"), data.get("comment_text")),
            )
        db.commit()
        db.close()
        self.write_json({"task_group_id": gid, "status": "running", "total": len(account_ids)})


class EngagementStatsHandler(APIHandler):
    """Global engagement stats across all accounts."""
    def get(self):
        db = get_db()
        rows = db.execute("""
            SELECT action_type, SUM(total_completed) as completed, SUM(total_failed) as failed
            FROM engagement_stats GROUP BY action_type ORDER BY completed DESC
        """).fetchall()
        db.close()
        self.write_json(rows_to_list(rows))


# ── Analytics / Dashboard ────────────────────────────────────────────────────

class DashboardHandler(APIHandler):
    def get(self):
        db = get_db()
        total = db.execute("SELECT COUNT(*) as c FROM accounts").fetchone()["c"]
        active = db.execute("SELECT COUNT(*) as c FROM accounts WHERE status='active'").fetchone()["c"]
        logged_in = db.execute("SELECT COUNT(*) as c FROM accounts WHERE login_status='logged_in'").fetchone()["c"]
        reauth = db.execute("SELECT COUNT(*) as c FROM accounts WHERE status='needs_reauth'").fetchone()["c"]
        followers = db.execute("SELECT COALESCE(SUM(follower_count),0) as c FROM accounts").fetchone()["c"]
        total_following = db.execute("SELECT COALESCE(SUM(following_count),0) as c FROM accounts").fetchone()["c"]
        total_tracks = db.execute("SELECT COALESCE(SUM(track_count),0) as c FROM accounts").fetchone()["c"]
        total_reposts = db.execute("SELECT COALESCE(SUM(repost_count),0) as c FROM accounts").fetchone()["c"]
        scheduled = db.execute("SELECT COUNT(*) as c FROM posts WHERE status='scheduled'").fetchone()["c"]
        pending_eng = db.execute("SELECT COUNT(*) as c FROM engagement_actions WHERE status='pending'").fetchone()["c"]
        total_proxies = db.execute("SELECT COUNT(*) as c FROM proxies WHERE status='active'").fetchone()["c"]
        accounts_with_proxy = db.execute("SELECT COUNT(*) as c FROM accounts WHERE proxy_id IS NOT NULL").fetchone()["c"]

        # Engagement totals
        eng_stats = db.execute("""
            SELECT action_type, SUM(total_completed) as completed, SUM(total_failed) as failed
            FROM engagement_stats GROUP BY action_type
        """).fetchall()
        engagement_totals = {s["action_type"]: {"completed": s["completed"], "failed": s["failed"]} for s in eng_stats}

        # Running task groups
        running_tasks = db.execute("SELECT * FROM task_groups WHERE status = 'running' ORDER BY created_at DESC").fetchall()
        recent_completed = db.execute("SELECT * FROM task_groups WHERE status = 'completed' ORDER BY created_at DESC LIMIT 5").fetchall()

        task_groups_data = []
        for tg in list(running_tasks) + list(recent_completed):
            d = row_to_dict(tg)
            d["progress_pct"] = round((d["completed_tasks"] + d["failed_tasks"]) / max(d["total_tasks"], 1) * 100, 1)
            task_groups_data.append(d)

        # Account summaries with rich data
        accounts = db.execute("""
            SELECT a.*, p.host as proxy_host, p.port as proxy_port, p.protocol as proxy_protocol
            FROM accounts a LEFT JOIN proxies p ON a.proxy_id = p.id
            ORDER BY a.follower_count DESC LIMIT 50
        """).fetchall()
        summaries = []
        for acc in accounts:
            a = row_to_dict(acc)
            proxy_str = f"{a.get('proxy_protocol','http')}://{a['proxy_host']}:{a['proxy_port']}" if a.get("proxy_host") else None
            summaries.append({
                "account_id": a["id"], "email": a["email"], "username": a["username"],
                "display_name": a.get("display_name"), "bio": a.get("bio"),
                "profile_url": a.get("profile_url"), "city": a.get("city"),
                "status": a["status"], "login_status": a.get("login_status"),
                "followers": a["follower_count"], "following": a["following_count"],
                "tracks": a["track_count"], "playlists": a["playlist_count"],
                "reposts": a["repost_count"], "likes": a["likes_count"],
                "proxy": proxy_str,
            })

        db.close()
        self.write_json({
            "total_accounts": total, "active_accounts": active, "logged_in_accounts": logged_in,
            "total_posts_scheduled": scheduled, "total_followers": followers,
            "total_following": total_following, "total_tracks": total_tracks,
            "total_reposts": total_reposts,
            "pending_actions": pending_eng, "accounts_needing_reauth": reauth,
            "total_proxies": total_proxies, "accounts_with_proxy": accounts_with_proxy,
            "engagement_totals": engagement_totals,
            "task_groups": task_groups_data,
            "account_summaries": summaries,
        })


class ActivityLogHandler(APIHandler):
    def get(self):
        db = get_db()
        rows = db.execute("SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 50").fetchall()
        db.close()
        self.write_json(rows_to_list(rows))


class HealthHandler(APIHandler):
    def get(self):
        self.write_json({"status": "ok", "version": "3.0.0", "platform": "soundcloud"})


# ── App ──────────────────────────────────────────────────────────────────────

def make_app():
    STATIC_DIR.mkdir(exist_ok=True)
    return tornado.web.Application([
        (r"/health", HealthHandler),
        (r"/api/v1/proxies/?", ProxiesHandler),
        (r"/api/v1/proxies/randomize", ProxyRandomizeHandler),
        (r"/api/v1/proxies/clear", ProxyClearHandler),
        (r"/api/v1/proxies/([a-f0-9-]+)", ProxyDetailHandler),
        (r"/api/v1/accounts/?", AccountsHandler),
        (r"/api/v1/accounts/health-check/all", HealthCheckAllHandler),
        (r"/api/v1/accounts/([a-f0-9-]+)", AccountDetailHandler),
        (r"/api/v1/accounts/([a-f0-9-]+)/health-check", AccountHealthCheckHandler),
        (r"/api/v1/campaigns/?", CampaignsHandler),
        (r"/api/v1/campaigns/([a-f0-9-]+)", CampaignDetailHandler),
        (r"/api/v1/posts/?", PostsHandler),
        (r"/api/v1/posts/([a-f0-9-]+)", PostDetailHandler),
        (r"/api/v1/uploads/?", UploadsHandler),
        (r"/api/v1/uploads/([a-f0-9-]+)", UploadDetailHandler),
        (r"/api/v1/engagement/action", EngagementActionHandler),
        (r"/api/v1/engagement/bulk", BulkEngagementHandler),
        (r"/api/v1/engagement/stats", EngagementStatsHandler),
        (r"/api/v1/task-groups/?", TaskGroupsHandler),
        (r"/api/v1/task-groups/([a-f0-9-]+)", TaskGroupDetailHandler),
        (r"/api/v1/analytics/dashboard", DashboardHandler),
        (r"/api/v1/activity-logs/?", ActivityLogHandler),
        (r"/(.*)", tornado.web.StaticFileHandler, {"path": str(STATIC_DIR), "default_filename": "index.html"}),
    ], debug=True, autoreload=False, max_body_size=500*1024*1024)  # 500MB max upload


if __name__ == "__main__":
    init_db()
    seed_demo_data()
    app = make_app()
    app.listen(PORT, address="0.0.0.0")
    logger.info("")
    logger.info("  ╔══════════════════════════════════════════════╗")
    logger.info(f"  ║  SoundCloud Hub v3.0 — port {PORT:<16}   ║")
    logger.info(f"  ║  Dashboard:  http://localhost:{PORT:<15}║")
    logger.info("  ╚══════════════════════════════════════════════╝")
    logger.info("")
    tornado.ioloop.IOLoop.current().start()
