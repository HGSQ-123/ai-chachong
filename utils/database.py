"""
数据库管理器 - 使用SQLite实现数据持久化
封装所有数据库操作，支持用户、检测记录、计费记录的CRUD
"""

import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager


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
        # 默认数据库路径
        if db_path is None:
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "detection.db")
        self.db_path = db_path
        self._init_tables()
        self._initialized = True

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器，自动提交和关闭）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使查询结果支持字典式访问
        conn.execute("PRAGMA journal_mode=WAL")  # 提升并发性能
        conn.execute("PRAGMA foreign_keys=ON")    # 启用外键约束
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

            # 兼容旧表
            for col_sql in [
                "ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''",
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

    def claim_referral_reward(self, user_id: int, reward_words: int = 1000) -> bool:
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
            total_reward = invited_count * 1000

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
                "reward_per_invite": 1000,
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


# 全局数据库管理器实例
db = DatabaseManager()
