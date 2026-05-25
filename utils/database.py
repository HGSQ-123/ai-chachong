"""
数据库管理器 - 使用SQLite实现数据持久化
封装所有数据库操作，支持用户、检测记录、计费记录的CRUD
支持 Turso 云数据库（设置环境变量自动切换）
"""

import sqlite3
import os
import json
from datetime import datetime
from contextlib import contextmanager

# Turso 配置（优先环境变量，回退硬编码）
TURSO_URL = os.getenv("TURSO_DB_URL", "") or "libsql://aichachong-hgsq-123.aws-ap-northeast-1.turso.io"
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "") or "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzkyNDYyMDgsImlkIjoiMDE5ZTQzNTUtNTkwMS03NTA3LWJjZTMtOWQyYTIzYWQ3YzA1IiwicmlkIjoiOWE2ZDBkNTMtMTZlNS00YzMxLWE0ODQtOTJmYWMxM2FlNmVjIn0.DPyWDyqAnUHUeO5-qIkhYubK_S5SxKKYEvRyHxDNyEsp8Aqr_ryv5nm40rOd9-G8UySdkhaKLF129v88RfRBDg"


class TursoConn:
    """轻量 Turso HTTP 连接，模拟 sqlite3 接口"""
    def __init__(self, url, token):
        self._url = url.replace("libsql://", "https://")
        self._token = token
        self.row_factory = None
        self._rows = []
        self._idx = 0
        self.rowcount = 0
        self.lastrowid = 0
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def cursor(self):
        return self
    def execute(self, sql, params=None):
        import requests as _r
        resp = _r.post(f"{self._url}/v2/pipeline",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            json={"requests": [{"type": "execute", "stmt": {"sql": sql, "args": params or []}}, {"type": "close"}]},
            timeout=30)
        resp.raise_for_status()
        data = resp.json()
        res = data.get("results", [{}])[0].get("response", {}).get("result", {})
        cols = res.get("cols", [])
        raw_rows = res.get("rows", [])
        self._rows = []
        for row in raw_rows:
            d = {}
            for i, col in enumerate(cols):
                cell = row[i]
                v = cell.get("value") if isinstance(cell, dict) else cell
                # 类型转换
                if col.get("type") == "integer" and v is not None:
                    v = int(v)
                elif col.get("type") == "real" and v is not None:
                    v = float(v)
                d[col["name"]] = v
            # 同时支持 dict 和 .key 访问
            class Row(dict):
                def __getattr__(self, k):
                    return self.get(k)
                def __setattr__(self, k, v):
                    self[k] = v
            self._rows.append(Row(d))
        self._idx = 0
        self.rowcount = len(self._rows)
        self.lastrowid = int(res.get("last_insert_rowid") or 0)
        return self
    def executemany(self, sql, seq):
        for p in seq:
            self.execute(sql, p)
    def fetchone(self):
        if self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            return r
        return None
    def fetchall(self):
        return self._rows
    def commit(self):
        pass
    def rollback(self):
        pass
    def close(self):
        pass
    def __iter__(self):
        self._idx = 0
        return self
    def __next__(self):
        r = self.fetchone()
        if r is None:
            raise StopIteration
        return r


class DatabaseManager:
    """
    数据库管理类（单例模式）
    使用SQLite作为本地数据库，无需额外安装数据库服务
    """

    _instance = None

    def __new__(cls, db_path=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path=None):
        if self._initialized:
            return
        self._turso = bool(TURSO_URL and TURSO_TOKEN)
        if self._turso:
            self.db_path = TURSO_URL
            print(f"[DB] Turso Cloud: {TURSO_URL}")
        else:
            if db_path is None:
                if os.path.isdir("/data"):
                    db_dir = "/data"
                else:
                    db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
                os.makedirs(db_dir, exist_ok=True)
                db_path = os.path.join(db_dir, "detection.db")
            self.db_path = db_path
        self._init_tables()
        self._initialized = True

    @contextmanager
    def get_connection(self):
        """获取数据库连接"""
        if self._turso:
            try:
                conn = TursoConn(TURSO_URL, TURSO_TOKEN)
                yield conn
                return
            except Exception as e:
                print(f"[DB] Turso failed: {e}", file=__import__('sys').stderr)
                # fall through to SQLite
        # SQLite fallback
        db_path = self.db_path if not self._turso else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "detection.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """初始化数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    phone TEXT DEFAULT '',
                    password_hash TEXT NOT NULL,
                    balance REAL DEFAULT 0,
                    credits INTEGER DEFAULT 0,
                    reduce_ai_count INTEGER DEFAULT 0,
                    reduce_plagiarism_count INTEGER DEFAULT 0,
                    member_rewrite_count INTEGER DEFAULT 0,
                    member_rewrite_reset TEXT,
                    free_quota_used INTEGER DEFAULT 0,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER,
                    referral_reward_claimed INTEGER DEFAULT 0,
                    is_member INTEGER DEFAULT 0,
                    member_expiry TEXT,
                    member_quota_used INTEGER DEFAULT 0,
                    member_quota_reset TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            # 验证码表（跨worker共享，替代内存字典）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verify_codes (
                    account TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    expires TEXT NOT NULL
                )
            """)

            # 兼容旧表
            for col_sql in [
                "ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''",
                "ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0",
                "ALTER TABLE users ADD COLUMN credits INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN reduce_ai_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN reduce_plagiarism_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN member_rewrite_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN member_rewrite_reset TEXT",
                "ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE",
                "ALTER TABLE users ADD COLUMN referred_by INTEGER",
                "ALTER TABLE users ADD COLUMN referral_reward_claimed INTEGER DEFAULT 0",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            # 检测记录表（不存储原文，仅存哈希用于去重）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detection_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text_hash TEXT NOT NULL,
                    word_count INTEGER DEFAULT 0,
                    ai_score REAL DEFAULT 0,
                    plagiarism_score REAL DEFAULT 0,
                    report_data TEXT,
                    file_name TEXT,
                    status TEXT DEFAULT 'completed',
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # 计费记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS billing_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL DEFAULT 0,
                    word_count INTEGER DEFAULT 0,
                    transaction_type TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # 改写历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rewrite_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    original_text TEXT NOT NULL,
                    result_text TEXT NOT NULL,
                    char_count INTEGER DEFAULT 0,
                    action TEXT DEFAULT 'rewrite',
                    method TEXT DEFAULT 'simulation',
                    billing_type TEXT DEFAULT '',
                    billing_cost REAL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # 创建索引以提升查询性能
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_user_id
                ON detection_records(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_created_at
                ON detection_records(created_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_billing_user_id
                ON billing_records(user_id)
            """)

    # ==================== 用户相关操作 ====================

    def create_user(self, username: str, email: str, password_hash: str,
                    referral_code: str = None, referred_by: int = None,
                    phone: str = "") -> int:
        """创建新用户"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO users (username, email, password_hash, referral_code, referred_by, phone)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (username, email, password_hash, referral_code, referred_by, phone)
            )
            return cursor.lastrowid

    def get_user_by_id(self, user_id: int) -> dict | None:
        """根据ID获取用户"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_user_by_username(self, username: str) -> dict | None:
        """根据用户名获取用户"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict | None:
        """根据邮箱获取用户"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            return dict(row) if row else None

    def get_user_by_phone(self, phone: str) -> dict | None:
        """根据手机号获取用户"""
        if not phone:
            return None
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            return dict(row) if row else None

    def update_user_password(self, user_id: int, new_password_hash: str) -> bool:
        """更新用户密码"""
        with self.get_connection() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                        (new_password_hash, user_id))
            return True

    def update_user_quota(self, user_id: int, free_quota_used: int = None,
                          member_quota_used: int = None) -> bool:
        """更新用户额度使用量"""
        fields = []
        values = []
        if free_quota_used is not None:
            fields.append("free_quota_used = ?")
            values.append(free_quota_used)
        if member_quota_used is not None:
            fields.append("member_quota_used = ?")
            values.append(member_quota_used)
        if not fields:
            return False
        values.append(user_id)
        with self.get_connection() as conn:
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
            return True

    def set_user_member(self, user_id: int, months: int = 1) -> bool:
        """设置用户为会员"""
        from datetime import datetime, timedelta
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        now = datetime.now()
        # 如果已是会员且在有效期内，则续期
        current_expiry = user.get("member_expiry")
        if current_expiry:
            try:
                expiry_date = datetime.strptime(current_expiry, "%Y-%m-%d %H:%M:%S")
                if expiry_date > now:
                    new_expiry = expiry_date + timedelta(days=30 * months)
                else:
                    new_expiry = now + timedelta(days=30 * months)
            except ValueError:
                new_expiry = now + timedelta(days=30 * months)
        else:
            new_expiry = now + timedelta(days=30 * months)

        with self.get_connection() as conn:
            conn.execute(
                """UPDATE users SET is_member = 1, member_expiry = ?,
                   member_quota_used = 0, member_quota_reset = ? WHERE id = ?""",
                (new_expiry.strftime("%Y-%m-%d %H:%M:%S"),
                 now.replace(day=1).strftime("%Y-%m-%d %H:%M:%S"),
                 user_id)
            )
            return True

    # ==================== 邀请裂变相关操作 ====================

    def get_user_by_referral_code(self, referral_code: str) -> dict | None:
        """根据邀请码查找用户"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE referral_code = ?", (referral_code,)
            ).fetchone()
            return dict(row) if row else None

    def claim_referral_reward(self, user_id: int, reward_words: int = 10000) -> bool:
        """领取邀请奖励（给被邀请人增加免费额度）"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        if user.get("referral_reward_claimed"):
            return False  # 已领取过

        with self.get_connection() as conn:
            # 减少 free_quota_used（等同增加可用额度）
            new_used = max(0, user["free_quota_used"] - reward_words)
            conn.execute(
                "UPDATE users SET free_quota_used = ?, referral_reward_claimed = 1 WHERE id = ?",
                (new_used, user_id)
            )
            # 也给邀请人奖励
            referrer_id = user.get("referred_by")
            if referrer_id:
                referrer = self.get_user_by_id(referrer_id)
                if referrer:
                    referrer_new = max(0, referrer["free_quota_used"] - reward_words)
                    conn.execute(
                        "UPDATE users SET free_quota_used = ? WHERE id = ?",
                        (referrer_new, referrer_id)
                    )
            return True

    def get_referral_stats(self, user_id: int) -> dict:
        """获取用户的邀请统计"""
        with self.get_connection() as conn:
            # 被邀请人数
            invited_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM users WHERE referred_by = ?", (user_id,)
            ).fetchone()["cnt"]
            # 总获得奖励字数
            total_reward = invited_count * 10000

            # 获取用户自己的邀请码
            user = self.get_user_by_id(user_id)
            referral_code = user.get("referral_code") if user else None

            # 如果旧用户没有邀请码，自动生成一个
            if not referral_code and user:
                import random, string
                uname = user.get("username", "user")
                referral_code = uname[:8] + ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                conn.execute(
                    "UPDATE users SET referral_code = ? WHERE id = ?",
                    (referral_code, user_id)
                )

            return {
                "referral_code": referral_code,
                "invited_count": invited_count,
                "total_reward_words": total_reward,
                "reward_per_invite": 10000,
            }

    # ==================== 检测记录相关操作 ====================

    def create_detection_record(self, user_id: int, text_hash: str, word_count: int,
                                ai_score: float, plagiarism_score: float,
                                report_data: dict, file_name: str = None) -> int:
        """创建检测记录，返回记录ID"""
        import json
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO detection_records
                   (user_id, text_hash, word_count, ai_score, plagiarism_score,
                    report_data, file_name, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')""",
                (user_id, text_hash, word_count, ai_score, plagiarism_score,
                 json.dumps(report_data, ensure_ascii=False), file_name)
            )
            return cursor.lastrowid

    def get_user_detection_records(self, user_id: int, limit: int = 50, offset: int = 0) -> list:
        """获取用户的检测记录列表"""
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM detection_records
                   WHERE user_id = ? AND status = 'completed'
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (user_id, limit, offset)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_detection_record(self, record_id: int, user_id: int = None) -> dict | None:
        """获取单条检测记录"""
        with self.get_connection() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT * FROM detection_records WHERE id = ? AND user_id = ?",
                    (record_id, user_id)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM detection_records WHERE id = ?",
                    (record_id,)
                ).fetchone()
            return dict(row) if row else None

    def delete_old_records(self, hours: int = 1):
        """删除超过指定时间的检测记录（清理历史数据）"""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            conn.execute("DELETE FROM detection_records WHERE created_at < ?", (cutoff,))

    # ==================== 计费记录相关操作 ====================

    def create_billing_record(self, user_id: int, amount: float, word_count: int,
                              transaction_type: str, description: str = "") -> int:
        """创建计费记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO billing_records
                   (user_id, amount, word_count, transaction_type, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, amount, word_count, transaction_type, description)
            )
            return cursor.lastrowid

    def get_user_billing_records(self, user_id: int, limit: int = 50) -> list:
        """获取用户计费记录"""
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM billing_records
                   WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_user_total_consumption(self, user_id: int) -> float:
        """获取用户总消费金额"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM billing_records WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            return row["total"] if row else 0.0

    def get_user_stats(self, user_id: int) -> dict:
        """获取用户统计信息"""
        with self.get_connection() as conn:
            # 总检测次数
            total_detections = conn.execute(
                "SELECT COUNT(*) as cnt FROM detection_records WHERE user_id = ?",
                (user_id,)
            ).fetchone()["cnt"]

            # 总检测字数
            total_words = conn.execute(
                "SELECT COALESCE(SUM(word_count), 0) as total FROM detection_records WHERE user_id = ?",
                (user_id,)
            ).fetchone()["total"]

            # 本月检测次数
            from datetime import datetime
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
            monthly_detections = conn.execute(
                "SELECT COUNT(*) as cnt FROM detection_records WHERE user_id = ? AND created_at >= ?",
                (user_id, month_start)
            ).fetchone()["cnt"]

            return {
                "total_detections": total_detections,
                "total_words": total_words,
                "monthly_detections": monthly_detections,
            }


    # ==================== 充值额度相关操作 ====================

    def add_credits(self, user_id: int, words: int, amount: float) -> bool:
        """充值额度：增加余额记录和可用字数"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET credits = credits + ?, balance = balance + ? WHERE id = ?",
                (words, amount, user_id)
            )
            return True

    def deduct_credits(self, user_id: int, words: int) -> bool:
        """扣除字数额度（检测消耗）- 原子操作"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
                (words, user_id, words)
            )
            return cursor.rowcount > 0

    def get_user_credits(self, user_id: int) -> dict:
        """获取用户额度信息"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT balance, credits, free_quota_used, reduce_ai_count, reduce_plagiarism_count FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()
            if not row:
                return {"balance": 0, "credits": 0, "free_remaining": 0}
            free_remaining = max(0, 5000 - row["free_quota_used"])
            return {
                "balance": row["balance"],
                "credits": row["credits"],
                "free_remaining": free_remaining,
                "total_available": free_remaining + row["credits"],
                "reduce_ai_count": row["reduce_ai_count"],
                "reduce_plagiarism_count": row["reduce_plagiarism_count"],
            }

    def is_first_reduce_ai(self, user_id: int) -> bool:
        """检查是否首次降低AI率"""
        user = self.get_user_by_id(user_id)
        return (user.get("reduce_ai_count", 0) if user else 0) == 0

    def is_first_reduce_plagiarism(self, user_id: int) -> bool:
        """检查是否首次降低查重率"""
        user = self.get_user_by_id(user_id)
        return (user.get("reduce_plagiarism_count", 0) if user else 0) == 0

    def increment_reduce_ai(self, user_id: int) -> bool:
        """增加降低AI率使用次数"""
        with self.get_connection() as conn:
            conn.execute("UPDATE users SET reduce_ai_count = reduce_ai_count + 1 WHERE id = ?", (user_id,))
            return True

    def increment_reduce_plagiarism(self, user_id: int) -> bool:
        """增加降低查重率使用次数"""
        with self.get_connection() as conn:
            conn.execute("UPDATE users SET reduce_plagiarism_count = reduce_plagiarism_count + 1 WHERE id = ?", (user_id,))
            return True

    # ==================== 改写历史 ====================

    def create_rewrite_record(self, user_id: int, original: str, result: str,
                               char_count: int, action: str, method: str,
                               billing_type: str, billing_cost: float) -> int:
        """创建改写历史记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO rewrite_records (user_id, original_text, result_text, char_count, action, method, billing_type, billing_cost)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, original, result, char_count, action, method, billing_type, billing_cost)
            )
            return cursor.lastrowid

    def get_user_rewrite_records(self, user_id: int, limit: int = 30) -> list:
        """获取用户改写历史"""
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT id, char_count, action, method, billing_type, billing_cost, created_at
                   FROM rewrite_records WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]


# 全局数据库管理器实例
db = DatabaseManager()
