"""
计费服务
处理字数统计、阶梯价格计算、额度扣除、会员权益判断

设计理念：
- 清晰的阶梯定价，透明消费
- 免费额度引流 → 付费转化
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
    def calculate_price(cls, word_count: int) -> dict:
        """
        根据字数计算阶梯价格

        参数:
            word_count: 待检测字数

        返回:
            dict: {
                "word_count": int,
                "price_per_k": float,      # 适用单价（元/千字）
                "total_price": float,       # 总价（元）
                "tier_label": str,          # 价格档位说明
            }
        """
        if word_count <= 0:
            return {
                "word_count": 0,
                "price_per_k": 0,
                "total_price": 0,
                "tier_label": "无",
            }

        # 遍历价格阶梯，找到适用档位
        for tier in config.PRICING_TIERS:
            if word_count <= tier["max_words"]:
                price_per_k = tier["price_per_k"]
                tier_label = tier["label"]
                break

        # 按千字计费（不足千字按千字算）
        k_words = math.ceil(word_count / 1000)
        total_price = round(k_words * price_per_k, 2)

        return {
            "word_count": word_count,
            "price_per_k": price_per_k,
            "total_price": total_price,
            "tier_label": tier_label,
        }

    @classmethod
    def get_available_quota(cls, user: dict) -> dict:
        """
        获取用户当前可用额度

        返回:
            dict: {
                "free_quota_remaining": int,     # 剩余免费额度
                "member_quota_remaining": int,   # 剩余会员额度
                "is_member": bool,               # 是否有效会员
                "total_remaining": int,          # 总剩余额度
            }
        """
        free_remaining = max(0, config.FREE_QUOTA_WORDS - user.get("free_quota_used", 0))

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
                        # 检查是否需要重置月度额度
                        member_quota_reset = user.get("member_quota_reset")
                        if member_quota_reset:
                            try:
                                reset_date = datetime.strptime(member_quota_reset, "%Y-%m-%d %H:%M:%S")
                                if datetime.now().month != reset_date.month:
                                    # 新月，重置会员额度
                                    member_quota_used = 0
                                    db.update_user_quota(
                                        user["id"],
                                        member_quota_used=0
                                    )
                                else:
                                    member_quota_used = user.get("member_quota_used", 0)
                            except ValueError:
                                member_quota_used = user.get("member_quota_used", 0)
                        else:
                            member_quota_used = user.get("member_quota_used", 0)

                        member_remaining = max(0, config.MEMBER_MONTHLY_QUOTA - member_quota_used)
                except (ValueError, TypeError):
                    pass

        return {
            "free_quota_remaining": free_remaining,
            "member_quota_remaining": member_remaining,
            "is_member": is_valid_member,
            "total_remaining": free_remaining + member_remaining,
        }

    @classmethod
    def deduct_quota(cls, user_id: int, word_count: int) -> dict:
        """
        扣除用户额度（优先使用会员额度，再使用免费额度）

        返回:
            dict: {
                "success": bool,
                "free_used": int,        # 使用了多少免费额度
                "member_used": int,      # 使用了多少会员额度
                "extra_needed": int,     # 需要额外付费的字数
                "extra_cost": float,     # 额外费用
            }
        """
        user = db.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "用户不存在"}

        quota_info = cls.get_available_quota(user)
        remaining = word_count

        free_used = 0
        member_used = 0
        extra_needed = 0

        # 优先使用会员额度
        if quota_info["member_quota_remaining"] > 0:
            member_used = min(remaining, quota_info["member_quota_remaining"])
            remaining -= member_used
            new_member_used = user.get("member_quota_used", 0) + member_used
            db.update_user_quota(user_id, member_quota_used=new_member_used)

        # 其次使用免费额度
        if remaining > 0 and quota_info["free_quota_remaining"] > 0:
            free_used = min(remaining, quota_info["free_quota_remaining"])
            remaining -= free_used
            new_free_used = user.get("free_quota_used", 0) + free_used
            db.update_user_quota(user_id, free_quota_used=new_free_used)

        # 超出部分需要付费
        extra_needed = remaining
        extra_cost = 0
        if extra_needed > 0:
            price_info = cls.calculate_price(extra_needed)
            extra_cost = price_info["total_price"]

        return {
            "success": True,
            "free_used": free_used,
            "member_used": member_used,
            "extra_needed": extra_needed,
            "extra_cost": extra_cost,
        }

    @classmethod
    def purchase_member(cls, user_id: int) -> dict:
        """
        购买会员月卡

        返回:
            dict: {"success": bool, "message": str, "expiry": str}
        """
        success = db.set_user_member(user_id, months=1)
        if success:
            # 记录计费记录
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
