"""
用户中心路由 - 检测历史、报告查看、会员管理
"""

import json
from flask import Blueprint, render_template, request, session, jsonify, redirect, url_for, flash
from config import config
from utils.database import db
from utils.decorators import login_required
from services.billing import BillingService

user_bp = Blueprint("user", __name__, url_prefix="/user")


@user_bp.route("/center")
@login_required
def user_center():
    """用户中心页面"""
    user_id = session["user_id"]
    user = db.get_user_by_id(user_id)
    if not user:
        session.clear()
        return redirect(url_for("auth.login_page"))

    # 获取检测记录
    records_raw = db.get_user_detection_records(user_id, limit=30)
    records = []
    for r in records_raw:
        rec = dict(r)
        report_data = rec.get("report_data")
        if isinstance(report_data, str):
            try:
                report_data = json.loads(report_data)
            except json.JSONDecodeError:
                report_data = {}
        rec["report_data"] = report_data
        records.append(rec)

    # 获取额度信息
    quota_info = BillingService.get_available_quota(user)

    # 获取统计信息
    stats = db.get_user_stats(user_id)

    # 获取邀请裂变统计
    referral_stats = db.get_referral_stats(user_id)

    # 获取计费记录
    billing_records = db.get_user_billing_records(user_id, limit=20)

    return render_template(
        "user_center.html",
        user=user,
        records=records,
        quota_info=quota_info,
        stats=stats,
        referral_stats=referral_stats,
        billing_records=billing_records,
        config=config,
    )


@user_bp.route("/api/quota")
@login_required
def api_get_quota():
    """获取用户额度信息API"""
    user = db.get_user_by_id(session["user_id"])
    if not user:
        return jsonify({"success": False, "message": "用户不存在"}), 404

    quota_info = BillingService.get_available_quota(user)
    return jsonify({
        "success": True,
        "quota": quota_info,
        "free_limit": config.FREE_QUOTA_WORDS,
        "member_limit": config.MEMBER_MONTHLY_QUOTA,
    })


@user_bp.route("/api/records")
@login_required
def api_get_records():
    """获取检测记录API（分页）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    offset = (page - 1) * per_page

    records_raw = db.get_user_detection_records(
        session["user_id"], limit=per_page, offset=offset
    )

    records = []
    for r in records_raw:
        rec = dict(r)
        report_data = rec.get("report_data")
        if isinstance(report_data, str):
            try:
                report_data = json.loads(report_data)
            except json.JSONDecodeError:
                report_data = {}
        rec["report_data"] = report_data
        records.append(rec)

    return jsonify({"success": True, "records": records, "page": page})


@user_bp.route("/member")
def member_page():
    """会员充值页面"""
    user = None
    quota_info = None
    if "user_id" in session:
        user = db.get_user_by_id(session["user_id"])
        if user:
            quota_info = BillingService.get_available_quota(user)

    return render_template(
        "pricing.html",
        user=user,
        quota_info=quota_info,
        config=config,
    )


@user_bp.route("/api/purchase-member", methods=["POST"])
@login_required
def api_purchase_member():
    """
    购买会员API（接入支付）
    步骤：
    1. 创建支付订单 → 返回二维码/支付链接
    2. 前端展示二维码，用户扫码支付
    3. 支付平台回调 → 自动开通会员
    """
    from services.payment import PaymentService

    user_id = session["user_id"]
    amount = config.MEMBER_MONTHLY_PRICE
    description = f"{config.SITE_NAME} - 会员月卡"

    # 创建支付订单
    order = PaymentService.create_order(
        user_id=user_id,
        amount=amount,
        description=description,
        order_type="member",
    )

    if not order["success"]:
        return jsonify({"success": False, "message": "创建订单失败，请重试"}), 500

    return jsonify({
        "success": True,
        "message": "订单已创建",
        "order": {
            "order_id": order["order_id"],
            "amount": order["amount"],
            "qr_code": order["qr_code"],
            "pay_url": order["pay_url"],
            "channel": order["channel"],
        },
    })


@user_bp.route("/api/pay-mock-confirm")
def api_pay_mock_confirm():
    """
    模拟支付确认（测试用）
    实际生产中由支付平台回调 /api/pay-callback/wechat 或 alipay
    """
    order_id = request.args.get("order_id", "")
    user_id = request.args.get("user_id", 0, type=int)
    amount = request.args.get("amount", 0, type=float)

    if not order_id or not user_id:
        return jsonify({"success": False, "message": "参数错误"}), 400

    # 直接开通会员
    result = BillingService.purchase_member(user_id)

    if result["success"]:
        return jsonify({
            "success": True,
            "message": f"支付成功！会员已开通（模拟）",
            "amount": amount,
        })
    else:
        return jsonify({"success": False, "message": result.get("message", "开通失败")}), 500


@user_bp.route("/api/pay-callback/<channel>", methods=["POST"])
def api_pay_callback(channel):
    """
    支付平台回调接口
    xorpay/微信支付/支付宝 支付成功后POST到此地址
    """
    from services.payment import PaymentService

    if channel == "xorpay":
        callback_data = request.form.to_dict()
    elif channel == "wechat":
        # 微信支付回调数据在request.data中（XML格式）
        callback_data = request.get_json(force=True, silent=True) or {}
    elif channel == "alipay":
        callback_data = request.form.to_dict()
    else:
        return "FAIL", 400

    # 验证回调并处理
    result = PaymentService.verify_callback(callback_data)

    if result["success"]:
        # 支付成功，开通会员
        BillingService.purchase_member(result["user_id"])

        # 返回成功应答
        if channel == "wechat":
            return '<xml><return_code>SUCCESS</return_code></xml>', 200
        elif channel == "xorpay":
            return "ok", 200
        else:
            return "success", 200
    else:
        return "FAIL", 400


@user_bp.route("/api/ai-rewrite", methods=["POST"])
def api_ai_rewrite():
    """
    AI降重改写接口（DeepSeek驱动）
    提供一键降重、语句润色、语病修正、句式优化功能

    优先级：DeepSeek真实API > 本地模拟算法
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供文本内容"}), 400

        text = data.get("text", "").strip()
        action = data.get("action", "rewrite")  # rewrite/polish/fix/optimize

        if not text:
            return jsonify({"success": False, "message": "请输入要处理的文本"}), 400

        if len(text) < 10:
            return jsonify({"success": False, "message": "文本过短，至少需要10个字符"}), 400

        if len(text) > 5000:
            return jsonify({"success": False, "message": "单次最多处理5000字符"}), 400

        # ---- 优先使用DeepSeek真实API ----
        from services.api_client import DeepSeekClient

        if DeepSeekClient.is_configured():
            success, result_text, suggestions, error = DeepSeekClient.rewrite(text, action)
            if success:
                # 扣除额度
                _deduct_rewrite_quota(text)

                return jsonify({
                    "success": True,
                    "result_text": result_text,
                    "suggestions": suggestions,
                    "action": action,
                    "method": "deepseek",
                })
            else:
                # DeepSeek调用失败，记录错误并降级
                print(f"[AI改写] DeepSeek失败: {error}, 降级为模拟算法")

        # ---- 降级：本地模拟算法 ----
        result_text, suggestions = _simulate_ai_rewrite(text, action)

        # 扣除额度
        _deduct_rewrite_quota(text)

        return jsonify({
            "success": True,
            "result_text": result_text,
            "suggestions": suggestions,
            "action": action,
            "method": "simulation",
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"处理失败：{str(e)}"}), 500


def _deduct_rewrite_quota(text: str):
    """AI改写消耗额度（原文字数的10%，象征性扣除）"""
    from flask import session
    user_id = session.get("user_id")
    if user_id:
        user = db.get_user_by_id(user_id)
        if user:
            cost_words = max(1, len(text) // 10)
            BillingService.deduct_quota(user_id, cost_words)


def _simulate_ai_rewrite(text: str, action: str) -> tuple:
    """
    本地模拟AI处理（DeepSeek未配置时的降级方案）
    返回 (result_text, suggestions)
    """
    import hashlib
    import random

    text_seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    random.seed(text_seed)

    if action == "rewrite":
        result_text = f"【改写版】{text}"
        suggestions = [
            "已对原文进行同义替换和句式重组（模拟算法）",
            "建议接入DeepSeek API获得真实降重效果",
            "改写后可再次检测确认降重效果",
        ]
    elif action == "polish":
        result_text = f"【润色版】{text}"
        suggestions = [
            "已优化词语搭配和语句流畅度（模拟算法）",
            "建议接入DeepSeek API获得真实润色效果",
        ]
    elif action == "fix":
        result_text = f"【修正版】{text}"
        suggestions = [
            "已检查并修正常见语病（模拟算法）",
            "建议接入DeepSeek API获得真实修正效果",
        ]
    elif action == "optimize":
        result_text = f"【优化版】{text}"
        suggestions = [
            "已优化句式结构（模拟算法）",
            "建议接入DeepSeek API获得真实优化效果",
        ]
    else:
        result_text = text
        suggestions = []

    random.seed()
    return result_text, suggestions


# ==================== 邀请裂变API ====================

@user_bp.route("/api/referral-stats")
@login_required
def api_referral_stats():
    """获取邀请裂变统计"""
    stats = db.get_referral_stats(session["user_id"])
    stats["invite_link"] = f"{config.SITE_DOMAIN}/auth/register?ref={stats.get('referral_code', '')}"
    return jsonify({"success": True, "stats": stats})


@user_bp.route("/invite")
@login_required
def invite_page():
    """邀请好友页面"""
    user = db.get_user_by_id(session["user_id"])
    referral_stats = db.get_referral_stats(session["user_id"])
    referral_stats["invite_link"] = f"{config.SITE_DOMAIN}/auth/register?ref={referral_stats.get('referral_code', '')}"
    return render_template("invite.html", user=user, referral_stats=referral_stats, config=config)
