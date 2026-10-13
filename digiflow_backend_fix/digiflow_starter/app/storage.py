from __future__ import annotations

import json
import sqlite3
import threading
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA / "digiflow.sqlite3"

CATEGORIES = [
    "Business & Investment",
    "Dating, Relationships & Romance",
    "Education",
    "Health & Fitness",
    "Family & Children",
    "Hobby & Craft",
]
ALL_CATEGORIES = "All Categories"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.lock = threading.RLock()
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init(self):
        with self.lock, self._connect() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    currency TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'collected',
                    approved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
                CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);

                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    category TEXT,
                    target_count INTEGER NOT NULL DEFAULT 60,
                    status TEXT NOT NULL DEFAULT 'queued',
                    message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL UNIQUE,
                    title TEXT,
                    description TEXT,
                    keywords_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'created',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS pins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL UNIQUE,
                    title TEXT,
                    description TEXT,
                    destination_url TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def fingerprint(category: str, name: str, url: str) -> str:
        raw = "|".join([category.strip().lower(), name.strip().lower(), url.strip().rstrip("/").lower()])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def audit(self, actor: str, action: str, entity_type: str, entity_id: Any = None, details: dict | None = None):
        with self.lock, self._connect() as c:
            c.execute(
                "INSERT INTO audit(actor,action,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?,?)",
                (actor, action, entity_type, str(entity_id) if entity_id is not None else None, json.dumps(details or {}), now()),
            )

    def add_product(self, *, category: str, name: str, url: str, amount: str, currency: str | None = None, details: dict | None = None):
        category = category.strip()
        name = name.strip()
        url = url.strip()
        amount = str(amount).strip()
        if category not in CATEGORIES:
            raise ValueError("Invalid category")
        if not name or not url or not amount:
            raise ValueError("name, url and amount are required")
        fp = self.fingerprint(category, name, url)
        t = now()
        with self.lock, self._connect() as c:
            try:
                cur = c.execute(
                    "INSERT INTO products(fingerprint,category,name,url,amount,currency,details_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (fp, category, name, url, amount, currency, json.dumps(details or {}), "collected", t, t),
                )
            except sqlite3.IntegrityError:
                row = c.execute("SELECT * FROM products WHERE fingerprint=?", (fp,)).fetchone()
                raise ValueError(f"Duplicate product already stored (id {row['id']})")
            pid = cur.lastrowid
        self.audit("system", "product_added", "product", pid, {"category": category, "name": name})
        return self.product(pid)

    def product(self, product_id: int):
        with self.lock, self._connect() as c:
            row = c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["details"] = json.loads(d.pop("details_json") or "{}")
            d["approved"] = bool(d["approved"])
            return d

    def products(self, category: str | None = None):
        with self.lock, self._connect() as c:
            if category and category != ALL_CATEGORIES:
                rows = c.execute("SELECT * FROM products WHERE category=? ORDER BY id", (category,)).fetchall()
            else:
                rows = c.execute("SELECT * FROM products ORDER BY id").fetchall()
            out = []
            for row in rows:
                d = dict(row)
                d["details"] = json.loads(d.pop("details_json") or "{}")
                d["approved"] = bool(d["approved"])
                out.append(d)
            return out

    def set_product_status(self, product_id: int, status: str, approved: bool | None = None):
        allowed = {"collected", "verified", "rejected", "approved", "content_ready", "image_ready", "pin_ready"}
        if status not in allowed:
            raise ValueError("Invalid product status")
        with self.lock, self._connect() as c:
            if approved is None:
                c.execute("UPDATE products SET status=?,updated_at=? WHERE id=?", (status, now(), product_id))
            else:
                c.execute("UPDATE products SET status=?,approved=?,updated_at=? WHERE id=?", (status, int(approved), now(), product_id))
            if c.total_changes == 0:
                raise ValueError("Product not found")
        self.audit("user", "product_status", "product", product_id, {"status": status, "approved": approved})
        return self.product(product_id)

    def create_run(self, kind: str, category: str | None, target_count: int):
        t = now()
        with self.lock, self._connect() as c:
            cur = c.execute("INSERT INTO runs(kind,category,target_count,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (kind, category, target_count, "queued", t, t))
            rid = cur.lastrowid
        self.audit("user", "run_created", "run", rid, {"kind": kind, "category": category, "target_count": target_count})
        return self.run(rid)

    def run(self, run_id: int):
        with self.lock, self._connect() as c:
            row = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def runs(self):
        with self.lock, self._connect() as c:
            return [dict(x) for x in c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 50")]

    def create_task(self, kind: str, payload: dict | None = None):
        t = now()
        with self.lock, self._connect() as c:
            cur = c.execute("INSERT INTO tasks(kind,status,progress,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)", (kind, "queued", 0, json.dumps(payload or {}), t, t))
            tid = cur.lastrowid
        self.audit("system", "task_created", "task", tid, {"kind": kind})
        return self.task(tid)

    def task(self, task_id: int):
        with self.lock, self._connect() as c:
            row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row: return None
            d = dict(row); d["payload"] = json.loads(d.pop("payload_json") or "{}"); return d

    def tasks(self):
        with self.lock, self._connect() as c:
            rows = c.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 50").fetchall()
            out=[]
            for row in rows:
                d=dict(row); d["payload"]=json.loads(d.pop("payload_json") or "{}"); out.append(d)
            return out

    def counts(self):
        with self.lock, self._connect() as c:
            total = c.execute("SELECT COUNT(*) n FROM products").fetchone()["n"]
            verified = c.execute("SELECT COUNT(*) n FROM products WHERE status IN ('verified','approved','content_ready','image_ready','pin_ready')").fetchone()["n"]
            images = c.execute("SELECT COUNT(*) n FROM assets WHERE kind='image'").fetchone()["n"]
            review = c.execute("SELECT COUNT(*) n FROM products WHERE status='approved'").fetchone()["n"]
            running = c.execute("SELECT COUNT(*) n FROM tasks WHERE status IN ('queued','running')").fetchone()["n"]
            completed = c.execute("SELECT COUNT(*) n FROM tasks WHERE status='completed'").fetchone()["n"]
            bycat = {cat: c.execute("SELECT COUNT(*) n FROM products WHERE category=?", (cat,)).fetchone()["n"] for cat in CATEGORIES}
            return {"products": total, "verified": verified, "images": images, "review": review, "running_tasks": running, "completed_tasks": completed, "by_category": bycat}

    def audit_rows(self):
        with self.lock, self._connect() as c:
            rows=c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100").fetchall()
            out=[]
            for row in rows:
                d=dict(row); d["details"]=json.loads(d.pop("details_json") or "{}"); out.append(d)
            return out


storage = Storage()
