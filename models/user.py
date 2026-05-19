"""
用户数据模型
包含用户基本信息、会员状态、额度管理
"""

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash


class User:
    """
    用户模型
    - free_quota_used: 已使用的免费额度（字数）
    - is_member: 是否为会员
    - member_expiry: 会员到期时间
    - member_quota_used: 本月已使用的会员额度
    - member_quota_reset: 会员额度重置日期（每月1号）
    """

    def __init__(self, username, email, password_hash=None, user_id=None,
                 free_quota_used=0, is_member=False, member_expiry=None,
                 member_quota_used=0, member_quota_reset=None, created_at=None):
        self.id = user_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.free_quota_used = free_quota_used
        self.is_member = is_member
        self.member_expiry = member_expiry
        self.member_quota_used = member_quota_used
        self.member_quota_reset = member_quota_reset or datetime.now().replace(day=1)
        self.created_at = created_at or datetime.now()

    @staticmethod
    def hash_password(password: str) -> str:
        """对密码进行哈希加密"""
        return generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        """验证密码是否正确"""
        return check_password_hash(self.password_hash, password)

    def get_remaining_free_quota(self, free_limit: int) -> int:
        """获取剩余免费额度"""
        return max(0, free_limit - self.free_quota_used)

    def get_remaining_member_quota(self, monthly_limit: int) -> int:
        """获取剩余会员额度（自动处理月度重置）"""
        now = datetime.now()
        # 如果到了新的月份，重置会员额度
        if now.month != self.member_quota_reset.month or now.year != self.member_quota_reset.year:
            self.member_quota_used = 0
            self.member_quota_reset = now.replace(day=1)
        return max(0, monthly_limit - self.member_quota_used)

    def is_valid_member(self) -> bool:
        """检查会员是否在有效期内"""
        if not self.is_member:
            return False
        if self.member_expiry and datetime.now() > self.member_expiry:
            self.is_member = False
            return False
        return True

    def to_dict(self) -> dict:
        """序列化为字典（不包含密码）"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "free_quota_used": self.free_quota_used,
            "is_member": self.is_member,
            "member_expiry": self.member_expiry.strftime("%Y-%m-%d") if self.member_expiry else None,
            "member_quota_used": self.member_quota_used,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
        }
