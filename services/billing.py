"""
计费服务
处理额度扣除、充值套餐、会员权益判断

设计理念：
- 充值买字数：0.5元/1000字，先充值后消费
- 新用户首次免费检测
- 会员月卡提供高性价比方案
"""

import math
from config import config
from utils.database import db


class BillingService:
    """
    计费服务类
    处理所有与费用、额度相关的业务逻辑
    """

    @classmethod
    def get_recharge_packages(cls) -> list:
        """获取充值套餐列表"""
        return config.RECHARGE_PACKAGES

    @classmethod
    def get_available_quota(cls, user: dict) -> dict:
        """
        获取用户当前可用额度

        返回:
            dict: {
                "free_remaining": int,         # 剩余免费额度
                "credits": int,                # 充值的剩余字数
                "member_remaining": int,       # 剩余会员额度
                "balance": float,              # 账户余额(元)
                "is_member": bool,             # 是否有效会员
                "total_remaining": int,        # 总剩余字数
                "first_detection_free": bool,  # 是否首次检测免费
            }
        """
        free_remaining = max(0, config.FREE_QUOTA_WORDS - user.get("free_quota_used", 0))
        credits = user.get("credits", 0)
        balance = user.get("balance", 0.0)
        
        # 首次检测
        first_free = config.FIRST_DETECTION_FREE and user.get("free_quota_used", 0) == 0

        # 检查会员状态
        is_valid_member = False
        member_remaining = 0

        if user.get("is_member"):
            from datetime import datetime
            member_expiry = user.get("member_expiry")
            if member_expiry:
                try:
                    expiry_date = datetime.strptime(member_expiry, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() < expiry_date:
                        is_valid_member = True
                        member_quota_reset = user.get("member_quota_reset")
                        if member_quota_reset:
                            try:
                                reset_date = datetime.strptime(member_quota_reset, "%Y-%m-%d %H:%M:%S")
                                if datetime.now().month != reset_date.month:
                                    member_quota_used = 0
                                    db.update_user_quota(user["id"], member_quota_used=0)
                                else:
                                    member_quota_used = user.get("member_quota_used", 0)
                            except ValueError:
                                member_quota_used = user.get("member_quota_used", 0)
                        else:
                            member_quota_used = user.get("member_quota_used", 0)
                        member_remaining = max(0, config.MEMBER_MONTHLY_QUOTA - member_quota_used)
                except (ValueError, TypeError):
                    pass

        total = free_remaining + credits + member_remaining

        return {
            "free_remaining": free_remaining,
            "credits": credits,
            "member_remaining": member_remaining,
            "balance": balance,
            "is_member": is_valid_member,
            "total_remaining": total,
            "first_detection_free": first_free,
        }

    @classmethod
    def deduct_quota(cls, user_id: int, word_count: int) -> dict:
        """
        扣除用户额度（优先级：首次免费 > 会员额度 > 免费额度 > 充值额度）

        返回:
            dict: {
                "success": bool,
                "free_used": int,        # 使用了多少免费额度
                "member_used": int,      # 使用了多少会员额度
                "credits_used": int,     # 使用了多少充值额度
                "extra_needed": int,     # 需要额外充值的字数
                "extra_cost": float,     # 额外费用(元)
            }
        """
        user = db.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "用户不存在"}

        quota_info = cls.get_available_quota(user)
        
        # 首次检测免费
        if quota_info["first_detection_free"]:
            db.update_user_quota(user_id, free_quota_used=word_count)
            return {
                "success": True,
                "free_used": word_count,
                "member_used": 0,
                "credits_used": 0,
                "extra_needed": 0,
                "extra_cost": 0,
                "first_free": True,
            }

        remaining = word_count
        free_used = 0
        member_used = 0
        credits_used = 0

        # 1. 优先使用会员额度
        if quota_info["member_remaining"] > 0 and remaining > 0:
            member_used = min(remaining, quota_info["member_remaining"])
            remaining -= member_used
            new_member_used = user.get("member_quota_used", 0) + member_used
            db.update_user_quota(user_id, member_quota_used=new_member_used)

        # 2. 其次使用免费额度
        if quota_info["free_remaining"] > 0 and remaining > 0:
            free_used = min(remaining, quota_info["free_remaining"])
            remaining -= free_used
            new_free_used = user.get("free_quota_used", 0) + free_used
            db.update_user_quota(user_id, free_quota_used=new_free_used)

        # 3. 最后使用充值额度
        if quota_info["credits"] > 0 and remaining > 0:
            credits_used = min(remaining, quota_info["credits"])
            remaining -= credits_used
            db.deduct_credits(user_id, credits_used)

        # 超出部分需要充值
        extra_needed = remaining
        extra_cost = 0
        if extra_needed > 0:
            k_words = math.ceil(extra_needed / 1000)
            extra_cost = round(k_words * config.CREDIT_PRICE_PER_K, 2)

        return {
            "success": True,
            "free_used": free_used,
            "member_used": member_used,
            "credits_used": credits_used,
            "extra_needed": extra_needed,
            "extra_cost": extra_cost,
        }

    @classmethod
    def purchase_member(cls, user_id: int) -> dict:
        """
        购买会员月卡
        """
        success = db.set_user_member(user_id, months=1)
        if success:
            db.create_billing_record(
                user_id=user_id,
                amount=config.MEMBER_MONTHLY_PRICE,
                word_count=0,
                transaction_type="member",
                description=f"购买会员月卡 - {config.MEMBER_MONTHLY_PRICE}元/月"
            )
            return {
                "success": True,
                "message": "会员开通成功！每月享50000字检测额度",
                "price": config.MEMBER_MONTHLY_PRICE,
            }
        return {"success": False, "message": "开通失败，请重试"}

    @classmethod
    def purchase_credits(cls, user_id: int, package_index: int) -> dict:
        """
        购买充值额度套餐
        
        参数:
            user_id: 用户ID
            package_index: 套餐索引 (0-4)
        """
        packages = config.RECHARGE_PACKAGES
        if package_index < 0 or package_index >= len(packages):
            return {"success": False, "message": "无效的充值套餐"}
        
        pkg = packages[package_index]
        db.add_credits(user_id, pkg["words"], pkg["amount"])
        db.create_billing_record(
            user_id=user_id,
            amount=pkg["amount"],
            word_count=pkg["words"],
            transaction_type="recharge",
            description=f"充值额度: {pkg['label']}"
        )
        return {
            "success": True,
            "message": f"充值成功！获得{pkg['words']}字额度",
            "words": pkg["words"],
            "amount": pkg["amount"],
        }
