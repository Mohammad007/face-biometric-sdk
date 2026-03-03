"""
Multi-tenant SQLite database for the subscription-based biometric SDK.

Tables: subscription_plans, clients, api_keys, api_usage_logs, subjects, face_embeddings
"""

import json
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Database:
    """Multi-tenant SQLite database handler."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Better concurrent reads
        return conn

    def _init_db(self):
        """Create all tables."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    rate_limit_per_minute INTEGER NOT NULL DEFAULT 10,
                    max_subjects INTEGER NOT NULL DEFAULT 100,
                    max_requests_per_month INTEGER NOT NULL DEFAULT 1000,
                    price_monthly REAL NOT NULL DEFAULT 0.0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    plan_id INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    key_prefix TEXT NOT NULL,
                    label TEXT DEFAULT 'default',
                    ip_whitelist TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS api_usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key_id INTEGER NOT NULL,
                    client_id INTEGER NOT NULL,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (api_key_id) REFERENCES api_keys(id),
                    FOREIGN KEY (client_id) REFERENCES clients(id)
                );

                CREATE TABLE IF NOT EXISTS subjects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    subject_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(client_id, subject_name),
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS face_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id INTEGER NOT NULL,
                    embedding TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
                CREATE INDEX IF NOT EXISTS idx_api_keys_client ON api_keys(client_id);
                CREATE INDEX IF NOT EXISTS idx_subjects_client ON subjects(client_id);
                CREATE INDEX IF NOT EXISTS idx_usage_client ON api_usage_logs(client_id);
                CREATE INDEX IF NOT EXISTS idx_usage_date ON api_usage_logs(created_at);
            """)
            conn.commit()
            self._seed_plans(conn)
            self._seed_super_admin(conn)
            self._seed_demo_client(conn)
        finally:
            conn.close()

    def _seed_plans(self, conn: sqlite3.Connection):
        """Seed default subscription plans if empty."""
        count = conn.execute("SELECT COUNT(*) FROM subscription_plans").fetchone()[0]
        if count == 0:
            now = datetime.utcnow().isoformat()
            for plan in settings.DEFAULT_PLANS:
                conn.execute(
                    "INSERT INTO subscription_plans "
                    "(name, rate_limit_per_minute, max_subjects, max_requests_per_month, price_monthly, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (plan["name"], plan["rate_limit_per_minute"], plan["max_subjects"],
                     plan["max_requests_per_month"], plan["price_monthly"], now),
                )
            conn.commit()

    def _seed_super_admin(self, conn: sqlite3.Connection):
        """Seed super admin client if not exists."""
        row = conn.execute(
            "SELECT id FROM clients WHERE email = ?",
            (settings.SUPER_ADMIN_EMAIL,),
        ).fetchone()
        if not row:
            # Get Enterprise plan
            plan = conn.execute(
                "SELECT id FROM subscription_plans WHERE name = 'Enterprise'"
            ).fetchone()
            if plan:
                now = datetime.utcnow().isoformat()
                conn.execute(
                    "INSERT INTO clients (company_name, email, password_hash, plan_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("IDS Soft (Super Admin)", settings.SUPER_ADMIN_EMAIL,
                     pwd_context.hash(settings.SUPER_ADMIN_PASSWORD), plan["id"], now),
                )
                conn.commit()

    def _seed_demo_client(self, conn: sqlite3.Connection):
        """Seed a demo client account if not exists for easy testing."""
        row = conn.execute(
            "SELECT id FROM clients WHERE email = ?",
            ("client@company.com",),
        ).fetchone()
        if not row:
            # Get Free plan
            plan = conn.execute(
                "SELECT id FROM subscription_plans WHERE name = 'Free'"
            ).fetchone()
            if plan:
                now = datetime.utcnow().isoformat()
                conn.execute(
                    "INSERT INTO clients (company_name, email, password_hash, plan_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Demo Company", "client@company.com",
                     pwd_context.hash("Client@123456"), plan["id"], now),
                )
                conn.commit()

    # ══════════════════════════════════════════════
    #  SUBSCRIPTION PLANS
    # ══════════════════════════════════════════════

    def create_plan(self, name: str, rate_limit: int, max_subjects: int,
                    max_requests: int, price: float) -> dict:
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                "INSERT INTO subscription_plans "
                "(name, rate_limit_per_minute, max_subjects, max_requests_per_month, price_monthly, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, rate_limit, max_subjects, max_requests, price, now),
            )
            conn.commit()
            return {"id": cursor.lastrowid, "name": name}
        except sqlite3.IntegrityError:
            raise ValueError(f"Plan '{name}' already exists")
        finally:
            conn.close()

    def list_plans(self) -> List[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM subscription_plans ORDER BY price_monthly").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_plan(self, plan_id: int) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM subscription_plans WHERE id = ?", (plan_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ══════════════════════════════════════════════
    #  CLIENTS
    # ══════════════════════════════════════════════

    def create_client(self, company_name: str, email: str, password: str, plan_id: int) -> dict:
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            password_hash = pwd_context.hash(password)
            cursor = conn.execute(
                "INSERT INTO clients (company_name, email, password_hash, plan_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (company_name, email, password_hash, plan_id, now),
            )
            conn.commit()
            return {"id": cursor.lastrowid, "company_name": company_name, "email": email}
        except sqlite3.IntegrityError:
            raise ValueError(f"Client with email '{email}' already exists")
        finally:
            conn.close()

    def get_client_by_email(self, email: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM clients WHERE email = ?", (email,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_client(self, client_id: int) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT c.*, p.name as plan_name, p.rate_limit_per_minute, "
                "p.max_subjects, p.max_requests_per_month "
                "FROM clients c JOIN subscription_plans p ON c.plan_id = p.id "
                "WHERE c.id = ?", (client_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_clients(self) -> List[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT c.id, c.company_name, c.email, c.is_active, c.created_at,
                       p.name as plan_name,
                       (SELECT COUNT(*) FROM api_keys ak WHERE ak.client_id = c.id AND ak.is_active = 1) as active_keys,
                       (SELECT COUNT(*) FROM subjects s WHERE s.client_id = c.id) as total_subjects
                FROM clients c
                JOIN subscription_plans p ON c.plan_id = p.id
                ORDER BY c.created_at DESC
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_client(self, client_id: int, **kwargs) -> bool:
        conn = self._get_conn()
        try:
            updates = []
            values = []
            for key, val in kwargs.items():
                if key in ("plan_id", "is_active", "company_name"):
                    updates.append(f"{key} = ?")
                    values.append(val)
            if not updates:
                return False
            values.append(client_id)
            cursor = conn.execute(
                f"UPDATE clients SET {', '.join(updates)} WHERE id = ?", values
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_client(self, client_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def verify_client_password(self, email: str, password: str) -> Optional[dict]:
        """Verify client credentials and return client info."""
        client = self.get_client_by_email(email)
        if client and pwd_context.verify(password, client["password_hash"]):
            return client
        return None

    # ══════════════════════════════════════════════
    #  API KEYS
    # ══════════════════════════════════════════════

    def store_api_key(self, client_id: int, key_hash: str, key_prefix: str,
                      label: str = "default", ip_whitelist: str = None,
                      expires_at: str = None) -> int:
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                "INSERT INTO api_keys (client_id, key_hash, key_prefix, label, ip_whitelist, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (client_id, key_hash, key_prefix, label, ip_whitelist, expires_at, now),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_api_key_by_hash(self, key_hash: str) -> Optional[dict]:
        """Look up an API key by its hash, including client and plan info."""
        conn = self._get_conn()
        try:
            row = conn.execute("""
                SELECT ak.*, c.id as client_id, c.company_name, c.is_active as client_active,
                       p.rate_limit_per_minute, p.max_subjects, p.max_requests_per_month, p.name as plan_name
                FROM api_keys ak
                JOIN clients c ON ak.client_id = c.id
                JOIN subscription_plans p ON c.plan_id = p.id
                WHERE ak.key_hash = ?
            """, (key_hash,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_client_api_keys(self, client_id: int) -> List[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, key_prefix, label, ip_whitelist, is_active, expires_at, created_at "
                "FROM api_keys WHERE client_id = ? ORDER BY created_at DESC",
                (client_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def revoke_api_key(self, key_id: int, client_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE api_keys SET is_active = 0 WHERE id = ? AND client_id = ?",
                (key_id, client_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ══════════════════════════════════════════════
    #  API USAGE LOGS
    # ══════════════════════════════════════════════

    def log_usage(self, api_key_id: int, client_id: int, endpoint: str,
                  method: str, status_code: int = 200):
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO api_usage_logs (api_key_id, client_id, endpoint, method, status_code, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (api_key_id, client_id, endpoint, method, status_code, now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_monthly_usage(self, client_id: int) -> int:
        """Get request count for current month."""
        conn = self._get_conn()
        try:
            now = datetime.utcnow()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM api_usage_logs WHERE client_id = ? AND created_at >= ?",
                (client_id, month_start),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_client_usage_stats(self, client_id: int) -> dict:
        """Get usage statistics for a client."""
        conn = self._get_conn()
        try:
            now = datetime.utcnow()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

            monthly = conn.execute(
                "SELECT COUNT(*) as cnt FROM api_usage_logs WHERE client_id = ? AND created_at >= ?",
                (client_id, month_start),
            ).fetchone()["cnt"]

            daily = conn.execute(
                "SELECT COUNT(*) as cnt FROM api_usage_logs WHERE client_id = ? AND created_at >= ?",
                (client_id, today_start),
            ).fetchone()["cnt"]

            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM api_usage_logs WHERE client_id = ?",
                (client_id,),
            ).fetchone()["cnt"]

            # Per-endpoint breakdown
            endpoints = conn.execute(
                "SELECT endpoint, COUNT(*) as cnt FROM api_usage_logs "
                "WHERE client_id = ? AND created_at >= ? GROUP BY endpoint ORDER BY cnt DESC",
                (client_id, month_start),
            ).fetchall()

            return {
                "requests_today": daily,
                "requests_this_month": monthly,
                "requests_total": total,
                "endpoint_breakdown": [dict(e) for e in endpoints],
            }
        finally:
            conn.close()

    def get_global_stats(self) -> dict:
        """Get global usage statistics for super admin."""
        conn = self._get_conn()
        try:
            clients_count = conn.execute("SELECT COUNT(*) as cnt FROM clients").fetchone()["cnt"]
            keys_count = conn.execute("SELECT COUNT(*) as cnt FROM api_keys WHERE is_active = 1").fetchone()["cnt"]
            subjects_count = conn.execute("SELECT COUNT(*) as cnt FROM subjects").fetchone()["cnt"]
            now = datetime.utcnow()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            monthly_requests = conn.execute(
                "SELECT COUNT(*) as cnt FROM api_usage_logs WHERE created_at >= ?",
                (month_start,),
            ).fetchone()["cnt"]
            return {
                "total_clients": clients_count,
                "active_api_keys": keys_count,
                "total_subjects": subjects_count,
                "requests_this_month": monthly_requests,
            }
        finally:
            conn.close()

    # ══════════════════════════════════════════════
    #  SUBJECTS (tenant-isolated)
    # ══════════════════════════════════════════════

    def create_subject(self, client_id: int, subject_name: str) -> dict:
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                "INSERT INTO subjects (client_id, subject_name, created_at) VALUES (?, ?, ?)",
                (client_id, subject_name, now),
            )
            conn.commit()
            return {"id": cursor.lastrowid, "subject_name": subject_name, "created_at": now}
        except sqlite3.IntegrityError:
            raise ValueError(f"Subject '{subject_name}' already exists for this client")
        finally:
            conn.close()

    def get_subject(self, client_id: int, subject_name: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM subjects WHERE client_id = ? AND subject_name = ?",
                (client_id, subject_name),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_subjects(self, client_id: int) -> List[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT s.id, s.subject_name, s.created_at, COUNT(f.id) as face_count
                FROM subjects s
                LEFT JOIN face_embeddings f ON s.id = f.subject_id
                WHERE s.client_id = ?
                GROUP BY s.id ORDER BY s.created_at DESC
            """, (client_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_subjects(self, client_id: int) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM subjects WHERE client_id = ?", (client_id,)
            ).fetchone()
            return row["cnt"]
        finally:
            conn.close()

    def delete_subject(self, client_id: int, subject_name: str) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM subjects WHERE client_id = ? AND subject_name = ?",
                (client_id, subject_name),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ══════════════════════════════════════════════
    #  FACE EMBEDDINGS (tenant-isolated via subject)
    # ══════════════════════════════════════════════

    def add_embedding(self, subject_id: int, embedding: np.ndarray) -> int:
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            embedding_json = json.dumps(embedding.tolist())
            cursor = conn.execute(
                "INSERT INTO face_embeddings (subject_id, embedding, created_at) VALUES (?, ?, ?)",
                (subject_id, embedding_json, now),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_all_embeddings(self, client_id: int) -> List[Tuple[str, np.ndarray]]:
        """Get all embeddings for a client's subjects."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT s.subject_name, f.embedding
                FROM face_embeddings f
                JOIN subjects s ON s.id = f.subject_id
                WHERE s.client_id = ?
                ORDER BY s.subject_name
            """, (client_id,)).fetchall()
            return [
                (row["subject_name"], np.array(json.loads(row["embedding"]), dtype=np.float32))
                for row in rows
            ]
        finally:
            conn.close()


# Singleton
db = Database()
