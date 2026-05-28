"""
计费服务 v2
- 普通版：每天免费检测1次
- Pro版：字数额度制，0.49元/千字
- 管理员：无限额度
"""

import math
from datetime import datetime
from config import config
from utils.database import db


class BillingService:

    @classmethod
    def get_recharge_packages(cls) -> list:
        return config.RECHARGE_PACKAGES

    @classmethod
    def is_admin(cls, user: dict) -> bool:
        """检查是否为管理员（无限额度）"""
        return user.get("username") == config.ADMIN_USERNAME

    @classmethod
    def get_available_quota(cls, user: dict) -> dict:
        """获取用户当前可用额度"""
        if cls.is_admin(user):
            return {
                "is_admin": True,
                "daily_free_remaining": 999,
                "credits": 999999,
                "member_remaining": 0,
                "balance": 0,
                "is_member": False,
                "total_remaining": 999999,
            }

        # 今日免费次数
        today = datetime.now().strftime("%Y-%m-%d")
        last_free_date = user.get("daily_free_date", "")
        if last_free_date != today:
            daily_used = 0
        else:
            daily_used = user.get("daily_free_used", 0)
        daily_free_remaining = max(0, config.DAILY_FREE_DETECTIONS - daily_used)

        credits = user.get("credits", 0)
        balance = user.get("balance", 0.0)

        # 会员
        is_valid_member = False
        member_remaining = 0
        if user.get("is_member"):
            member_expiry = user.get("member_expiry")
            if member_expiry:
                try:
                    expiry_date = datetime.strptime(member_expiry, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() < expiry_date:
                        is_valid_member = True
                        member_quota_used = user.get("member_quota_used", 0)
                        member_remaining = max(0, config.MEMBER_MONTHLY_QUOTA - member_quota_used)
                except (ValueError, TypeError):
                    pass

        total = daily_free_remaining * 10000 + credits + member_remaining
        return {
            "is_admin": False,
            "daily_free_remaining": daily_free_remaining,
            "credits": credits,
            "member_remaining": member_remaining,
            "balance": balance,
            "is_member": is_valid_member,
            "total_remaining": total,
        }

    @classmethod
    def deduct_quota(cls, user_id: int, word_count: int, use_pro: bool = False) -> dict:
        """
        扣除额度
        use_pro=False: 优先用每日免费（普通版）
        use_pro=True: 使用Pro字数额度
        """
        user = db.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "用户不存在"}

        quota = cls.get_available_quota(user)

        # 管理员无限
        if quota.get("is_admin"):
            return {"success": True, "mode": "admin", "cost": 0}

        # Pro版：只用字数额度
        if use_pro:
            if quota["credits"] >= word_count:
                db.deduct_credits(user_id, word_count)
                return {"success": True, "mode": "pro", "credits_used": word_count, "cost": round(word_count/1000*config.PRO_PRICE_PER_K, 2)}
            else:
                shortage = word_count - quota["credits"]
                cost = round(shortage / 1000 * config.PRO_PRICE_PER_K, 2)
                return {"success": False, "need_pay": True, "mode": "pro", "shortage": shortage, "cost": cost}

        # 普通版：优先每日免费
        if quota["daily_free_remaining"] > 0:
            today = datetime.now().strftime("%Y-%m-%d")
            db.update_user_quota(user_id, daily_free_used=user.get("daily_free_used",0)+1, daily_free_date=today)
            return {"success": True, "mode": "free", "cost": 0}

        # 免费用完了，提示升级Pro
        return {"success": False, "need_upgrade": True, "mode": "free_exhausted",
                "message": "今日免费次数已用完，请使用Pro版或明天再来"}

    @classmethod
    def purchase_credits(cls, user_id: int, package_index: int) -> dict:
        """购买充值额度"""
        packages = config.RECHARGE_PACKAGES
        if package_index < 0 or package_index >= len(packages):
            return {"success": False, "message": "无效的充值套餐"}
        pkg = packages[package_index]
        words = pkg["words"]
        user = db.get_user_by_id(user_id)
        is_first = (user.get("credits", 0) if user else 0) == 0
        if is_first and pkg["amount"] > 0:
            words = words * 2
        db.add_credits(user_id, words, pkg["amount"])
        desc = f"Pro版充值: {pkg['label']}" + (" (首充翻倍!)" if is_first else "")
        db.create_billing_record(user_id=user_id, amount=pkg["amount"], word_count=words,
                                 transaction_type="recharge", description=desc)
        return {"success": True, "message": f"充值成功!获得{words}字Pro额度"+(" (首充翻倍!)" if is_first else ""),
                "words": words, "amount": pkg["amount"], "first_recharge": is_first}

    @classmethod
    def purchase_member(cls, user_id: int) -> dict:
        success = db.set_user_member(user_id, months=1)
        if success:
            db.create_billing_record(user_id=user_id, amount=config.MEMBER_MONTHLY_PRICE,
                word_count=0, transaction_type="member",
                description=f"购买会员月卡 - {config.MEMBER_MONTHLY_PRICE}元/月")
            return {"success": True, "message": "会员开通成功!每月享50000字Pro额度", "price": config.MEMBER_MONTHLY_PRICE}
        return {"success": False, "message": "开通失败，请重试"}
